import flet as ft
from pathlib import Path
from app_storage.module_store import ModuleStore
from app_storage.app_config import AppConfig
import updater
from ui.theme import MODE_LABELS, PALETTES, ThemeManager
from ui.update_install import UpdateInstaller

CURRENT_VERSION = "2.4.0"

REPO_URL = "https://github.com/Lukas-dev-de/UniDocs"
RELEASES_URL = f"{REPO_URL}/releases"
CHANGELOG_URL = f"{REPO_URL}/blob/main/CHANGELOG.md"
ISSUES_URL = f"{REPO_URL}/issues"

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

    def __init__(self, store: ModuleStore, on_location_change=None, theme: ThemeManager | None = None):
        super().__init__()
        self._store = store
        self._cfg = AppConfig()
        self._on_location_change = on_location_change
        # Shared with main.py when available; otherwise a local fallback is
        # created and attached once this dialog mounts.
        self._theme = theme or ThemeManager(self._cfg)

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
        self._update_release: updater.Release | None = None
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

        # Only one of the two download buttons is ever visible: where UniDocs can
        # replace itself (Windows installer, Linux install.sh / AppImage) the
        # button installs in place, everywhere else the browser gets the archive.
        self._install_button = ft.FilledButton(
            "Download and install",
            icon=ft.Icons.DOWNLOAD,
            visible=False,
            on_click=self._download_and_install,
        )
        self._download_button = ft.FilledButton(
            "Download",
            icon=ft.Icons.DOWNLOAD,
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
        # asking. Only an install that can replace itself may do that: on
        # macOS, and on Linux when running from source or a read-only folder,
        # the switch sits at "off" and greyed out instead of promising
        # something that will not happen.
        self._can_self_update = updater.can_self_update()
        self._auto_patch_switch = ft.Switch(
            label="Install patches automatically",
            value=self._cfg.auto_install_patches and self._can_self_update,
            on_change=self._on_auto_patch_change,
            disabled=not self._can_self_update,
        )
        self._auto_patch_note = ft.Text(
            "Patch releases such as 2.3.0 → 2.3.1 are installed quietly on startup."
            if self._can_self_update
            else "Only available in the installed builds (Windows setup, Linux "
            "install.sh / AppImage).",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )

        #  appearance controls 
        self._mode_selector = ft.SegmentedButton(
            selected=[self._theme.mode],
            allow_multiple_selection=False,
            show_selected_icon=False,
            segments=[
                ft.Segment(value="system", label=ft.Text(MODE_LABELS["system"]),
                           icon=ft.Icon(ft.Icons.BRIGHTNESS_AUTO)),
                ft.Segment(value="light", label=ft.Text(MODE_LABELS["light"]),
                           icon=ft.Icon(ft.Icons.LIGHT_MODE)),
                ft.Segment(value="dark", label=ft.Text(MODE_LABELS["dark"]),
                           icon=ft.Icon(ft.Icons.DARK_MODE)),
            ],
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

        #  LAYOUT 
        self.modal = True
        # Let Material wrap title + content in a scroll view, so that on a short
        # window the body scrolls instead of overflowing past the dialog (and
        # the window) while the buttons stay visible.
        self.scrollable = True

        self.title = ft.Row(
            spacing=8,
            controls=[
                ft.Icon(ft.Icons.SETTINGS, size=20),
                ft.Text("Settings", size=18, weight=ft.FontWeight.BOLD),
            ],
        )

        self.content = ft.Container(
            width=480,
            content=ft.Column(
                tight=True,
                spacing=16,
                controls=[
                    # UniDocs folder location
                    ft.Column(spacing=0, controls=[
                        ft.Text("UniDocs location", weight=ft.FontWeight.W_600),
                        ft.Row(controls=[self._path_field]),
                        self._status,
                    ]),

                    ft.Divider(height=1),

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

                    # Update check
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

                    ft.Divider(height=1),

                    # About / links
                    self._section(
                        "About",
                        self._link_row("Source code", ft.Icons.CODE, REPO_URL),
                        self._link_row("Releases", ft.Icons.NEW_RELEASES, RELEASES_URL),
                        self._link_row("Changelog", ft.Icons.DESCRIPTION, CHANGELOG_URL),
                        self._link_row("Report an issue", ft.Icons.BUG_REPORT_OUTLINED, ISSUES_URL),
                        ft.Text(
                            f"Version {CURRENT_VERSION}",
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ),
                ],
            ),
        )

        self.actions = [
            ft.TextButton("Cancel", on_click=self._cancel),
            ft.FilledButton("Apply", on_click=self._apply),
        ]

    #  lifecycle 

    def did_mount(self):
        # Bind the fallback manager (if enabled) to the live page.
        if not self._theme.attached:
            self._theme.attach(self.page)

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

    #  public 

    def show(self) -> None:
        """Open the dialog, re-syncing the appearance controls first."""
        self._sync_mode_selector()
        self._sync_palette_dropdown()
        self._status.value = ""
        self._reset_update_section()
        self.open = True
        self.update()

    def _on_palette_change(self, e):
        self._theme.set_palette(self._palette_dropdown.value)

    def _cancel(self, e):
        self._status.value = ""
        self.open = False
        self.update()

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
        self._update_release = None
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
            newer = updater.is_newer(release.version, CURRENT_VERSION)
        except updater.UpdateError as ex:
            self._set_update_status(f"Could not read the released version: {ex}", error=True)
            self.update()
            return

        if not newer:
            self._set_update_status(
                f"UniDocs {CURRENT_VERSION} is the latest version."
            )
            self.update()
            return

        self._update_release = release
        self._update_asset = updater.asset_for(release)

        note = "" if self._update_asset else " (no download for this system)"
        self._set_update_status(
            f"Version {release.version} is available — you have {CURRENT_VERSION}.{note}"
        )
        self._notes_button.url = release.page_url
        self._notes_button.visible = True

        if updater.can_install_asset(self._update_asset) and updater.can_self_update():
            self._install_button.visible = True
        elif self._update_asset:
            self._download_button.url = self._update_asset[1]
            self._download_button.visible = True

        self._update_actions.visible = True
        self.update()

    # -- install ------------------------------------------------------------

    def _download_and_install(self, e):
        """Fetch the update and let it replace this install (then restart)."""
        if self._update_asset:
            self._installer.start(self._update_asset[1])

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
