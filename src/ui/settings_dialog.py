import flet as ft
from pathlib import Path
from app_storage.module_store import ModuleStore
from app_storage.app_config import AppConfig
from ui.theme import MODE_LABELS, PALETTES, ThemeManager

CURRENT_VERSION = "2.3.0"

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
