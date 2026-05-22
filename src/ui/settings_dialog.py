import flet as ft
from pathlib import Path
from app_storage.module_store import ModuleStore
from app_storage.app_config import AppConfig


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

        #  layout 
        self.modal = True
        self.title = ft.Row(
            controls=[
                ft.Icon(ft.Icons.SETTINGS, size=20),
                ft.Text("Settings", size=18, weight=ft.FontWeight.BOLD),
            ],
            spacing=8,
        )


        self.content = ft.Container(
            width=480,
            content=ft.Column(
                tight=True,
                spacing=16,
                controls=[
                    #  UniDocs location 
                    ft.Text("UniDocs location", weight=ft.FontWeight.W_600),
                    ft.Row(
                        controls=[
                            self._path_field,
                        ],
                    ),
                    self._status,

                    #  Bug Reporting 
                    ft.Markdown(
                        "If you discover any bugs, errors or you have a suggestion " \
                        "feel free to create an issue on GitHub, "
                        "or contact me to give further ideas or suggestions.  "
                    ),
                    ft.Row(controls=[
                        ft.Button("Create Issue", on_click=self.open_website("https://github.com/Lukas-dev-de/UniDocs/issues/new")),
                        ft.Button("Contact", on_click=self.open_website("mailto:lukas.buschauer@gmail.com")),
                    ]),
             
                ],
            ),
        )

        self.actions = [
            ft.TextButton("Cancel", on_click=self._cancel),
            ft.FilledButton("Apply", on_click=self._apply),
        ]
        self.actions_alignment = ft.MainAxisAlignment.END

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

    async def open_website(self, url:str):
        if url:
            await self.page.launch_url(url=url)
            print(f"open website {url}")
        print("")