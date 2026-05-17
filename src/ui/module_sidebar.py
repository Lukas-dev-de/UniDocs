import flet as ft
from ui.components.module_tile import ModuleTile
from ui.components.icon_selector import IconSelector
from ui.settings_dialog import SettingsDialog
from ui.context_menu import ContextMenu
from models.module import Module
from storage.module_store import ModuleStore


@ft.control
class ModuleSidebar(ft.Container):
    #expand: int = 1
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
                ft.Column(
                    alignment="CENTER",
                    controls=[
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

        self._load_from_store()
        self._store._on_change = self._on_fs_change
        self._store.start_watching()

    # ── lifecycle ──────────────────────────────────────────────────────────

    def did_mount(self):
        self._settings_dialog = SettingsDialog(
            store=self._store,
            on_location_change=self._on_location_change,
        )

        self._ctx_menu = ContextMenu()

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
                    style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700),
                    on_click=self._commit_delete,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        for item in (self._settings_dialog, self._ctx_menu, self._delete_dialog):
            self.page.overlay.append(item)
        self.page.update()

    def will_unmount(self):
        page = self.page
        if page is None:
            return
        for item in (self._settings_dialog, self._ctx_menu, self._delete_dialog):
            if hasattr(self, "_settings_dialog") and item in page.overlay:
                page.overlay.remove(item)

    # ── settings ───────────────────────────────────────────────────────────

    def _open_settings(self, e):
        self._settings_dialog.open = True
        self._settings_dialog.update()

    def _on_location_change(self, new_path):
        self._store.stop_watching()
        self._store.root = new_path
        self._store._on_change = self._on_fs_change
        self._store.start_watching()
        self._reload_and_update()

    # ── store helpers ──────────────────────────────────────────────────────

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
        )

        self._store.save_module(_module)
        self.modules_list.controls.append(self._make_tile(_module))

        self.icon_selector.reset()
        self.title_field.value = ""
        self.description_field.value = ""
        self.update()

    # ── context menu ───────────────────────────────────────────────────────

    def _show_module_menu(self, e: ft.TapEvent, module: Module):
        self._ctx_menu.show(
            e.global_position.x,
            e.global_position.y,
            [
                ("Delete", ft.Icons.DELETE_OUTLINE, ft.Colors.RED_400, lambda m=module: self._module_delete(m)),
            ],
        )

    # ── dialog helpers ─────────────────────────────────────────────────────

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

    # ── module actions ─────────────────────────────────────────────────────

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


# ── Floating context menu (shared helper) ──────────────────────────────────────

class _ContextMenu(ft.Container):
    """
    Lightweight floating context menu rendered in page.overlay.
    Positioned at cursor coordinates on secondary tap.
    """

    def __init__(self):
        super().__init__()
        self._items_col = ft.Column(spacing=0, tight=True)
        self.visible = False
        self.left = 0
        self.top = 0
        self.bgcolor = ft.Colors.GREY_850
        self.border_radius = 8
        self.border = ft.Border.all(1, ft.Colors.OUTLINE_VARIANT)
        self.shadow = ft.BoxShadow(blur_radius=12, color=ft.Colors.BLACK54)
        self.padding = ft.Padding.symmetric(vertical=4)
        self.content = self._items_col
        self.z_index = 9999

    def show(self, x: float, y: float, items: list[tuple]):
        """items: list of (label, icon, color, callback)."""
        self._items_col.controls.clear()
        for label, icon, color, cb in items:
            self._items_col.controls.append(
                ft.TextButton(
                    content=ft.Row(
                        spacing=10,
                        controls=[
                            ft.Icon(icon, size=16, color=color),
                            ft.Text(label, color=color, size=13),
                        ],
                    ),
                    style=ft.ButtonStyle(
                        padding=ft.Padding.symmetric(horizontal=14, vertical=6),
                        shape=ft.RoundedRectangleBorder(radius=0),
                        overlay_color=ft.Colors.WHITE10,
                    ),
                    on_click=lambda e, fn=cb: self._select(fn),
                )
            )
        self.left = x
        self.top = y
        self.visible = True
        self.update()

    def hide(self):
        self.visible = False
        self.update()

    def _select(self, cb):
        self.hide()
        cb()