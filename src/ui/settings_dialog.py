import flet as ft
from pathlib import Path
from app_info import APP_VERSION, CHANGELOG_URL, ISSUES_URL, REPO_URL, RELEASES_URL
from app_storage.module_store import ModuleStore
from app_storage.app_config import AppConfig
from app_storage.secrets_store import SecretsStore
from app_logging import get_logger
import updater
from sync.gdrive import TOKEN_KEY, resolve_client_secret
from sync.service import unidocs_token_key, webdav_password_key
from sync.unidocs import UniDocsProvider
from sync.webdav import WebDAVProvider
from ui.theme import MODE_LABELS, PALETTES, ThemeManager
from ui.update_install import UpdateInstaller

log = get_logger(__name__)

# The settings body is a navigation list on the left plus one scrollable
# panel on the right. The panel must never get narrower than the widest
# control in it - the System / Light / Dark switch - because Flet would then
# squeeze the labels onto two lines. Below the nav breakpoint the list
# collapses into a dropdown above the panel; on very narrow windows the
# switch drops its text labels so it fits even then.
NAV_WIDTH = 176             # left navigation list
NAV_PANEL_GAP = 48          # spacing + divider + padding next to the list
NAV_BREAKPOINT = 640        # below this: nav list becomes a dropdown
CONTENT_MAX_WIDTH = 780     # widest the dialog ever gets
CONTENT_MIN_WIDTH = 380
CONTENT_MAX_HEIGHT = 560
CONTENT_MIN_HEIGHT = 320
CONTENT_SIDE_MARGIN = 72    # dialog padding + a little breathing room
CONTENT_HEIGHT_MARGIN = 180 # title bar + dialog actions + window chrome
COMPACT_BREAKPOINT = 400    # below this: mode selector drops its text labels

class SettingsDialog(ft.AlertDialog):
    """
    A self-contained settings dialog.

    Usage
    -----
        dialog = SettingsDialog(store=store, on_location_change=callback)
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    Callbacks
    ---------
        on_location_change(new_path: Path)
            Fired when the user confirms a new UniDocs location.
            
            The caller is responsible for reloading the store / sidebar.
    """

    def __init__(
        self,
        store: ModuleStore,
        on_location_change=None,
        theme: ThemeManager | None = None,
        sync_service=None,
    ):
        super().__init__()
        self._store = store
        self._cfg = AppConfig()
        self._on_location_change = on_location_change
        self._sync_service = sync_service
        self._secrets = SecretsStore()
        # Shared with main.py when available; otherwise a local fallback is
        # created and attached once this dialog mounts.
        self._theme = theme or ThemeManager(self._cfg)
        # Responsive body (see _build_content / _apply_layout).
        self._content_width = CONTENT_MAX_WIDTH
        self._content_height = CONTENT_MAX_HEIGHT
        self._nav_compact = False
        self._selected_section = 0
        self._resize_hooked = False
        self._prev_resize_handler = None
        # Esc closes the dialog: while it is open this dialog owns the page
        # keyboard hook and forwards every other key to whoever held it before
        # (the detail view uses the same hook to track Ctrl/Shift).
        self._prev_key_handler = None

        self._path_field = ft.TextField(
            value=str(store.root),
            expand=True,
            hint_text="Absolute path to UniDocs folder",
            on_submit=self._apply,
        )

        self._status = ft.Text("", color=ft.Colors.ERROR, size=12)

        #  update check 
        # The whole update state lives in these few controls: the check runs in
        # a background thread and only ever writes into them.
        self._update_asset: tuple[str, str] | None = None

        self._check_button = ft.FilledButton(
            "Check for updates",
            icon=ft.Icons.SYSTEM_UPDATE_ALT,
            on_click=self._check_for_updates,
        )
        self._update_progress = ft.ProgressRing(
            width=16, height=16, stroke_width=2, visible=False
        )
        self._update_status = ft.Text(
            "", size=12, color=ft.Colors.ON_SURFACE_VARIANT
        )

        # Only one of the two download buttons is ever visible: on Windows the
        # button installs in place, everywhere else it opens the release page.
        self._install_button = ft.FilledButton(
            "Download and install",
            icon=ft.Icons.DOWNLOAD,
            visible=False,
            on_click=self._download_and_install,
        )
        self._download_button = ft.FilledButton(
            "Open release page",
            icon=ft.Icons.OPEN_IN_NEW,
            visible=False,
            url=RELEASES_URL,
        )
        self._notes_button = ft.TextButton(
            "Release notes",
            icon=ft.Icons.DESCRIPTION,
            visible=False,
            url=RELEASES_URL,
        )
        self._update_actions = ft.Row(
            spacing=8,
            visible=False,
            wrap=True,
            controls=[
                self._install_button,
                self._download_button,
                self._notes_button,
            ],
        )

        # Download + restart-in-place is shared with the startup popup.
        self._installer = UpdateInstaller(
            self._update_status,
            on_busy=self._install_busy,
            on_failed=self._install_failed,
        )

        # Patch releases (2.3.0 -> 2.3.1) are installed on startup without
        # asking. Only an install that can replace itself may do that - the
        # Windows setup. Linux and macOS have no silent install at all, so the
        # switch and its note are hidden there instead of sitting greyed out
        # with an explanation.
        self._can_self_update = updater.can_self_update()
        self._auto_patch_switch = ft.Switch(
            label="Install patches automatically",
            value=self._cfg.auto_install_patches and self._can_self_update,
            on_change=self._on_auto_patch_change,
            disabled=not self._can_self_update,
            visible=self._can_self_update,
        )
        self._auto_patch_note = ft.Text(
            "Patch releases such as 2.3.0 → 2.3.1 are installed quietly on startup.",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
            visible=self._can_self_update,
        )

        #  appearance controls 
        # The segment labels are kept so a narrow window can swap the text out
        # for icon-only segments (see _apply_layout) - three labelled segments
        # do not fit into a very narrow dialog.
        self._mode_segments = [
            ft.Segment(value="system", label=ft.Text(MODE_LABELS["system"]),
                       icon=ft.Icon(ft.Icons.BRIGHTNESS_AUTO)),
            ft.Segment(value="light", label=ft.Text(MODE_LABELS["light"]),
                       icon=ft.Icon(ft.Icons.LIGHT_MODE)),
            ft.Segment(value="dark", label=ft.Text(MODE_LABELS["dark"]),
                       icon=ft.Icon(ft.Icons.DARK_MODE)),
        ]
        self._compact_segments = False
        self._mode_selector = ft.SegmentedButton(
            selected=[self._theme.mode],
            allow_multiple_selection=False,
            show_selected_icon=False,
            segments=self._mode_segments,
            on_change=self._on_mode_change,
        )

        self._palette_dropdown = ft.Dropdown(
            label="Color palette",
            value=self._theme.palette_id,
            options=[
                ft.dropdown.Option(key=p.id, text=p.label)
                for p in PALETTES.values()
            ],
            on_select=self._on_palette_change,
            expand=True,
        )

        #  startup controls 
        # Remember the group / module that was on screen, so the next launch can
        # return there. The module switch only makes sense inside a remembered
        # group, so it is greyed out while the first one is off.
        self._restore_group_switch = ft.Switch(
            label="Reopen in the last group",
            value=self._cfg.restore_group,
            on_change=self._on_restore_group_change,
        )
        self._restore_module_switch = ft.Switch(
            label="Also reopen the last module",
            value=self._cfg.restore_module and self._cfg.restore_group,
            on_change=self._on_restore_module_change,
            disabled=not self._cfg.restore_group,
        )

        #  cloud sync controls
        self._sync_provider = ft.Dropdown(
            label="Cloud sync",
            value=self._cfg.sync_provider,
            options=[
                ft.dropdown.Option(key="off", text="Off (local only)"),
                ft.dropdown.Option(key="unidocs", text="UniDocs server"),
                ft.dropdown.Option(key="webdav", text="Nextcloud / WebDAV"),
                ft.dropdown.Option(key="gdrive", text="Google Drive"),
            ],
            on_select=self._on_sync_provider_change,
            expand=True,
        )
        self._unidocs_url = ft.TextField(
            label="Server URL",
            value=self._cfg.unidocs_url,
            hint_text="https://unidocs.example.com",
            dense=True,
        )
        self._unidocs_token = ft.TextField(
            label="API token",
            hint_text="Leave empty to keep the saved token",
            password=True,
            can_reveal_password=True,
            dense=True,
        )
        self._unidocs_save = ft.FilledButton(
            "Save & test",
            icon=ft.Icons.CLOUD_DONE_OUTLINED,
            on_click=self._save_unidocs,
        )
        self._webdav_url = ft.TextField(
            label="Server URL",
            value=self._cfg.webdav_url,
            hint_text="https://cloud.example.com/remote.php/dav/files/user",
            dense=True,
        )
        self._webdav_user = ft.TextField(
            label="Username",
            value=self._cfg.webdav_username,
            dense=True,
        )
        self._webdav_password = ft.TextField(
            label="App password",
            hint_text="Leave empty to keep the saved password",
            password=True,
            can_reveal_password=True,
            dense=True,
        )
        self._webdav_root = ft.TextField(
            label="Remote folder",
            value=self._cfg.webdav_root,
            dense=True,
        )
        self._webdav_save = ft.FilledButton(
            "Save & test",
            icon=ft.Icons.CLOUD_DONE_OUTLINED,
            on_click=self._save_webdav,
        )
        self._sync_progress = ft.ProgressRing(
            width=16, height=16, stroke_width=2, visible=False
        )
        self._sync_status = ft.Text(
            "", size=12, color=ft.Colors.ON_SURFACE_VARIANT
        )
        self._unidocs_group = ft.Column(
            spacing=6,
            tight=True,
            controls=[
                self._unidocs_url,
                self._unidocs_token,
                ft.Row(
                    spacing=8,
                    controls=[self._unidocs_save, self._sync_progress],
                ),
                ft.Text(
                    "The token is printed when the server starts "
                    "(unidocs-server) and lives in ~/.config/UniDocs/server_token.txt.",
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
        )
        self._webdav_group = ft.Column(
            spacing=6,
            tight=True,
            controls=[
                self._webdav_url,
                self._webdav_user,
                self._webdav_password,
                self._webdav_root,
                ft.Row(
                    spacing=8,
                    controls=[self._webdav_save, self._sync_progress],
                ),
            ],
        )

        self._gdrive_secret_path = ft.TextField(
            label="OAuth client_secret.json",
            value=self._cfg.gdrive_client_secret_path,
            hint_text="Your own Google Cloud desktop client",
            dense=True,
            expand=True,
        )
        self._gdrive_browse = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            tooltip="Choose client_secret.json",
            on_click=self._pick_client_secret,
        )
        self._gdrive_connect = ft.FilledButton(
            "Connect & sync",
            icon=ft.Icons.LOGIN,
            on_click=self._google_connect,
        )
        self._gdrive_disconnect = ft.TextButton(
            "Disconnect",
            icon=ft.Icons.LOGOUT,
            on_click=self._google_disconnect,
        )
        self._gdrive_secret_row = ft.Row(
            spacing=4,
            controls=[self._gdrive_secret_path, self._gdrive_browse],
        )
        self._gdrive_managed_note = ft.Text(
            "This build includes the Google app registration. Click Connect & sync "
            "and sign in with your own Google account; files stay in your Drive.",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        self._gdrive_group = ft.Column(
            spacing=6,
            tight=True,
            controls=[
                ft.Text("Google Drive", weight=ft.FontWeight.W_600),
                self._gdrive_managed_note,
                self._gdrive_secret_row,
                ft.Row(
                    spacing=8,
                    controls=[self._gdrive_connect, self._gdrive_disconnect],
                ),
                ft.Text(
                    "The app only sees files it created itself (drive.file scope).",
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
        )

        self._sync_on_start_switch = ft.Switch(
            label="Sync on startup",
            value=self._cfg.sync_on_start,
            on_change=self._on_sync_on_start_change,
        )
        self._sync_now_button = ft.FilledButton(
            "Sync now",
            icon=ft.Icons.CLOUD_SYNC,
            on_click=self._sync_now,
        )
        self._trash_auto_switch = ft.Switch(
            label="Empty trash automatically",
            value=self._cfg.trash_auto_empty_enabled,
            on_change=self._on_trash_auto_change,
        )
        self._trash_days = ft.TextField(
            label="Keep trash for (days)",
            value=str(self._cfg.trash_retention_days),
            width=150,
            dense=True,
            disabled=not self._cfg.trash_auto_empty_enabled,
            on_blur=self._on_trash_days_change,
            on_submit=self._on_trash_days_change,
        )
        self._sync_section = self._section(
            "Cloud sync",
            self._sync_provider,
            self._unidocs_group,
            self._webdav_group,
            self._gdrive_group,
            self._sync_status,
            ft.Row(
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[self._sync_on_start_switch, self._sync_now_button],
            ),
            ft.Divider(height=1),
            ft.Row(
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[self._trash_auto_switch, self._trash_days],
            ),
        )
        self._apply_sync_visibility()
        self._apply_gdrive_visibility()

        #  LAYOUT
        self.modal = True
        # Flet fires this when the dialog closes for any reason - keep the
        # keyboard hook tidy even if we did not close it ourselves.
        self.on_dismiss = self._on_dismiss
        # The panel scrolls on its own; Material must not wrap the whole body
        # in another scroll view, else the nav list would scroll away too.
        self.scrollable = False

        self.title = ft.Row(
            spacing=8,
            controls=[
                ft.Icon(ft.Icons.SETTINGS, size=20),
                ft.Text("Settings", size=18, weight=ft.FontWeight.BOLD),
            ],
        )

        #  section panels - one per navigation entry
        self._section_columns = [
            # General: appearance + startup
            ft.Column(
                tight=True,
                spacing=16,
                controls=[
                    # UniDocs folder location
                    # TODO: auskommentiert, kommt spaeter wieder rein
                    # ft.Column(spacing=0, controls=[
                    #     ft.Text("UniDocs location", weight=ft.FontWeight.W_600),
                    #     ft.Row(controls=[self._path_field]),
                    #     self._status,
                    # ]),
                    #
                    # ft.Divider(height=1),

                    # Appearance (theme palette + light/dark mode)
                    self._section(
                        "Appearance",
                        self._mode_selector,
                        # The palette dropdown floats its label above the field,
                        # so it needs extra room below the mode selector.
                        ft.Container(height=12, bgcolor=ft.Colors.TRANSPARENT),
                        self._palette_dropdown,
                        ft.Text(
                            "Changes apply instantly and are saved.",
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ),

                    ft.Divider(height=1),

                    # Startup (reopen group / module)
                    self._section(
                        "Startup",
                        self._restore_group_switch,
                        self._restore_module_switch,
                        ft.Text(
                            "Off: the app always opens on Home.",
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ),
                ],
            ),
            # Cloud sync + trash retention
            ft.Column(
                tight=True,
                spacing=16,
                controls=[self._sync_section],
            ),
            # Update check
            ft.Column(
                tight=True,
                spacing=16,
                controls=[
                    self._section(
                        "Updates",
                        ft.Row(
                            spacing=8,
                            controls=[self._check_button, self._update_progress],
                        ),
                        self._update_status,
                        self._update_actions,
                        self._auto_patch_switch,
                        self._auto_patch_note,
                    ),
                ],
            ),
            # About / links
            ft.Column(
                tight=True,
                spacing=16,
                controls=[
                    self._section(
                        "About",
                        self._link_row("Source code", ft.Icons.CODE, REPO_URL),
                        self._link_row("Releases", ft.Icons.NEW_RELEASES, RELEASES_URL),
                        self._link_row("Changelog", ft.Icons.DESCRIPTION, CHANGELOG_URL),
                        self._link_row(
                            "Report an issue",
                            ft.Icons.BUG_REPORT_OUTLINED,
                            ISSUES_URL,
                        ),
                        ft.Text(
                            f"Version {APP_VERSION}",
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ),
                ],
            ),
        ]

        # Only the first panel is visible; _show_section toggles the rest.
        for index, panel in enumerate(self._section_columns):
            panel.visible = index == 0

        #  navigation (list on wide windows, dropdown on narrow ones)
        nav_entries = [
            ("General", ft.Icons.TUNE),
            ("Cloud sync", ft.Icons.CLOUD_SYNC),
            ("Updates", ft.Icons.SYSTEM_UPDATE_ALT),
            ("About", ft.Icons.INFO_OUTLINE),
        ]
        self._nav_items = [
            ft.ListTile(
                leading=ft.Icon(icon, size=20),
                title=ft.Text(label, size=14),
                dense=True,
                selected=index == 0,
                selected_tile_color=ft.Colors.SECONDARY_CONTAINER,
                on_click=lambda e, index=index: self._show_section(index),
            )
            for index, (label, icon) in enumerate(nav_entries)
        ]
        self._nav_dropdown = ft.Dropdown(
            options=[
                ft.dropdown.Option(key=str(index), text=label)
                for index, (label, _icon) in enumerate(nav_entries)
            ],
            value="0",
            on_select=self._on_nav_select,
            visible=False,
        )
        self._nav_area = ft.Container(
            width=NAV_WIDTH,
            content=ft.Column(
                width=NAV_WIDTH,
                spacing=2,
                tight=True,
                controls=self._nav_items,
            ),
        )
        self._vdiv = ft.Container(
            width=1,
            height=self._content_height,
            bgcolor=ft.Colors.OUTLINE_VARIANT,
        )
        self._section_host = ft.Column(
            tight=True,
            spacing=0,
            controls=self._section_columns,
        )
        self._content_pane = ft.Column(
            expand=True,
            spacing=16,
            controls=[
                self._nav_dropdown,
                ft.Column(
                    expand=True,
                    scroll=ft.ScrollMode.AUTO,
                    controls=[self._section_host],
                ),
            ],
        )
        self._body = ft.Container(
            width=self._content_width,
            height=self._content_height,
            content=ft.Row(
                spacing=24,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[self._nav_area, self._vdiv, self._content_pane],
            ),
        )
        self.content = self._build_content()

        # Everything here applies instantly, so there is nothing to "Apply":
        # a single Back button ends the dialog (Esc does the same).
        self.actions = [
            ft.FilledButton(
                "Back",
                icon=ft.Icons.ARROW_BACK,
                on_click=self._close,
            ),
        ]

    #  lifecycle 

    def did_mount(self):
        # Bind the fallback manager (if enabled) to the live page.
        if not self._theme.attached:
            self._theme.attach(self.page)
        # Re-layout whenever the window is resized: the nav list folds into a
        # dropdown on narrow windows (see _apply_layout).
        self._hook_resize()
        self._apply_layout()

    #  responsive layout 

    def _build_content(self) -> ft.Container:
        """Body of the dialog: navigation list plus one scrollable panel."""
        return self._body

    def _show_section(self, index: int) -> None:
        """Switch the panel to `index` and sync nav list + dropdown."""
        if not 0 <= index < len(self._section_columns):
            return
        self._selected_section = index
        # All panels stay mounted; hiding is cheaper than swapping children
        # (and a detached control must not be re-attached later).
        for i, panel in enumerate(self._section_columns):
            panel.visible = i == index
        self._nav_dropdown.value = str(index)
        for i, tile in enumerate(self._nav_items):
            tile.selected = i == index
        self.update()

    def _on_nav_select(self, e) -> None:
        try:
            index = int(self._nav_dropdown.value or 0)
        except ValueError:
            index = 0
        self._show_section(index)

    def _apply_layout(self) -> None:
        """Fit the body to the current window (called on mount + resize)."""
        page = self.page
        if page is None or not self._resize_hooked:
            return
        page_width = page.width or CONTENT_MAX_WIDTH
        page_height = page.height or 900
        width = int(
            max(CONTENT_MIN_WIDTH,
                min(CONTENT_MAX_WIDTH, page_width - CONTENT_SIDE_MARGIN))
        )
        height = int(
            max(CONTENT_MIN_HEIGHT,
                min(CONTENT_MAX_HEIGHT, page_height - CONTENT_HEIGHT_MARGIN))
        )
        nav_compact = width < NAV_BREAKPOINT
        panel_width = width if nav_compact else width - NAV_WIDTH - NAV_PANEL_GAP
        compact = panel_width < COMPACT_BREAKPOINT
        if (width, height, nav_compact, compact) == (
            self._content_width, self._content_height,
            self._nav_compact, self._compact_segments,
        ):
            return
        self._content_width = width
        self._content_height = height
        self._nav_compact = nav_compact
        self._apply_compact_segments(compact)
        self._apply_nav_mode(nav_compact)
        self._body.width = width
        self._body.height = height
        self._vdiv.height = height
        self.update()

    def _apply_nav_mode(self, compact: bool) -> None:
        """Wide: list on the left. Narrow: dropdown above the panel."""
        self._nav_area.visible = not compact
        self._vdiv.visible = not compact
        self._nav_dropdown.visible = compact

    def _apply_compact_segments(self, compact: bool) -> None:
        """Drop the mode labels on very narrow windows so the segments fit."""
        self._compact_segments = compact
        for seg in self._mode_segments:
            # A fresh Text every time: a control detached from the segment must
            # not be re-attached later.
            seg.label = None if compact else ft.Text(MODE_LABELS[seg.value])

    def _hook_resize(self) -> None:
        page = self.page
        if page is None or self._resize_hooked:
            return
        self._resize_hooked = True
        self._prev_resize_handler = getattr(page, "on_resize", None)
        page.on_resize = self._on_resize

    def _unhook_resize(self) -> None:
        page = self.page
        if page is None or not self._resize_hooked:
            return
        self._resize_hooked = False
        page.on_resize = self._prev_resize_handler

    def _on_resize(self, e=None):
        self._apply_layout()
        prev = self._prev_resize_handler
        if callable(prev):
            try:
                prev(e)
            except Exception as ex:
                # We chained onto someone else's handler; its crash must not
                # take our dialog down, but it should not vanish either.
                log.warning("Previous keyboard handler failed: %s", ex)

    #  helpers 

    def _section(self, title: str, *controls) -> ft.Column:
        return ft.Column(
            spacing=6,
            tight=True,
            controls=[
                ft.Text(title, weight=ft.FontWeight.W_600),
                *controls,
            ],
        )

    def _link_row(self, label: str, icon: str, url: str) -> ft.TextButton:
        # `url` is handled natively by Flet: clicking opens the link in the
        # user's default browser (works on both desktop and web).
        return ft.TextButton(label, icon=icon, url=url)

    #  private 

    def _on_mode_change(self, e):
        # `selected` is a list of Segment.value strings (Flet 0.84).
        selected = list(e.control.selected or [])
        self._theme.set_mode(selected[0] if selected else "system")

    def _sync_mode_selector(self) -> None:
        """Re-align the segmented button after an external mode change."""
        self._mode_selector.selected = [self._theme.mode]

    def _sync_palette_dropdown(self) -> None:
        """Re-align the palette dropdown after an external change."""
        self._palette_dropdown.value = self._theme.palette_id

    def _sync_startup_switches(self) -> None:
        """Re-align the startup switches with the stored config."""
        self._restore_group_switch.value = self._cfg.restore_group
        self._restore_module_switch.disabled = not self._cfg.restore_group
        self._restore_module_switch.value = (
            self._cfg.restore_module and self._cfg.restore_group
        )

    #  cloud sync helpers

    def _apply_sync_visibility(self) -> None:
        provider = self._cfg.sync_provider
        self._unidocs_group.visible = provider == "unidocs"
        self._webdav_group.visible = provider == "webdav"
        # Offer the one-click Google login also while sync is off.
        self._gdrive_group.visible = provider in ("off", "gdrive")
        self._sync_now_button.disabled = provider == "off"
        self._trash_days.disabled = not self._cfg.trash_auto_empty_enabled

    def _apply_gdrive_visibility(self) -> None:
        managed = bool(resolve_client_secret(self._cfg.gdrive_client_secret_path))
        self._gdrive_managed_note.visible = managed
        self._gdrive_secret_row.visible = not managed

    def _sync_sync_controls(self) -> None:
        self._sync_provider.value = self._cfg.sync_provider
        self._unidocs_url.value = self._cfg.unidocs_url
        self._unidocs_token.value = ""
        self._webdav_url.value = self._cfg.webdav_url
        self._webdav_user.value = self._cfg.webdav_username
        self._webdav_password.value = ""
        self._webdav_root.value = self._cfg.webdav_root
        self._gdrive_secret_path.value = self._cfg.gdrive_client_secret_path
        self._sync_on_start_switch.value = self._cfg.sync_on_start
        self._trash_auto_switch.value = self._cfg.trash_auto_empty_enabled
        self._trash_days.value = str(self._cfg.trash_retention_days)
        self._sync_status.value = ""
        self._sync_progress.visible = False
        self._apply_sync_visibility()
        self._apply_gdrive_visibility()

    def _on_sync_provider_change(self, e) -> None:
        self._cfg.sync_provider = self._sync_provider.value or "off"
        self._apply_sync_visibility()
        self._sync_status.value = ""
        self.update()

    def _on_sync_on_start_change(self, e) -> None:
        self._cfg.sync_on_start = bool(self._sync_on_start_switch.value)

    def _on_trash_auto_change(self, e) -> None:
        self._cfg.trash_auto_empty_enabled = bool(self._trash_auto_switch.value)
        self._trash_days.disabled = not self._cfg.trash_auto_empty_enabled
        self.update()

    def _on_trash_days_change(self, e) -> None:
        try:
            days = int((self._trash_days.value or "").strip())
        except ValueError:
            days = self._cfg.trash_retention_days
        self._cfg.trash_retention_days = days
        self._trash_days.value = str(self._cfg.trash_retention_days)
        self.update()

    def _save_webdav(self, e) -> None:
        url = (self._webdav_url.value or "").strip()
        user = (self._webdav_user.value or "").strip()
        root = (self._webdav_root.value or "UniDocs").strip() or "UniDocs"
        password = self._webdav_password.value or ""
        self._cfg.webdav_url = url
        self._cfg.webdav_username = user
        self._cfg.webdav_root = root
        self._set_sync_busy(True, "Connecting…")
        page = self.page
        if page is None:
            return
        page.run_thread(lambda: self._test_webdav_worker(url, user, password, root))

    def _save_unidocs(self, e) -> None:
        url = (self._unidocs_url.value or "").strip().rstrip("/")
        token = self._unidocs_token.value or ""
        self._cfg.unidocs_url = url
        self._set_sync_busy(True, "Connecting…")
        page = self.page
        if page is None:
            return
        page.run_thread(lambda: self._test_unidocs_worker(url, token))

    def _test_unidocs_worker(self, url, token) -> None:
        error = None
        try:
            if not url:
                raise ValueError("Server URL is missing")
            if token:
                self._secrets.set_secret(unidocs_token_key(url), token)
            else:
                token = self._secrets.get_secret(unidocs_token_key(url)) or ""
                if not token:
                    raise ValueError("API token is missing")
            provider = UniDocsProvider(url, token)
            try:
                provider.test_connection()
            finally:
                provider.close()
        except Exception as ex:
            error = str(ex)
        page = self.page
        if page is not None:
            page.run_task(self._show_webdav_result, error)

    def _test_webdav_worker(self, url, user, password, root) -> None:
        error = None
        try:
            if not url:
                raise ValueError("Server URL is missing")
            if password:
                self._secrets.set_secret(webdav_password_key(url, user), password)
            else:
                password = self._secrets.get_secret(webdav_password_key(url, user)) or ""
                if not password:
                    raise ValueError("App password is missing")
            provider = WebDAVProvider(url, user, password, remote_root=root)
            try:
                provider.test_connection()
            finally:
                provider.close()
        except Exception as ex:
            error = str(ex)
        page = self.page
        if page is not None:
            page.run_task(self._show_webdav_result, error)

    async def _show_webdav_result(self, error) -> None:
        self._set_sync_busy(False)
        if error:
            self._set_sync_status(f"Error: {error}", error=True)
        else:
            self._set_sync_status("Connection successful.")
        self.update()

    def _set_sync_busy(self, busy: bool, message: str = "") -> None:
        self._unidocs_save.disabled = busy
        self._webdav_save.disabled = busy
        self._sync_progress.visible = busy
        if message:
            self._set_sync_status(message)

    def _set_sync_status(self, message: str, *, error: bool = False) -> None:
        self._sync_status.value = message
        self._sync_status.color = (
            ft.Colors.ERROR if error else ft.Colors.ON_SURFACE_VARIANT
        )

    async def _pick_client_secret(self, e) -> None:
        files = await ft.FilePicker().pick_files(
            allow_multiple=False,
            allowed_extensions=["json"],
            dialog_title="Google client_secret.json",
        )
        if files:
            path = getattr(files[0], "path", "") or ""
            if path:
                self._gdrive_secret_path.value = path
                self._cfg.gdrive_client_secret_path = path
                self.update()

    def _google_connect(self, e) -> None:
        path = (self._gdrive_secret_path.value or "").strip()
        self._cfg.gdrive_client_secret_path = path
        self._cfg.sync_provider = "gdrive"
        self._sync_provider.value = "gdrive"
        self._apply_sync_visibility()
        if not resolve_client_secret(path):
            self._set_sync_status(
                "This build has no Google client. Select client_secret.json first.",
                error=True,
            )
            self.update()
            return
        if self._sync_service is None:
            self._set_sync_status("Sync service is not available.", error=True)
            self.update()
            return
        if not self._sync_service.start(interactive=True):
            self._set_sync_status("A sync is already running or the provider is off.", error=True)
        else:
            # Connected once, then keep syncing on every start. The switch
            # stays visible so the user can turn it off again.
            self._cfg.sync_on_start = True
            self._sync_on_start_switch.value = True
            self._set_sync_status("Google login in the browser…")
        self.update()

    def _google_disconnect(self, e) -> None:
        page = self.page
        if page is None:
            return
        page.run_thread(self._google_disconnect_worker)

    def _google_disconnect_worker(self) -> None:
        try:
            self._secrets.delete_secret(TOKEN_KEY)
            message = "Google Drive disconnected."
        except Exception as ex:
            message = f"Disconnect failed: {ex}"
        page = self.page
        if page is not None:
            page.run_task(self._show_sync_message, message)

    async def _show_sync_message(self, message: str) -> None:
        self._set_sync_status(message)
        self.update()

    def _sync_now(self, e) -> None:
        if self._sync_service is None:
            self._set_sync_status("Sync service is not available.", error=True)
            self.update()
            return
        if not self._sync_service.start():
            self._set_sync_status("A sync is already running or the provider is off.", error=True)
        else:
            self._set_sync_status("Sync started…")
        self.update()

    #  public

    def show(self) -> None:
        """Open the dialog, re-syncing the appearance controls first."""
        # Re-hook the resize callback: closing the dialog hands the page hook
        # back (see _unhook_resize), and did_mount does not fire again.
        self._hook_resize()
        self._apply_layout()
        self._cfg.reload()
        self._sync_mode_selector()
        self._sync_palette_dropdown()
        self._sync_startup_switches()
        self._sync_sync_controls()
        self._status.value = ""
        self._reset_update_section()
        self._install_key_handler()
        self.open = True
        self.update()

    def _on_palette_change(self, e):
        self._theme.set_palette(self._palette_dropdown.value)

    def _on_restore_group_change(self, e):
        enabled = bool(self._restore_group_switch.value)
        self._cfg.restore_group = enabled
        # The module restore only works on top of a restored group.
        self._restore_module_switch.disabled = not enabled
        if not enabled:
            self._restore_module_switch.value = False
            self._cfg.restore_module = False
        self.update()

    def _on_restore_module_change(self, e):
        if self._restore_module_switch.disabled:
            return
        self._cfg.restore_module = bool(self._restore_module_switch.value)

    def _close(self, e=None):
        """End the dialog (Back button / Esc)."""
        self._status.value = ""
        self.open = False
        self._restore_key_handler()
        self._unhook_resize()
        self.update()

    def _on_dismiss(self, e=None):
        """Flet event fired whenever the dialog closes - keep the hook tidy."""
        self._restore_key_handler()
        self._unhook_resize()

    #  keyboard 

    def _install_key_handler(self) -> None:
        """Take over the page keyboard hook while the dialog is open."""
        page = self.page
        if page is None:
            return
        self._prev_key_handler = getattr(page, "on_keyboard_event", None)
        page.on_keyboard_event = self._on_key_event

    def _restore_key_handler(self) -> None:
        """Hand the page keyboard hook back to whoever owned it before."""
        page = self.page
        if page is None:
            return
        page.on_keyboard_event = self._prev_key_handler

    def _on_key_event(self, e):
        key = getattr(e, "key", "") or ""
        if key in ("Escape", "Esc"):
            self._close()
            return
        # Forward everything else so the detail view keeps tracking Ctrl/Shift.
        prev = self._prev_key_handler
        if callable(prev):
            try:
                prev(e)
            except Exception as ex:
                # We chained onto someone else's handler; its crash must not
                # take our dialog down, but it should not vanish either.
                log.warning("Previous keyboard handler failed: %s", ex)

    def _apply(self, e):
        raw = self._path_field.value.strip()
        if not raw:
            self._show_error("Path cannot be empty.")
            return

        new_path = Path(raw).expanduser().resolve()

        if new_path == self._store.root:
            self.open = False
            self.update()
            return

        try:
            new_path.mkdir(parents=True, exist_ok=True)
        except OSError as ex:
            self._show_error(f"Cannot create folder: {ex}")
            return

        # persist to config.json so the path survives restarts
        self._cfg.unidocs_location = new_path

        self._store.root = new_path
        self._status.value = ""
        self.open = False
        self.update()

        if self._on_location_change:
            self._on_location_change(new_path)

    def _show_error(self, msg: str):
        self._status.value = msg
        self.update()

    #  update check 
    #
    # Layout: one click -> ``_check_for_updates`` (UI thread) puts the section
    # into "checking" and hands the actual network call to ``page.run_thread``.
    # The worker never touches the widgets itself; it posts back with
    # ``page.run_task``, so every UI write happens on the page's event loop.

    def _reset_update_section(self) -> None:
        """Back to the idle state (also called on every ``show()``)."""
        self._update_asset = None
        self._set_update_busy(False)
        self._update_status.value = ""
        self._update_status.color = ft.Colors.ON_SURFACE_VARIANT
        self._update_actions.visible = False
        self._auto_patch_switch.value = (
            self._cfg.auto_install_patches and self._can_self_update
        )

    def _on_auto_patch_change(self, e) -> None:
        if not self._can_self_update:
            return
        self._cfg.auto_install_patches = bool(self._auto_patch_switch.value)

    def _set_update_busy(self, busy: bool) -> None:
        self._check_button.disabled = busy
        self._update_progress.visible = busy
        if busy:
            self._update_actions.visible = False

    def _set_update_status(self, message: str, *, error: bool = False) -> None:
        self._update_status.value = message
        self._update_status.color = (
            ft.Colors.ERROR if error else ft.Colors.ON_SURFACE_VARIANT
        )

    def _check_for_updates(self, e):
        self._set_update_busy(True)
        self._set_update_status("Checking for updates…")
        self.update()
        self.page.run_thread(self._check_worker)

    # -- worker (background thread) -----------------------------------------

    def _check_worker(self) -> None:
        try:
            release = updater.fetch_latest()
        except updater.UpdateError as ex:
            self.page.run_task(self._show_check_result, None, str(ex))
            return
        self.page.run_task(self._show_check_result, release, None)

    # -- results (event loop) -----------------------------------------------

    async def _show_check_result(self, release, error) -> None:
        self._set_update_busy(False)

        if error:
            self._set_update_status(f"Could not check for updates: {error}", error=True)
            self.update()
            return

        try:
            newer = updater.is_newer(release.version, APP_VERSION)
        except updater.UpdateError as ex:
            self._set_update_status(f"Could not read the released version: {ex}", error=True)
            self.update()
            return

        if not newer:
            self._set_update_status(
                f"UniDocs {APP_VERSION} is the latest version."
            )
            self.update()
            return

        self._update_asset = updater.asset_for(release)

        note = "" if self._update_asset else " (no download for this system)"
        self._set_update_status(
            f"Version {release.version} is available — you have {APP_VERSION}.{note}"
        )
        self._notes_button.url = release.page_url
        self._notes_button.visible = True

        if updater.can_install_update(self._update_asset):
            self._install_button.visible = True
        elif self._update_asset:
            # Nothing installs itself here (Linux, macOS, a Windows zip), so the
            # button only hands over to the release page - no download behind
            # the user's back.
            self._download_button.url = release.page_url
            self._download_button.visible = True

        self._update_actions.visible = True
        self.update()

    # -- install ------------------------------------------------------------

    def _download_and_install(self, e):
        """Fetch the update and let it replace this install (then restart)."""
        if self._update_asset:
            self._installer.start(self._update_asset)

    #  called by the shared installer 

    def _install_busy(self, busy: bool) -> None:
        self._set_update_busy(busy)
        if not busy:
            # The install can only fail when it is over, so the buttons have to
            # come back for a retry.
            self._update_actions.visible = True

    def _install_failed(self, message: str) -> None:
        self._set_update_status(f"Update failed: {message}", error=True)
        self.update()
