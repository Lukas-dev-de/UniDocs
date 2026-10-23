import flet as ft
from pathlib import Path
from app_storage.module_store import ModuleStore
from app_storage.app_config import AppConfig
import updater
from ui.theme import MODE_LABELS, PALETTES, ThemeManager
from ui.update_install import UpdateInstaller

CURRENT_VERSION = "2.5.0"

# The settings body is a two-column layout. The columns must never get
# narrower than the widest control in them - the System / Light / Dark switch -
# because Flet would then squeeze the labels onto two lines. So the whole body
# falls back to a single stacked column before that width is reached; below the
# second breakpoint the switch drops its text labels so it fits even then.
COLUMN_MIN_WIDTH = 374      # width the mode selector needs next to its icon
CONTENT_MAX_WIDTH = 780     # widest the dialog ever gets
STACK_BREAKPOINT = 2 * COLUMN_MIN_WIDTH + 32   # = full dialog width
COMPACT_BREAKPOINT = 400    # below this: mode selector drops its text labels
CONTENT_MIN_WIDTH = 300
CONTENT_SIDE_MARGIN = 72    # dialog padding + a little breathing room

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
        # Responsive body (see _build_content / _apply_layout).
        self._content_width = CONTENT_MAX_WIDTH
        self._stacked = False
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

        #  LAYOUT 
        self.modal = True
        # Flet fires this when the dialog closes for any reason - keep the
        # keyboard hook tidy even if we did not close it ourselves.
        self.on_dismiss = self._on_dismiss
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

        # Left column: appearance + startup. Right column: updates + about.
        self._left_column = ft.Column(
            expand=True,
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
        )

        self._right_column = ft.Column(
            expand=True,
            tight=True,
            spacing=16,
            controls=[
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
        # Re-layout whenever the window is resized: below the breakpoint the two
        # columns stack into one (see _apply_layout).
        self._hook_resize()
        self._apply_layout()

    #  responsive layout 

    def _build_content(self) -> ft.Container:
        """Body of the dialog: two side-by-side columns, or one stacked column."""
        # In a Row the columns share the available width; stacked they have to
        # size to their own content instead.
        self._left_column.expand = not self._stacked
        self._right_column.expand = not self._stacked
        if self._stacked:
            body = ft.Column(
                tight=True,
                spacing=24,
                controls=[self._left_column, self._right_column],
            )
        else:
            body = ft.Row(
                spacing=32,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[self._left_column, self._right_column],
            )
        return ft.Container(width=self._content_width, content=body)

    def _apply_layout(self) -> None:
        """Fit the body to the current window width (called on mount + resize)."""
        page = self.page
        if page is None or not self._resize_hooked:
            return
        page_width = page.width or CONTENT_MAX_WIDTH
        width = int(
            max(CONTENT_MIN_WIDTH,
                min(CONTENT_MAX_WIDTH, page_width - CONTENT_SIDE_MARGIN))
        )
        stacked = width < STACK_BREAKPOINT
        compact = width < COMPACT_BREAKPOINT
        if (width, stacked, compact) == (
            self._content_width, self._stacked, self._compact_segments
        ):
            return
        self._content_width = width
        self._stacked = stacked
        self._apply_compact_segments(compact)
        self.content = self._build_content()
        self.update()

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
            except Exception:
                pass

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

    #  public 

    def show(self) -> None:
        """Open the dialog, re-syncing the appearance controls first."""
        # Re-hook the resize callback: closing the dialog hands the page hook
        # back (see _unhook_resize), and did_mount does not fire again.
        self._hook_resize()
        self._apply_layout()
        self._sync_mode_selector()
        self._sync_palette_dropdown()
        self._sync_startup_switches()
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
            except Exception:
                pass

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

        if updater.can_install_update(self._update_asset):
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
            self._installer.start(self._update_asset, self._update_release)

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
