import flet as ft
from models.module import Module
from storage.module_store import ModuleStore
from ui.upload_dialog import UploadDialog
from pathlib import Path
import subprocess
import sys


@ft.control
class ModuleDetail(ft.Container):

    def __init__(self, store: ModuleStore):
        super().__init__()

        self._store = store
        self.module: Module | None = None
        self._list_view = False  # False = grid, True = list

        # UI elements
        self.title_text = ft.Text(
            value="No Module Selected",
            size=32,
            weight=ft.FontWeight.BOLD,
        )
        self.description_text = ft.Text(
            value="Select a module to display information.",
            size=16,
            color=ft.Colors.WHITE_70,
        )

        # Grid view
        self.documents_grid = ft.GridView(
            expand=True,
            runs_count=5,
            max_extent=160,
            spacing=8,
            run_spacing=8,
        )

        # List view
        self.documents_list = ft.ListView(
            expand=True,
            spacing=4,
            visible=False,
        )

        # Toggle button
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

        # Upload dialog (registered on page in did_mount)
        self._upload_dialog = UploadDialog(
            store=self._store,
            on_upload=self._on_upload_done,
        )

        # Styling
        self.border_radius = 16
        self.padding = 16
        self.expand = 19
        self.bgcolor = ft.Colors.GREY_900

        # Content
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
                            controls=[self.title_text, self.description_text],
                        ),
                        ft.Row(
                            spacing=4,
                            controls=[self._view_toggle, self._upload_btn],
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

    def will_unmount(self):
        page = self.page
        if page is None:
            return
        for item in [self._upload_dialog, self._upload_dialog._file_picker]:
            if item in page.overlay:
                page.overlay.remove(item)

    # ── public ─────────────────────────────────────────────────────────────

    def set_module(self, module: Module):
        self.module = module
        self.title_text.value = module.title
        self.description_text.value = module.description
        self._refresh_documents()
        self.update()

    # ── private ────────────────────────────────────────────────────────────

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

    def _on_upload_done(self, module: Module, docs):
        """Refresh the view if the upload was for the currently shown module."""
        if self.module and module.title == self.module.title:
            self._reload_current_module()

    def _reload_current_module(self):
        """Re-read the current module from disk and refresh the document view."""
        if self.module is None:
            return
        for m in self._store.load_all():
            if m.title == self.module.title:
                self.module = m
                break
        self._refresh_documents()
        self.update()

    def _refresh_documents(self):
        self.documents_grid.controls.clear()
        self.documents_list.controls.clear()
        if self.module is None:
            return
        for doc in self.module.documents:
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
        return ft.Container(
            border_radius=10,
            bgcolor=ft.Colors.GREY_800,
            padding=10,
            ink=True,
            on_click=lambda e, path=doc.filepath: self._open_file(path),
            tooltip=doc.title,
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

    def _doc_row(self, doc):
        suffix = Path(doc.filepath).suffix
        return ft.Container(
            border_radius=8,
            bgcolor=ft.Colors.GREY_800,
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            ink=True,
            on_click=lambda e, path=doc.filepath: self._open_file(path),
            tooltip=doc.title,
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