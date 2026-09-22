import flet as ft
from ui.components.module_tile import ModuleTile
from ui.components.icon_selector import IconSelector
from ui.components.color_selector import ColorSelector
from ui.components.module_edit_dialog import ModuleEditDialog
from ui.settings_dialog import SettingsDialog
from ui.context_menu import ContextMenu
from models.module import Module
from app_storage.module_store import ModuleStore
from ui.theme import ThemeManager


@ft.control
class ModuleSidebar(ft.Container):
    padding: int = 8
    border_radius: int = 16
    bgcolor: ft.Colors = ft.Colors.SURFACE

    def __init__(
        self,
        store: ModuleStore,
        on_module_select=None,
        on_module_update=None,
        theme: ThemeManager | None = None,
    ):
        super().__init__()
        self._store = store
        self._on_module_select = on_module_select
        self._on_module_update = on_module_update
        self._theme = theme

        self.modules_list = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)

        self.icon_selector = IconSelector()
        self.color_selector = ColorSelector()
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
                ft.PopupMenuButton(
                    icon=ft.Icons.ADD_BOX,
                    tooltip="Add Module",
                    items=[
                        ft.PopupMenuItem(
                            content=ft.Row(
                                controls=[
                                    self.icon_selector,
                                    self.color_selector,
                                    self.title_field,
                                ]
                            ),
                            padding=8,
                        ),
                        ft.PopupMenuItem(
                            content=self.description_field, padding=8
                        ),
                    ],
                    align=ft.Alignment.TOP_CENTER,
                ),
                self.modules_list,
                ft.IconButton(
                    icon=ft.Icons.SETTINGS,
                    tooltip="Settings",
                    on_click=self._open_settings,
                ),
            ],
        )

        self._load_from_store()
        self._store._on_change = self._on_fs_change
        self._store.start_watching()

    #  lifecycle 

    def did_mount(self):
        self._settings_dialog = SettingsDialog(
            store=self._store,
            theme=self._theme,
            on_location_change=self._on_location_change,
        )

        self._ctx_menu = ContextMenu()
        self._edit_dialog = ModuleEditDialog(
            store=self._store,
            on_saved=self._on_module_edited,
        )

        # Delete confirm dialog
        self._delete_label = ft.Text("")
        self._delete_confirm_cb = None
        self._delete_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Delete Module"),
            content=self._delete_label,
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self._close_dialog(self._delete_dialog)),
                ft.FilledButton(
                    "Delete",
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.ERROR,
                        color=ft.Colors.ON_ERROR,
                    ),
                    on_click=self._commit_delete,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        for item in (self._settings_dialog, self._ctx_menu, self._delete_dialog, self._edit_dialog):
            self.page.overlay.append(item)
        self.page.update()

    def will_unmount(self):
        page = self.page
        if page is None:
            return
        for item in (self._settings_dialog, self._ctx_menu, self._delete_dialog, self._edit_dialog):
            if hasattr(self, "_settings_dialog") and item in page.overlay:
                page.overlay.remove(item)

    #  settings 

    def _open_settings(self, e):
        self._settings_dialog.show()

    def _on_location_change(self, new_path):
        self._store.stop_watching()
        self._store.root = new_path
        self._store._on_change = self._on_fs_change
        self._store.start_watching()
        self._reload_and_update()

    #  store helpers 

    def _load_from_store(self):
        self.modules_list.controls.clear()
        for module in self._store.load_all():
            self.modules_list.controls.append(self._make_tile(module))

    def _make_tile(self, module: Module):
        tile = ModuleTile(module, on_select=self._on_module_select)
        return ft.GestureDetector(
            content=tile,
            on_secondary_tap_down=lambda e, m=module: self._show_module_menu(e, m),
        )

    def add_module(self, e: ft.ControlEvent):
        title = self.title_field.value.strip()
        if not title:
            return

        _module = Module(
            title=title,
            description=self.description_field.value,
            icon=self.icon_selector.value or ft.Icons.FOLDER,
            color=self.color_selector.value,
        )

        self._store.save_module(_module)
        self.modules_list.controls.append(self._make_tile(_module))

        self.icon_selector.reset()
        self.color_selector.reset()
        self.title_field.value = ""
        self.description_field.value = ""
        self.update()

    #  context menu 

    def _show_module_menu(self, e: ft.TapEvent, module: Module):
        self._ctx_menu.show(
            e.global_position.x,
            e.global_position.y,
            [
                ("Edit", ft.Icons.EDIT_OUTLINED, ft.Colors.ON_SURFACE, lambda m=module: self._module_edit(m)),
                ("Delete", ft.Icons.DELETE_OUTLINE, ft.Colors.ERROR, lambda m=module: self._module_delete(m)),
            ],
        )

    #  dialog helpers 

    def _close_dialog(self, dlg):
        dlg.open = False
        dlg.update()

    def _open_delete_dialog(self, label: str, on_confirm):
        self._delete_label.value = label
        self._delete_confirm_cb = on_confirm
        self._delete_dialog.open = True
        self._delete_dialog.update()

    def _commit_delete(self, e):
        self._close_dialog(self._delete_dialog)
        if self._delete_confirm_cb:
            self._delete_confirm_cb()

    #  module actions 

    def _module_edit(self, module: Module):
        self._edit_dialog.open_for(module)

    def _on_module_edited(self, module: Module, previous_title: str | None):
        """Re-render the sidebar, and let the detail view refresh itself.

        ``previous_title`` is what the module was called before the edit, so
        the detail view can tell whether *it* was the module being edited.
        """
        self._reload_and_update()
        if self._on_module_update:
            self._on_module_update(module, previous_title)

    def _module_delete(self, module: Module):
        def on_confirm():
            try:
                self._store.delete_module(module)
            except Exception as ex:
                print(f"Delete failed: {ex}")
            self._reload_and_update()
        self._open_delete_dialog(
            f'Delete "{module.title}" and all its documents? This cannot be undone.',
            on_confirm,
        )

    #  live-sync 

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

