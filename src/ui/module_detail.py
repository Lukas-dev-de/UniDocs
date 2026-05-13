import flet as ft
from models.module import Module
from storage.module_store import ModuleStore
from pathlib import Path
import subprocess
import sys


@ft.control
class ModuleDetail(ft.Container):

    def __init__(self, store: ModuleStore):
        super().__init__()

        self._store = store
        self.module: Module | None = None

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
        self.documents_grid = ft.GridView(
            expand=True,
            runs_count=5,
            max_extent=160,
            spacing=8,
            run_spacing=8,
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
                self.title_text,
                self.description_text,
                ft.Divider(color=ft.Colors.WHITE_24),
                self.documents_grid,
            ],
        )


    def set_module(self, module: Module):
        self.module = module
        self.title_text.value = module.title
        self.description_text.value = module.description
        self._refresh_documents()
        self.update()


    def _refresh_documents(self):
        self.documents_grid.controls.clear()
        if self.module is None:
            return
        for doc in self.module.documents:
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