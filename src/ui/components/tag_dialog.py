"""
ui/components/tag_dialog.py
---------------------------
Dialog for assigning and creating tags on a Document.
Tags are now identified by their stable UUID (tag.id), not by name.
"""

from __future__ import annotations

import flet as ft

from models.document import Document
from models.module import Module
from models.tag import DEFAULT_TAG_COLOR
from app_storage.module_store import ModuleStore
from ui.components.tag_colors import TAG_PALETTE


class TagDialog(ft.AlertDialog):
    """
    Shows all global tags as toggleable chips.
    Lets the user create new tags with a chosen color.
    Saves assignments back via ModuleStore on confirm (stores IDs).
    """

    def __init__(self, store: ModuleStore, on_changed=None):
        super().__init__()
        self._store = store
        self._on_changed = on_changed

        self._doc: Document | None = None
        self._module: Module | None = None
        self._selected_ids: set[str] = set()   # set of tag IDs
        self._new_tag_color: str = DEFAULT_TAG_COLOR

        # existing tags chips
        self._chips_row = ft.Row(wrap=True, spacing=8, run_spacing=8)

        # new tag creation row
        self._new_tag_field = ft.TextField(
            hint_text="New tag name…",
            expand=True,
            dense=True,
            on_submit=self._add_new_tag,
        )
        self._color_swatch = ft.Container(
            width=28,
            height=28,
            border_radius=6,
            bgcolor=self._new_tag_color,
            border=ft.Border.all(2, ft.Colors.WHITE_30),
            tooltip="Pick color",
            on_click=self._open_color_picker,
            ink=True,
        )
        self._status = ft.Text("", color=ft.Colors.RED_400, size=12)

        # color picker popup
        self._color_picker_container = ft.Container(
            visible=False,
            bgcolor=ft.Colors.GREY_800,
            border_radius=10,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            padding=10,
            content=ft.Row(
                wrap=True,
                spacing=6,
                run_spacing=6,
                controls=self._build_palette_swatches(),
            ),
        )

        # layout
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
                    ft.Container(
                        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                        border_radius=8,
                        padding=12,
                        content=self._chips_row,
                    ),
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            self._new_tag_field,
                            self._color_swatch,
                            ft.FilledButton("Add", icon=ft.Icons.ADD, on_click=self._add_new_tag),
                        ],
                    ),
                    self._color_picker_container,
                    self._status,
                ],
            ),
        )
        self.actions = [
            ft.TextButton("Cancel", on_click=self._cancel),
            ft.FilledButton("Save", on_click=self._save),
        ]
        self.actions_alignment = ft.MainAxisAlignment.END

    # -- public --------------------------------------------------------------

    def open_for_document(self, doc: Document, module: Module):
        self._doc = doc
        self._module = module
        # seed selection from doc's current tag IDs
        self._selected_ids = {t.id for t in doc.tags}
        self._status.value = ""
        self._new_tag_field.value = ""
        self._new_tag_color = DEFAULT_TAG_COLOR
        self._color_swatch.bgcolor = DEFAULT_TAG_COLOR
        self._color_picker_container.visible = False
        self._rebuild_chips()
        self.open = True
        self.update()

    # -- private -------------------------------------------------------------

    def _build_palette_swatches(self) -> list[ft.Control]:
        return [
            ft.Container(
                width=26,
                height=26,
                border_radius=5,
                bgcolor=hex_color,
                tooltip=label,
                ink=True,
                on_click=lambda e, c=hex_color: self._pick_color(c),
            )
            for hex_color, label in TAG_PALETTE
        ]

    def _open_color_picker(self, e):
        self._color_picker_container.visible = not self._color_picker_container.visible
        self.update()

    def _pick_color(self, hex_color: str):
        self._new_tag_color = hex_color
        self._color_swatch.bgcolor = hex_color
        self._color_picker_container.visible = False
        self.update()

    def _rebuild_chips(self):
        all_tags = self._store.load_all_tags()
        self._chips_row.controls.clear()
        if not all_tags:
            self._chips_row.controls.append(
                ft.Text("No tags yet – add one below.", size=12,
                        color=ft.Colors.WHITE_38, italic=True)
            )
        else:
            for tag in sorted(all_tags, key=lambda t: t["name"]):
                selected = tag["id"] in self._selected_ids
                self._chips_row.controls.append(
                    self._build_chip(tag["id"], tag["name"], tag["color"], selected)
                )

    def _build_chip(self, tag_id: str, tag_name: str, color: str, selected: bool) -> ft.Container:
        return ft.Container(
            key=tag_id,
            bgcolor=color if selected else ft.Colors.GREY_800,
            border_radius=20,
            border=ft.Border.all(2, color) if not selected else None,
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            on_click=lambda e, tid=tag_id: self._toggle_tag(tid),
            ink=True,
            content=ft.Row(
                spacing=6,
                tight=True,
                controls=[
                    ft.Icon(
                        ft.Icons.LABEL if selected else ft.Icons.LABEL_OUTLINE,
                        size=14,
                        color=ft.Colors.WHITE if selected else color,
                    ),
                    ft.Text(
                        tag_name,
                        size=13,
                        color=ft.Colors.WHITE if selected else ft.Colors.WHITE_70,
                    ),
                ],
            ),
        )

    def _toggle_tag(self, tag_id: str):
        if tag_id in self._selected_ids:
            self._selected_ids.discard(tag_id)
        else:
            self._selected_ids.add(tag_id)
        self._rebuild_chips()
        self.update()

    def _add_new_tag(self, e):
        name = (self._new_tag_field.value or "").strip()
        if not name:
            return
        existing_names = self._store.load_tag_names()
        if name in existing_names:
            self._status.value = f'Tag "{name}" already exists.'
            self.update()
            return
        new_tag = self._store.add_global_tag(name, self._new_tag_color)
        # auto-select the freshly created tag
        self._selected_ids.add(new_tag["id"])
        self._new_tag_field.value = ""
        self._new_tag_color = DEFAULT_TAG_COLOR
        self._color_swatch.bgcolor = DEFAULT_TAG_COLOR
        self._color_picker_container.visible = False
        self._status.value = ""
        self._rebuild_chips()
        self.update()

    def _save(self, e):
        if self._doc is None or self._module is None:
            return
        # persist IDs to .doc_tags
        self._store.save_doc_tags(self._module, self._doc, list(self._selected_ids))
        # update the in-memory doc so the UI reflects changes immediately
        tag_map = {t["id"]: t for t in self._store.load_all_tags()}
        from models.tag import Tag
        self._doc.tags = [
            Tag(tid, tag_map[tid]["name"], tag_map[tid]["color"])
            for tid in self._selected_ids
            if tid in tag_map
        ]
        self.open = False
        self.update()
        if self._on_changed:
            self._on_changed()

    def _cancel(self, e):
        self._color_picker_container.visible = False
        self.open = False
        self.update()