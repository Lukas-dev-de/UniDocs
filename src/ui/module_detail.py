import flet as ft
from models.module import Module
from app_storage.module_store import ModuleStore
from ui.upload_dialog import UploadDialog
from ui.context_menu import ContextMenu
from pathlib import Path
import subprocess
import sys


@ft.control
class ModuleDetail(ft.Container):

    def __init__(self, store: ModuleStore):
        super().__init__()

        self._store = store
        self.module: Module | None = None
        self._list_view = False
        self._sort_asc = True

        # ── Title: text display + inline editor ───────────────────────────
        self.title_text = ft.Text(
            value="No Module Selected",
            size=32,
            weight=ft.FontWeight.BOLD,
        )
        self.title_field = ft.TextField(
            text_size=32,
            border=ft.InputBorder.UNDERLINE,
            expand=True,
            visible=False,
            on_submit=self._commit_title,
            on_blur=self._commit_title,
        )
        self._title_click = ft.GestureDetector(
            content=self.title_text,
            on_tap= self._start_title_edit,
            mouse_cursor=ft.MouseCursor.TEXT,
        )

        # ── Description: text display + inline editor ─────────────────────
        self.description_text = ft.Text(
            value="Select a module to display information. You can create a new module by ",
            size=16,
            color=ft.Colors.WHITE_70,
        )
        self.description_field = ft.TextField(
            text_size=16,
            border=ft.InputBorder.UNDERLINE,
            hint_text="Add a description…",
            expand=True,
            visible=False,
            on_submit=self._commit_description,
            on_blur=self._commit_description,
        )
        self._desc_click = ft.GestureDetector(
            content=self.description_text,
            on_tap=self._start_desc_edit,
            mouse_cursor=ft.MouseCursor.TEXT,
        )

        # ── Toolbar buttons ───────────────────────────────────────────────
        self._sort_toggle = ft.IconButton(
            icon=ft.Icons.SORT_BY_ALPHA,
            tooltip="Sort Z → A",
            on_click=self._toggle_sort,
        )
        self._view_toggle = ft.IconButton(
            icon=ft.Icons.VIEW_LIST,
            tooltip="Switch to list view",
            on_click=self._toggle_view,
        )
        self._upload_btn = ft.FloatingActionButton(
            icon=ft.Icons.UPLOAD_FILE,
            tooltip="Upload documents",
            on_click=self._open_upload,
            bgcolor=ft.Colors.BLUE_700,
            mini=True,
        )

        # ── Upload dialog ─────────────────────────────────────────────────
        self._upload_dialog = UploadDialog(
            store=self._store,
            on_upload=self._on_upload_done,
        )

        # ── Document views ────────────────────────────────────────────────
        self.documents_grid = ft.GridView(
            expand=True,
            runs_count=5,
            max_extent=160,
            spacing=8,
            run_spacing=8,
        )
        self.documents_list = ft.ListView(
            expand=True,
            spacing=4,
            visible=False,
        )

        # ── Styling ───────────────────────────────────────────────────────
        self.border_radius = 16
        self.padding = 16
        self.expand = 19
        self.bgcolor = ft.Colors.GREY_900

        # ── Layout ────────────────────────────────────────────────────────
        self.content = ft.Column(
            spacing=10,
            expand=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Column(
                            spacing=4,
                            expand=True,
                            controls=[
                                # Title row: static text XOR text field
                                ft.Row(controls=[self._title_click, self.title_field]),
                                # Description row: static text XOR text field
                                ft.Row(controls=[self._desc_click, self.description_field]),
                            ],
                        ),
                        ft.Row(
                            spacing=4,
                            controls=[self._sort_toggle, self._view_toggle, self._upload_btn],
                        ),
                    ],
                ),
                ft.Divider(color=ft.Colors.WHITE_24),
                self.documents_grid,
                self.documents_list,
            ],
        )

    # ── lifecycle ──────────────────────────────────────────────────────────

    def did_mount(self):
        self._upload_dialog.attach_to_page(self.page)

        # Floating context menu for documents
        self._ctx_menu = ContextMenu()
        self.page.overlay.append(self._ctx_menu)

        # Document rename dialog
        self._rename_field = ft.TextField(label="New name", expand=True)
        self._rename_confirm_cb = None
        self._rename_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Rename document"),
            content=ft.Container(width=360, content=self._rename_field),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self._close_dialog(self._rename_dialog)),
                ft.FilledButton("Rename", on_click=self._commit_rename),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        # Document delete confirm dialog
        self._delete_label = ft.Text("")
        self._delete_confirm_cb = None
        self._delete_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Delete document"),
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

        for dlg in (self._rename_dialog, self._delete_dialog):
            self.page.overlay.append(dlg)
        self.page.update()

    def will_unmount(self):
        page = self.page
        if page is None:
            return
        for item in [
            self._upload_dialog,
            self._upload_dialog._file_picker,
            self._ctx_menu,
            self._rename_dialog,
            self._delete_dialog,
        ]:
            if item in page.overlay:
                page.overlay.remove(item)

    # ── public ─────────────────────────────────────────────────────────────

    def set_module(self, module: Module):
        self.module = module
        # exit any active inline edit
        self._show_title_text(module.title)
        self._show_desc_text(module.description)
        self._refresh_documents()
        self.update()

    # ── inline title editing ───────────────────────────────────────────────

    async def _start_title_edit(self, e):
        if self.module is None:
            return
        self.title_field.value = self.module.title
        self._title_click.visible = False
        self.title_field.visible = True
        self.update()
        await self.title_field.focus()

    def _commit_title(self, e):
        new_title = (self.title_field.value or "").strip()
        if not new_title or self.module is None:
            self._show_title_text(self.module.title if self.module else "")
            self.update()
            return
        if new_title != self.module.title:
            try:
                self._store.rename_module(self.module, new_title)
            except Exception as ex:
                print(f"Rename failed: {ex}")
        self._show_title_text(self.module.title)
        self.update()

    def _show_title_text(self, value: str):
        self.title_text.value = value
        self._title_click.visible = True
        self.title_field.visible = False

    # ── inline description editing ─────────────────────────────────────────

    async def _start_desc_edit(self, e):
        if self.module is None:
            return
        self.description_field.value = self.module.description
        self._desc_click.visible = False
        self.description_field.visible = True
        self.update()
        await self.description_field.focus()

    def _commit_description(self, e):
        new_desc = (self.description_field.value or "").strip()
        if self.module is None:
            self._show_desc_text("")
            self.update()
            return
        self.module.description = new_desc
        try:
            self._store.save_module(self.module)
        except Exception as ex:
            print(f"Save description failed: {ex}")
        self._show_desc_text(new_desc)
        self.update()

    def _show_desc_text(self, value: str):
        self.description_text.value = value or "Click to add a description…"
        self.description_text.color = ft.Colors.WHITE_70 if value else ft.Colors.WHITE_38
        self._desc_click.visible = True
        self.description_field.visible = False

    # ── toolbar ────────────────────────────────────────────────────────────

    def _toggle_sort(self, e):
        self._sort_asc = not self._sort_asc
        self._sort_toggle.tooltip = "Sort Z → A" if self._sort_asc else "Sort A → Z"
        self._refresh_documents()
        self.update()

    def _toggle_view(self, e):
        self._list_view = not self._list_view
        if self._list_view:
            self._view_toggle.icon = ft.Icons.GRID_VIEW
            self._view_toggle.tooltip = "Switch to grid view"
            self.documents_grid.visible = False
            self.documents_list.visible = True
        else:
            self._view_toggle.icon = ft.Icons.VIEW_LIST
            self._view_toggle.tooltip = "Switch to list view"
            self.documents_grid.visible = True
            self.documents_list.visible = False
        self._refresh_documents()
        self.update()

    def _open_upload(self, e):
        self._upload_dialog.refresh_modules()
        if self.module:
            self._upload_dialog.open_for_module(self.module)
        else:
            self._upload_dialog.open = True
            self._upload_dialog.update()

    # ── upload callback ────────────────────────────────────────────────────

    def _on_upload_done(self, module: Module, docs):
        if self.module and module.title == self.module.title:
            self._reload_current_module()

    def _reload_current_module(self):
        if self.module is None:
            return
        for m in self._store.load_all():
            if m.title == self.module.title:
                self.module = m
                break
        self._refresh_documents()
        self.update()

    # ── document rendering ─────────────────────────────────────────────────

    def _refresh_documents(self):
        self.documents_grid.controls.clear()
        self.documents_list.controls.clear()
        if self.module is None:
            return
        docs = sorted(
            self.module.documents,
            key=lambda d: d.title.lower(),
            reverse=not self._sort_asc,
        )
        for doc in docs:
            if self._list_view:
                self.documents_list.controls.append(self._doc_row(doc))
            else:
                self.documents_grid.controls.append(self._doc_tile(doc))

    def _ext_icon(self, suffix: str) -> str:
        suffix = suffix.lower()
        mapping = {
            ".pdf":  ft.Icons.PICTURE_AS_PDF,
            ".doc":  ft.Icons.DESCRIPTION,
            ".docx": ft.Icons.DESCRIPTION,
            ".ppt":  ft.Icons.SLIDESHOW,
            ".pptx": ft.Icons.SLIDESHOW,
            ".xls":  ft.Icons.TABLE_CHART,
            ".xlsx": ft.Icons.TABLE_CHART,
            ".png":  ft.Icons.IMAGE,
            ".jpg":  ft.Icons.IMAGE,
            ".jpeg": ft.Icons.IMAGE,
            ".gif":  ft.Icons.IMAGE,
            ".mp4":  ft.Icons.VIDEO_FILE,
            ".mp3":  ft.Icons.AUDIO_FILE,
            ".zip":  ft.Icons.FOLDER_ZIP,
            ".py":   ft.Icons.CODE,
            ".txt":  ft.Icons.ARTICLE,
            ".md":   ft.Icons.ARTICLE,
        }
        return mapping.get(suffix, ft.Icons.INSERT_DRIVE_FILE)

    def _doc_tile(self, doc):
        suffix = Path(doc.filepath).suffix
        inner = ft.Container(
            border_radius=10,
            bgcolor=ft.Colors.GREY_800,
            padding=10,
            ink=True,
            on_click=lambda e, path=doc.filepath: self._open_file(path),
            tooltip="Click to open · Right-click for options",
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=6,
                controls=[
                    ft.Icon(self._ext_icon(suffix), size=40, color=ft.Colors.BLUE_200),
                    ft.Text(
                        doc.title,
                        size=12,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        suffix.lstrip(".").upper(),
                        size=10,
                        color=ft.Colors.WHITE_38,
                    ),
                ],
            ),
        )
        return ft.GestureDetector(
            content=inner,
            on_secondary_tap_down=lambda e, d=doc: self._show_doc_menu(e, d),
        )

    def _doc_row(self, doc):
        suffix = Path(doc.filepath).suffix
        inner = ft.Container(
            border_radius=8,
            bgcolor=ft.Colors.GREY_800,
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            ink=True,
            on_click=lambda e, path=doc.filepath: self._open_file(path),
            tooltip="Click to open · Right-click for options",
            content=ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(self._ext_icon(suffix), size=24, color=ft.Colors.BLUE_200),
                    ft.Text(
                        doc.title,
                        size=14,
                        expand=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        suffix.lstrip(".").upper(),
                        size=11,
                        color=ft.Colors.WHITE_38,
                        width=40,
                        text_align=ft.TextAlign.RIGHT,
                    ),
                ],
            ),
        )
        return ft.GestureDetector(
            content=inner,
            on_secondary_tap_down=lambda e, d=doc: self._show_doc_menu(e, d),
        )

    # ── document context menu ──────────────────────────────────────────────

    def _show_doc_menu(self, e: ft.TapEvent, doc):
        self._ctx_menu.show(
            e.global_position.x,
            e.global_position.y,
            [
                ("Rename", ft.Icons.DRIVE_FILE_RENAME_OUTLINE, ft.Colors.WHITE,
                 lambda d=doc: self._doc_rename(d)),
                ("Delete", ft.Icons.DELETE_OUTLINE, ft.Colors.RED_400,
                 lambda d=doc: self._doc_delete(d)),
            ],
        )

    # ── document dialog helpers ────────────────────────────────────────────

    def _close_dialog(self, dlg):
        dlg.open = False
        dlg.update()

    def _doc_rename(self, doc):
        self._rename_field.value = doc.title
        self._rename_field.error_text = ""
        self._rename_confirm_cb = lambda new_name, d=doc: self._apply_doc_rename(d, new_name)
        self._rename_dialog.open = True
        self._rename_dialog.update()

    def _commit_rename(self, e):
        new_name = (self._rename_field.value or "").strip()
        if not new_name:
            self._rename_field.error_text = "Name cannot be empty."
            self._rename_dialog.update()
            return
        self._close_dialog(self._rename_dialog)
        if self._rename_confirm_cb:
            self._rename_confirm_cb(new_name)

    def _apply_doc_rename(self, doc, new_name: str):
        try:
            self._store.rename_document(doc, new_name)
        except Exception as ex:
            print(f"Rename failed: {ex}")
        self._reload_current_module()

    def _doc_delete(self, doc):
        self._delete_label.value = f'Delete "{doc.title}"? This cannot be undone.'
        self._delete_confirm_cb = lambda d=doc: self._apply_doc_delete(d)
        self._delete_dialog.open = True
        self._delete_dialog.update()

    def _commit_delete(self, e):
        self._close_dialog(self._delete_dialog)
        if self._delete_confirm_cb:
            self._delete_confirm_cb()

    def _apply_doc_delete(self, doc):
        try:
            self._store.delete_document(self.module, doc)
        except Exception as ex:
            print(f"Delete failed: {ex}")
        self._reload_current_module()

    # ── file opener ────────────────────────────────────────────────────────

    def _open_file(self, filepath: str):
        try:
            if sys.platform == "win32":
                import os
                os.startfile(filepath)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", filepath])
            else:
                subprocess.Popen(["xdg-open", filepath])
        except Exception as ex:
            print(f"Could not open {filepath}: {ex}")