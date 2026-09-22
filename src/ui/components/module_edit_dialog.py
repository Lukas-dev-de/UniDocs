"""
ui/components/module_edit_dialog.py
------------------------------------
Modal editor for an existing module's title, description, icon and colour.

The title is the module's folder name on disk, so a rename goes through
``ModuleStore.rename_module`` (which moves the folder, keeping the documents
and their tags with it). A rename that would collide with another module is
refused with an inline error instead of clobbering the other folder.

    dialog = ModuleEditDialog(store=store, on_saved=cb)
    dialog.open_for(module)      # -> cb(module, previous_title)
"""

import flet as ft

from models.module import Module
from ui.components.color_selector import ColorSelector
from ui.components.icon_selector import IconSelector


class ModuleEditDialog(ft.AlertDialog):
    def __init__(self, store, on_saved=None):
        self._store = store
        self._on_saved = on_saved
        self._module: Module | None = None
        self._previous_title: str | None = None

        self._title_field = ft.TextField(
            label="Title",
            dense=True,
            on_submit=self._save,
        )
        self._desc_field = ft.TextField(
            label="Description",
            dense=True,
            on_submit=self._save,
        )
        self._icon_selector = IconSelector()
        self._color_selector = ColorSelector()

        self._heading = ft.Text("Edit Module")

        super().__init__(
            modal=True,
            title=self._heading,
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
                ft.FilledButton("Save", on_click=self._save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    #  api 

    def open_for(self, module: Module) -> None:
        """Load *module* into the form and show the dialog."""
        self._module = module
        self._previous_title = module.title

        self._heading.value = f'Edit "{module.title}"'
        self._title_field.value = module.title
        self._title_field.error_text = None
        self._desc_field.value = module.description or ""
        self._icon_selector.set_value(module.icon)
        self._color_selector.set_value(module.color)

        self.open = True
        self.update()

    def close(self) -> None:
        self.open = False
        self.update()

    #  save 

    def _confirm_error(self, message: str) -> None:
        self._title_field.error_text = message
        self.update()

    def _save(self, e=None) -> None:
        module = self._module
        if module is None:
            return

        new_title = (self._title_field.value or "").strip()
        if not new_title:
            self._confirm_error("Title cannot be empty")
            return

        renamed = new_title != module.title
        if renamed and self._store.rename_conflict(module, new_title):
            self._confirm_error("A module with this name already exists")
            return

        module.description = self._desc_field.value or ""
        module.icon = self._icon_selector.value or module.icon
        module.color = self._color_selector.value

        try:
            if renamed:
                self._store.rename_module(module, new_title)
            self._store.save_module(module)
        except Exception as ex:  # disk trouble: keep the dialog open
            self._confirm_error(f"Could not save: {ex}")
            return

        previous_title = self._previous_title
        self.close()
        if self._on_saved:
            self._on_saved(module, previous_title)
