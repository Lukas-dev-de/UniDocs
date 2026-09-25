"""
ui/components/module_create_dialog.py
--------------------------------------
Modal form for creating a new module.

Mirrors ``ModuleEditDialog``: a titled ``AlertDialog`` with full-width
title / description fields, an icon + colour row, and Cancel / Create
actions. The dialog owns no storage state; it collects the values and
hands them to ``on_create(title, description, icon, color)``.

    dialog = ModuleCreateDialog(on_create=cb)
    dialog.show()
"""

import flet as ft

from ui.components.color_selector import ColorSelector
from ui.components.icon_selector import IconSelector


class ModuleCreateDialog(ft.AlertDialog):
    def __init__(self, on_create=None):
        self._on_create = on_create

        self._title_field = ft.TextField(
            label="Title",
            dense=True,
            autofocus=True,
            on_submit=self._create,
        )
        self._desc_field = ft.TextField(
            label="Description",
            dense=True,
            on_submit=self._create,
        )
        self._icon_selector = IconSelector()
        self._color_selector = ColorSelector()

        super().__init__(
            modal=True,
            title=ft.Text("New Module"),
            content=ft.Container(
                width=400,
                content=ft.Column(
                    spacing=12,
                    tight=True,
                    controls=[
                        self._title_field,
                        self._desc_field,
                        ft.Row(
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Text(
                                    "Icon",
                                    size=13,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                self._icon_selector,
                                ft.Container(width=8),
                                ft.Text(
                                    "Color",
                                    size=13,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                self._color_selector,
                            ],
                        ),
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.close()),
                ft.FilledButton("Create", on_click=self._create),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    #  api 

    def show(self) -> None:
        """Reset the form to a blank module and open the dialog."""
        self._title_field.value = ""
        self._title_field.error_text = None
        self._desc_field.value = ""
        self._icon_selector.reset()
        self._color_selector.reset()
        self.open = True
        self.update()

    def close(self) -> None:
        self.open = False
        self.update()

    #  create 

    def _create(self, e=None) -> None:
        title = (self._title_field.value or "").strip()
        if not title:
            self._title_field.error_text = "Title cannot be empty"
            self.update()
            return

        description = self._desc_field.value or ""
        icon = self._icon_selector.value or ft.Icons.FOLDER
        color = self._color_selector.value

        self.close()
        if self._on_create:
            self._on_create(title, description, icon, color)
