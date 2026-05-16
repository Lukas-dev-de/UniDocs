import flet as ft
from ui.components.module_tile import ModuleTile
from ui.components.icon_selector import IconSelector
from ui.settings_dialog import SettingsDialog
from models.module import Module
from storage.module_store import ModuleStore


@ft.control
class ModuleSidebar(ft.Container):
    expand: int = 1
    padding: int = 8
    border_radius: int = 16
    bgcolor: ft.Colors = ft.Colors.GREY_900

    def __init__(self, store: ModuleStore, on_module_select=None):
        super().__init__()
        self._store = store
        self._on_module_select = on_module_select

        self.modules_list = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)

        self.icon_selector = IconSelector()
        self.title_field = ft.TextField(
            hint_text="New Module", on_submit=self.add_module, expand=True
        )
        self.description_field = ft.TextField(
            hint_text="Description", on_submit=self.add_module
        )

        ### UI-LAYOUT ###
        self.content = ft.Column(
            expand=True,
            alignment="CENTER",
            controls=[
                # header row: add-module button + settings button
                ft.Column(
                    alignment="CENTER",
                    controls=[
                        # Add Module Dialog
                        ft.PopupMenuButton(
                            icon=ft.Icons.ADD_BOX,
                            tooltip="Add Module",
                            items=[
                                ft.PopupMenuItem(
                                    content=ft.Row(
                                        controls=[self.icon_selector, self.title_field]
                                    ),
                                    padding=8,
                                ),
                                ft.PopupMenuItem(
                                    content=self.description_field, padding=8
                                ),
                            ],
                            align=ft.Alignment.TOP_CENTER,
                        ),
                        # Settings Button
                        ft.IconButton(
                            icon=ft.Icons.SETTINGS,
                            tooltip="Settings",
                            on_click=self._open_settings,
                        ),
                    ],
                ),
                self.modules_list,
            ],
        )
        #################

        # Load persisted modules on startup
        self._load_from_store()

        # Start watching for external filesystem changes
        self._store._on_change = self._on_fs_change
        self._store.start_watching()

    # ── lifecycle ──────────────────────────────────────────────────────────

    def did_mount(self):
        self._dialog = SettingsDialog(
            store=self._store,
            on_location_change=self._on_location_change,
        )
        self.page.overlay.append(self._dialog)
        self.page.update()

    def will_unmount(self):
        if hasattr(self, "_dialog") and self._dialog in self.page.overlay:
            self.page.overlay.remove(self._dialog)

    # ── settings ───────────────────────────────────────────────────────────

    def _open_settings(self, e):
        self._dialog.open = True
        self._dialog.update()

    def _on_location_change(self, new_path):
        """Called by SettingsDialog after the user confirms a new path."""
        self._store.stop_watching()
        self._store.root = new_path
        self._store._on_change = self._on_fs_change
        self._store.start_watching()
        self._reload_and_update()

    # ── store helpers ──────────────────────────────────────────────────────

    def _load_from_store(self):
        """Populate the sidebar from whatever is already in UniDocs/."""
        self.modules_list.controls.clear()
        for module in self._store.load_all():
            self.modules_list.controls.append(
                ModuleTile(module, on_select=self._on_module_select)
            )

    def add_module(self, e: ft.ControlEvent):
        title = self.title_field.value.strip()
        if not title:
            return

        _module = Module(
            title=title,
            description=self.description_field.value,
            icon=self.icon_selector.value or ft.Icons.FOLDER,
        )

        self._store.save_module(_module)

        self.modules_list.controls.append(
            ModuleTile(_module, on_select=self._on_module_select)
        )

        self.icon_selector.reset()
        self.title_field.value = ""
        self.description_field.value = ""
        self.update()

    # ── live-sync ──────────────────────────────────────────────────────────

    def _on_fs_change(self):
        try:
            page = self.page
            if page is None:
                return
            page.run_thread_safe(self._reload_and_update)
        except Exception:
            pass

    def _reload_and_update(self):
        self._load_from_store()
        self.update()