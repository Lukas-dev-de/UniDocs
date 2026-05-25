"""
ui/import_dialog.py
-------------------
A dialog for importing files into an existing module.

Usage
-----
    dialog = ImportDialog(store=store, on_import=callback)
    page.overlay.append(dialog)
    dialog.open_for_module(module)   # pre-selects a module
    # or
    dialog.open = True               # user picks the module from dropdown
    page.update()

Callbacks
---------
    on_import(module, [Document, ...])
        Fired after files have been copied into the module folder.
        Documents are passed with their final (possibly renamed) titles
        and filepaths already updated on disk.
"""

from __future__ import annotations

from pathlib import Path

import flet as ft

from models.module import Module
from app_storage.module_store import ModuleStore


class ImportDialog(ft.AlertDialog):

    def __init__(self, store: ModuleStore, on_import=None):
        super().__init__()
        self._store = store
        self._on_import = on_import

        #  state 
        self._picked_files: list[ft.FilePickerResultFile] = []
        self._selected_module: Module | None = None
        # original filename → display name (stem only, or full name typed by user)
        self._display_names: dict[str, str] = {}

        #  module dropdown 
        self._module_dropdown = ft.Dropdown(
            label="Target module",
            hint_text="Select a module…",
            expand=True,
            on_select=self._on_module_changed,
        )

        #  file list display 
        self._file_list = ft.Column(spacing=4, tight=True)

        self._no_files_text = ft.Text(
            "No files selected.",
            size=12,
            color=ft.Colors.WHITE_38,
            italic=True,
        )

        self._status = ft.Text("", color=ft.Colors.RED_400, size=12)

        #  layout 
        self.modal = True
        self.title = ft.Row(
            spacing=8,
            controls=[
                ft.Icon(ft.Icons.UPLOAD_FILE, size=20),
                ft.Text("Import Documents", size=18, weight=ft.FontWeight.BOLD),
            ],
        )

        self.content = ft.Container(
            width=520,
            content=ft.Column(
                tight=True,
                spacing=16,
                controls=[
                    self._module_dropdown,
                    ft.Button(
                        "Choose files…",
                        icon=ft.Icons.FOLDER_OPEN,
                        on_click=self._pick_files,
                    ),
                    ft.Container(
                        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                        border_radius=8,
                        padding=10,
                        content=ft.Column(
                            tight=True,
                            spacing=4,
                            controls=[self._file_list, self._no_files_text],
                        ),
                    ),
                    self._status,
                ],
            ),
        )

        self.actions = [
            ft.TextButton("Cancel", on_click=self._cancel),
            ft.FilledButton("Import", icon=ft.Icons.UPLOAD, on_click=self._import),
        ]
        self.actions_alignment = ft.MainAxisAlignment.END

        self.on_dismiss = self._reset_state

    #  public API 

    def open_for_module(self, module: Module):
        """Open the dialog with *module* pre-selected in the dropdown."""
        self._refresh_dropdown()
        self._select_module(module)
        self.open = True
        self.update()

    def refresh_modules(self):
        """Call this after modules are added/removed to keep the dropdown fresh."""
        self._refresh_dropdown()

    #  lifecycle (called by ModuleDetail.did_mount) 

    def attach_to_page(self, page: ft.Page):
        if self not in page.overlay:
            page.overlay.append(self)
        page.update()

    #  private 

    def _refresh_dropdown(self):
        modules = self._store.load_all()
        self._module_dropdown.options = [
            ft.dropdown.Option(key=m.title, text=m.title) for m in modules
        ]
        if self._selected_module:
            titles = {m.title for m in modules}
            if self._selected_module.title not in titles:
                self._selected_module = None
                self._module_dropdown.value = None

    def _select_module(self, module: Module):
        self._selected_module = module
        self._module_dropdown.value = module.title

    def _on_module_changed(self, e):
        title = self._module_dropdown.value
        if not title:
            self._selected_module = None
            return
        for m in self._store.load_all():
            if m.title == title:
                self._selected_module = m
                break

    #  file list 

    def _rebuild_file_list(self):
        self._file_list.controls.clear()
        if not self._picked_files:
            self._no_files_text.visible = True
            return
        self._no_files_text.visible = False
        for f in self._picked_files:
            display = self._display_names.get(f.name, Path(f.name).stem)

            #  name label (click -> inline edit) 
            name_label = ft.Text(display, size=12, expand=True)

            name_field = ft.TextField(
                value=display,
                expand=True,
                text_size=12,
                height=32,
                content_padding=ft.Padding.symmetric(horizontal=6, vertical=0),
                visible=False,
                on_submit=lambda ev, file=f, lbl=name_label: (
                    self._commit_rename(file, ev.control, lbl)
                ),
                on_blur=lambda ev, file=f, lbl=name_label: (
                    self._commit_rename(file, ev.control, lbl)
                ),
            )

            name_click = ft.GestureDetector(
                content=name_label,
                on_tap=lambda ev, file=f, lbl=name_label, fld=name_field: (
                    self.page.run_task(self._start_rename, file, lbl, fld)
                ),
                mouse_cursor=ft.MouseCursor.TEXT,
            )

            # store controls on the file object for easy cross-reference
            f._name_label = name_label
            f._name_click = name_click
            f._name_field = name_field

            self._file_list.controls.append(
                ft.Row(
                    spacing=6,
                    controls=[
                        ft.Icon(
                            ft.Icons.INSERT_DRIVE_FILE,
                            size=16,
                            color=ft.Colors.BLUE_200,
                        ),
                        ft.Stack(
                            expand=True,
                            controls=[name_click, name_field],
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            icon_size=14,
                            tooltip="Remove",
                            on_click=lambda ev, file=f: self._remove_file(file),
                        ),
                    ],
                )
            )

    async def _start_rename(
        self,
        file: ft.FilePickerResultFile,
        label: ft.Text,
        field: ft.TextField,
    ):
        """Switch a file row from label view to inline TextField."""
        field.value = label.value
        file._name_click.visible = False
        field.visible = True
        self.update()
        await field.focus()

    def _commit_rename(
        self,
        file: ft.FilePickerResultFile,
        field: ft.TextField,
        label: ft.Text,
    ):
        """Commit the inline rename and switch back to label view."""
        new_name = (field.value or "").strip()
        if not new_name:
            # revert to whatever was stored (or original filename)
            new_name = self._display_names.get(file.name, file.name)

        self._display_names[file.name] = new_name
        label.value = new_name

        field.visible = False
        file._name_click.visible = True
        self.update()

    #  file picking / removal 

    async def _pick_files(self, e):
        files = await ft.FilePicker().pick_files(allow_multiple=True)
        if files:
            self._picked_files.extend(files)
        self._rebuild_file_list()
        self.update()

    def _remove_file(self, file: ft.FilePickerResultFile):
        self._picked_files = [f for f in self._picked_files if f.name != file.name]
        self._display_names.pop(file.name, None)
        self._rebuild_file_list()
        self.update()

    #  import 

    def _import(self, e):
        if not self._selected_module:
            self._show_error("Please select a module.")
            return
        if not self._picked_files:
            self._show_error("Please choose at least one file.")
            return

        added_docs = []
        errors = []

        for f in self._picked_files:
            display_name = self._display_names.get(f.name, f.name)

            # rename_document takes a stem only; strip extension if the user
            # happened to type one (e.g. "my notes.pdf" -> "my notes")
            display_stem = (
                Path(display_name).stem
                if "." in display_name
                else display_name
            )

            try:
                # 1. copy file into module folder under its original name
                doc = self._store.add_document(
                    self._selected_module, Path(f.path)
                )

                # 2. rename on disk if the user changed the name
                if display_stem != doc.title:
                    self._store.rename_document(doc, display_stem)

                added_docs.append(doc)

            except Exception as ex:
                errors.append(f"{display_name}: {ex}")

        if errors:
            self._show_error("\n".join(errors))
            return

        # success
        self.open = False
        self._reset_state(None)
        self.update()

        if self._on_import:
            self._on_import(self._selected_module, added_docs)

    #  cancel / reset 

    def _cancel(self, e):
        self.open = False
        self._reset_state(None)
        self.update()

    def _reset_state(self, e):
        self._picked_files = []
        self._display_names = {}
        self._rebuild_file_list()
        self._status.value = ""

    def _show_error(self, msg: str):
        self._status.value = msg
        self.update()