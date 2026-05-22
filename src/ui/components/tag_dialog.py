"""
ui/components/tag_dialog.py
---------------------------
Dialog for assigning and creating tags on a Document.

Usage
-----
    dialog = TagDialog(store=store)
    page.overlay.append(dialog)

    dialog.open_for_document(doc, module)
"""

from __future__ import annotations

import flet as ft

from models.document import Document
from models.module import Module
from app_storage.module_store import ModuleStore


class TagDialog(ft.AlertDialog):
    """
    Shows all global tags as toggleable chips.
    Lets the user create new tags inline.
    Saves assignments back via ModuleStore on confirm.
    """

    def __init__(self, store: ModuleStore, on_changed=None):
        super().__init__()
        self._store = store
        self._on_changed = on_changed   # called after tags are saved

        self._doc: Document | None = None
        self._module: Module | None = None
        self._selected: set[str] = set()

        # --- widgets ---
        self._chips_row = ft.Row(wrap=True, spacing=8, run_spacing=8)

        self._new_tag_field = ft.TextField(
            hint_text="New tag name…",
            expand=True,
            dense=True,
            on_submit=self._add_new_tag,
        )

        self._status = ft.Text("", color=ft.Colors.RED_400, size=12)

        # --- layout ---
        self.modal = True
        self.title = ft.Row(
            spacing=8,
            controls=[
                ft.Icon(ft.Icons.LABEL_OUTLINE, size=20),
                ft.Text("Manage Tags", size=18, weight=ft.FontWeight.BOLD),
            ],
        )
        self.content = ft.Container(
            width=480,
            content=ft.Column(
                tight=True,
                spacing=16,
                controls=[
                    ft.Text(
                        "Toggle tags for this document. Create new global tags below.",
                        size=13,
                        color=ft.Colors.WHITE_70,
                    ),
                    # tag chips
                    ft.Container(
                        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                        border_radius=8,
                        padding=12,
                        #min_height=60,
                        content=self._chips_row,
                    ),
                    # new tag row
                    ft.Row(
                        controls=[
                            self._new_tag_field,
                            ft.FilledButton(
                                "Add",
                                icon=ft.Icons.ADD,
                                on_click=self._add_new_tag,
                            ),
                        ],
                    ),
                    self._status,
                ],
            ),
        )
        self.actions = [
            ft.TextButton("Cancel", on_click=self._cancel),
            ft.FilledButton("Save", on_click=self._save),
        ]
        self.actions_alignment = ft.MainAxisAlignment.END

    # ------------------------------------------------------------------ public

    def open_for_document(self, doc: Document, module: Module):
        self._doc = doc
        self._module = module
        self._selected = set(t.name if hasattr(t, "name") else t for t in doc.tags)
        self._status.value = ""
        self._new_tag_field.value = ""
        self._rebuild_chips()
        self.open = True
        self.update()

    # ----------------------------------------------------------------- private

    def _rebuild_chips(self):
        all_tags = self._store.load_all_tags()
        self._chips_row.controls.clear()

        if not all_tags:
            self._chips_row.controls.append(
                ft.Text("No tags yet — add one below.", size=12, color=ft.Colors.WHITE_38, italic=True)
            )
        else:
            for tag_name in sorted(all_tags):
                selected = tag_name in self._selected
                self._chips_row.controls.append(
                    self._build_chip(tag_name, selected)
                )

    def _build_chip(self, tag_name: str, selected: bool) -> ft.Container:
        return ft.Container(
            key=tag_name,
            bgcolor=ft.Colors.BLUE_700 if selected else ft.Colors.GREY_800,
            border_radius=20,
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            on_click=lambda e, n=tag_name: self._toggle_tag(n),
            ink=True,
            content=ft.Row(
                spacing=6,
                tight=True,
                controls=[
                    ft.Icon(
                        ft.Icons.LABEL if selected else ft.Icons.LABEL_OUTLINE,
                        size=14,
                        color=ft.Colors.WHITE if selected else ft.Colors.WHITE_70,
                    ),
                    ft.Text(
                        tag_name,
                        size=13,
                        color=ft.Colors.WHITE if selected else ft.Colors.WHITE_70,
                    ),
                ],
            ),
        )

    def _toggle_tag(self, tag_name: str):
        if tag_name in self._selected:
            self._selected.discard(tag_name)
        else:
            self._selected.add(tag_name)
        self._rebuild_chips()
        self.update()

    def _add_new_tag(self, e):
        name = (self._new_tag_field.value or "").strip()
        if not name:
            return
        existing = self._store.load_all_tags()
        if name in existing:
            self._status.value = f'Tag "{name}" already exists.'
            self.update()
            return
        self._store.add_global_tag(name)
        self._selected.add(name)
        self._new_tag_field.value = ""
        self._status.value = ""
        self._rebuild_chips()
        self.update()

    def _save(self, e):
        if self._doc is None or self._module is None:
            return
        self._store.save_doc_tags(self._module, self._doc, list(self._selected))
        # update the in-memory doc object so the UI reflects immediately
        from models.tag import Tag
        self._doc.tags = [Tag(n) for n in self._selected]
        self.open = False
        self.update()
        if self._on_changed:
            self._on_changed()

    def _cancel(self, e):
        self.open = False
        self.update()
