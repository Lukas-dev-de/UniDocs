import flet as ft
from app_storage.module_store import ModuleStore
from ui.components.dialogs import ConfirmDialog
from ui.components.tag_dialog import TagDialog
from ui.components.tag_colors import TAG_PALETTE
from ui.context_menu import ContextMenu

class TagManager:
    """Helper class to encapsulate tag management logic."""
    def __init__(self, page: ft.Page, store: ModuleStore, on_changed):
        self.page = page
        self.store = store
        self.on_changed = on_changed

        self.menu = ContextMenu()
        self.tag_dialog = TagDialog(store=store, on_changed=on_changed)

        self.rename_field = ft.TextField(label="New tag name", expand=True)
        self.rename_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Rename tag"),
            content=ft.Container(width=360, content=self.rename_field),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self._close_dialog(self.rename_dialog)),
                ft.FilledButton("Rename", on_click=self._commit_tag_rename),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.color_target: str | None = None
        self.color_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Change tag color"),
            content=ft.Container(
                width=320,
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[self._build_color_grid()],
                ),
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self._close_dialog(self.color_dialog)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.rename_old: str | None = None
        
        self.page.overlay.extend([self.menu, self.tag_dialog, self.rename_dialog, self.color_dialog])

    def show_menu(self, e: ft.TapEvent, tag_id: str):
        tag_dict = self.store.get_tag_by_id(tag_id) or {}
        tag_name = tag_dict.get("name", tag_id)
        self.menu.show(
            e.global_position.x,
            e.global_position.y,
            [
                ("Change Color", ft.Icons.PALETTE_OUTLINED, ft.Colors.ON_SURFACE,
                 lambda tid=tag_id: self._start_change_color(tid)),
                ("Rename", ft.Icons.DRIVE_FILE_RENAME_OUTLINE, ft.Colors.ON_SURFACE,
                 lambda tid=tag_id, n=tag_name: self._start_rename(tid, n)),
                ("Delete", ft.Icons.DELETE_OUTLINE, ft.Colors.ERROR,
                 lambda tid=tag_id, n=tag_name: self._start_delete(tid, n)),
            ],
        )

    def _build_color_grid(self) -> ft.Row:
        return ft.Row(
            wrap=True,
            spacing=8,
            run_spacing=8,
            controls=[
                ft.Container(
                    width=30,
                    height=30,
                    border_radius=6,
                    bgcolor=hex_color,
                    tooltip=label,
                    ink=True,
                    on_click=lambda e, c=hex_color: self._commit_tag_color(c),
                )
                for hex_color, label in TAG_PALETTE
            ],
        )

    def _start_change_color(self, tag_id: str):
        tag_dict = self.store.get_tag_by_id(tag_id) or {}
        tag_name = tag_dict.get("name", tag_id)
        self.color_target = tag_id
        self.color_dialog.title = ft.Text(f'Color for "{tag_name}"')
        self.color_dialog.open = True
        self.color_dialog.update()

    def _commit_tag_color(self, hex_color: str):
        self._close_dialog(self.color_dialog)
        if not self.color_target: return
        self.store.set_tag_color(self.color_target, hex_color)
        self.on_changed()

    def _start_rename(self, tag_id: str, current_name: str):
        self.rename_old = tag_id
        self.rename_field.value = current_name
        self.rename_field.error_text = ""
        self.rename_dialog.open = True
        self.rename_dialog.update()

    def _commit_tag_rename(self, e):
        new_name = (self.rename_field.value or "").strip()
        if not new_name:
            self.rename_field.error_text = "Name cannot be empty."
            self.rename_dialog.update()
            return
        
        current_tag = self.store.get_tag_by_id(self.rename_old) or {}
        if new_name != current_tag.get("name") and new_name in self.store.load_tag_names():
            self.rename_field.error_text = f'"{new_name}" already exists.'
            self.rename_dialog.update()
            return
            
        self._close_dialog(self.rename_dialog)
        self.store.rename_global_tag(self.rename_old, new_name)
        self.on_changed()

    def _start_delete(self, tag_id: str, tag_name: str):
        def on_confirm():
            self.store.remove_global_tag(tag_id)
            self.on_changed()

        dlg = ConfirmDialog(
            "Delete tag",
            f'Delete tag "{tag_name}"? It will be removed from all documents.',
            on_confirm
        )
        self.page.overlay.append(dlg)
        self.page.update()
        dlg.open = True
        dlg.update()

    def _close_dialog(self, dlg):
        dlg.open = False
        dlg.update()

    def cleanup(self):
        for item in [self.menu, self.tag_dialog, self.rename_dialog, self.color_dialog]:
            if item in self.page.overlay:
                self.page.overlay.remove(item)
