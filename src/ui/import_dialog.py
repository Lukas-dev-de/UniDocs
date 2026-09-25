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
from models.document import Document
from models.tag import Tag
from app_storage.module_store import ModuleStore
from ui.components.tag_dialog import TagDialog


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
        # original filenames of currently selected rows
        self._selected_files: set[str] = set()
        # original filename → set of tag IDs to apply on import
        self._file_tags: dict[str, set[str]] = {}

        #  module dropdown (fills the width via the column's STRETCH) 
        self._module_dropdown = ft.Dropdown(
            label="Target module",
            hint_text="Select a module…",
            on_select=self._on_module_changed,
        )

        #  file list display 
        self._no_files_text = ft.Text(
            "No files selected.",
            size=12,
            color=ft.Colors.OUTLINE,
            italic=True,
        )

        self._file_list = ft.Column(spacing=4, tight=True)

        self._file_list_container = ft.Container(
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
            padding=10,
            height=48,
            content=ft.Column(
                spacing=4,
                scroll=ft.ScrollMode.AUTO,
                controls=[self._file_list, self._no_files_text],
            ),
        )

        self._status = ft.Text("", color=ft.Colors.ERROR, size=12)

        #  tag assignment (for the selected rows) 
        self._tag_button = ft.Button(
            "Tags for selected…",
            icon=ft.Icons.LABEL_OUTLINE,
            on_click=self._open_tag_panel,
            disabled=True,
        )
        # reuse the "Manage Tags" dialog; its Save hands the staged documents
        # back instead of touching the disk (docs do not exist yet)
        self._tag_dialog = TagDialog(
            store=self._store, save_handler=self._apply_staged_tags
        )

        #  layout 
        self.modal = True
        # hug the content and sit at the top of the window, not in the middle
        self.alignment = ft.Alignment.TOP_CENTER
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
                # keep the fields packed: the dialog hugs its content
                tight=True,
                alignment=ft.MainAxisAlignment.START,
                spacing=16,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    self._module_dropdown,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.START,
                        controls=[
                            ft.Button(
                                "Choose files…",
                                icon=ft.Icons.FOLDER_OPEN,
                                on_click=self._pick_files,
                            ),
                            self._tag_button,
                        ],
                    ),
                    self._file_list_container,
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
        self._tag_button.disabled = not self._selected_files
        if not self._picked_files:
            self._no_files_text.visible = True
            self._resize_file_list_container(0)
            return
        self._no_files_text.visible = False
        self._resize_file_list_container(len(self._picked_files))
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

            selected = f.name in self._selected_files

            # clicking anywhere on the row (icon, empty space) selects it;
            # the name has its own gesture detector so a tap there renames
            row = ft.Container(
                border_radius=6,
                padding=ft.Padding.symmetric(horizontal=4, vertical=2),
                bgcolor=(
                    ft.Colors.with_opacity(0.16, ft.Colors.PRIMARY)
                    if selected
                    else None
                ),
                on_click=lambda ev, file=f: self._toggle_selection(file),
                content=ft.Row(
                    spacing=6,
                    controls=[
                        ft.Icon(
                            ft.Icons.INSERT_DRIVE_FILE,
                            size=16,
                            color=ft.Colors.PRIMARY,
                        ),
                        ft.Stack(
                            expand=True,
                            controls=[name_click, name_field],
                        ),
                        self._tag_dots(f.name),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            icon_size=14,
                            tooltip="Remove",
                            on_click=lambda ev, file=f: self._remove_file(file),
                        ),
                    ],
                ),
            )

            self._file_list.controls.append(row)

    _FILE_ROW_HEIGHT = 44   # one row incl. spacing
    _FILE_LIST_MAX_HEIGHT = 420   # beyond that the list scrolls

    def _resize_file_list_container(self, rows: int):
        """Grow with the rows, but stop at a max height (then it scrolls)."""
        needed = 16 + rows * self._FILE_ROW_HEIGHT if rows else 40
        self._file_list_container.height = min(needed, self._FILE_LIST_MAX_HEIGHT)

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

    #  tag assignment for the selected rows 

    def _selected_file_names(self) -> list[str]:
        return [f.name for f in self._picked_files if f.name in self._selected_files]

    def _tag_dots(self, filename: str) -> ft.Control:
        """Tiny colour dots showing the tags staged for one file."""
        tag_ids = self._file_tags.get(filename, set())
        if not tag_ids:
            return ft.Container(width=0, height=0)
        by_id = {t["id"]: t for t in self._store.load_all_tags()}
        return ft.Row(
            spacing=3,
            tight=True,
            controls=[
                ft.Container(
                    width=9,
                    height=9,
                    border_radius=5,
                    bgcolor=by_id[tid]["color"],
                    tooltip=by_id[tid]["name"],
                )
                for tid in tag_ids
                if tid in by_id
            ],
        )

    def _open_tag_panel(self, e):
        if not self._selected_module:
            self._show_error("Select a target module first.")
            return
        names = self._selected_file_names()
        if not names:
            self._show_error("Select at least one document first.")
            return
        self._status.value = ""

        by_id = {t["id"]: t for t in self._store.load_all_tags()}
        docs = []
        for f in self._picked_files:
            if f.name not in self._selected_files:
                continue
            staged = self._file_tags.get(f.name, set())
            tags = [
                Tag(tid, by_id[tid]["name"], by_id[tid]["color"])
                for tid in staged
                if tid in by_id
            ]
            # filepath carries the original filename, so _apply_staged_tags can
            # map the dialog's documents back onto the staged files
            docs.append(
                Document(
                    title=Path(f.name).stem,
                    description="",
                    filepath=f.name,
                    tags=tags,
                )
            )

        if self._tag_dialog not in self.page.overlay:
            self.page.overlay.append(self._tag_dialog)
            # appending to the overlay only wires the parent up on page.update(),
            # so the dialog has no .page yet -> flush once before opening it
            self.page.update()
        self._tag_dialog.open_for_documents(docs, self._selected_module)

    def _apply_staged_tags(self, docs: list[Document]):
        """Callback from the Manage Tags popup: write the chosen tags back."""
        for doc in docs:
            self._file_tags[doc.filepath] = {t.id for t in doc.tags}
        self._rebuild_file_list()
        self.update()

    #  file picking / removal 

    async def _pick_files(self, e):
        files = await ft.FilePicker().pick_files(allow_multiple=True)
        if files:
            self._picked_files.extend(files)
        self._rebuild_file_list()
        self.update()

    def _toggle_selection(self, file: ft.FilePickerResultFile):
        if file.name in self._selected_files:
            self._selected_files.discard(file.name)
        else:
            self._selected_files.add(file.name)
        self._rebuild_file_list()
        self.update()

    def _remove_file(self, file: ft.FilePickerResultFile):
        self._picked_files = [f for f in self._picked_files if f.name != file.name]
        self._display_names.pop(file.name, None)
        self._selected_files.discard(file.name)
        self._file_tags.pop(file.name, None)
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

            # strip name extension
            display_stem = (
                Path(display_name).stem
                if "." in display_name
                else display_name
            )

            try:
                # copy file into module folder under its original name
                doc = self._store.add_document(
                    self._selected_module, Path(f.path)
                )

                # rename on disk if name changed 
                if display_stem != doc.title:
                    self._store.rename_document(doc, display_stem)

                # apply the tags staged for this file
                tag_ids = self._file_tags.get(f.name)
                if tag_ids:
                    self._store.save_doc_tags(
                        self._selected_module, doc, list(tag_ids)
                    )
                    tag_map = {t["id"]: t for t in self._store.load_all_tags()}
                    doc.tags = [
                        Tag(tid, tag_map[tid]["name"], tag_map[tid]["color"])
                        for tid in tag_ids
                        if tid in tag_map
                    ]

                added_docs.append(doc)

            except Exception as ex:
                errors.append(f"{display_name}: {ex}")

        if errors:
            self._show_error("\n".join(errors))
            return

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
        self._selected_files = set()
        self._file_tags = {}
        self._rebuild_file_list()
        self._status.value = ""

    def _show_error(self, msg: str):
        self._status.value = msg
        self.update()