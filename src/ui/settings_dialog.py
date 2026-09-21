import flet as ft
from pathlib import Path
from app_storage.module_store import ModuleStore
from app_storage.app_config import AppConfig

CURRENT_VERSION = "2.2.0"

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

    def __init__(self, store: ModuleStore, on_location_change=None):
        super().__init__()
        self._store = store
        self._cfg = AppConfig()
        self._on_location_change = on_location_change

        self._path_field = ft.TextField(
            value=str(store.root),
            expand=True,
            hint_text="Absolute path to UniDocs folder",
            on_submit=self._apply,
        )

        self._status = ft.Text("", color=ft.Colors.RED_400, size=12)

        #  LAYOUT 
        self.modal = True

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

                    # Themes
                    self._section(
                        "Themes",
                        ft.Row(
                            spacing=8,
                            controls=[
                                ft.Icon(
                                    ft.Icons.PALETTE_OUTLINED,
                                    size=16,
                                    color=ft.Colors.GREY_500,
                                ),
                                ft.Text(
                                    "Coming soon",
                                    size=13,
                                    color=ft.Colors.GREY_500,
                                ),
                            ],
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
                            color=ft.Colors.GREY_500,
                        ),
                    ),
                ],
            ),
        )

        self.actions = [
            ft.TextButton("Cancel", on_click=self._cancel),
            ft.FilledButton("Apply", on_click=self._apply),
        ]

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

        # basic validation
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

        # commit to live store
        self._store.root = new_path
        self._status.value = ""
        self.open = False
        self.update()

        if self._on_location_change:
            self._on_location_change(new_path)

    def _show_error(self, msg: str):
        self._status.value = msg
        self.update()
