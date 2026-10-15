"""
ui/components/group_dialog.py
-----------------------------
Modal for moving a module into a group (or back to "Home").

The dialog lists the existing groups in a dropdown (plus a "Home" entry) and
lets the user create a new group on the spot, mirroring the "New group…"
entry of the sidebar's group selector.

    dialog = GroupDialog(store=store, on_moved=cb)
    page.overlay.append(dialog)
    dialog.open_for_module(module)

Callback
--------
    on_moved()
        Fired after the module folder has been moved on disk. The sidebar
        reloads itself so the module disappears from / appears in the list.
"""

from __future__ import annotations

import flet as ft

from app_storage.module_store import ModuleStore

# Sentinel key for the "Home" entry: a real group folder can never be empty.
_HOME_KEY = "__home__"


class GroupDialog(ft.AlertDialog):
    def __init__(self, store: ModuleStore, on_moved=None):
        self._store = store
        self._on_moved = on_moved
        self._module = None

        self._dropdown = ft.Dropdown(
            label="Group",
            hint_text="Select a group…",
        )
        self._new_field = ft.TextField(
            label="New group",
            dense=True,
            expand=True,
            on_submit=self._create_group,
        )
        self._status = ft.Text("", color=ft.Colors.ERROR, size=12)

        super().__init__(
            modal=True,
            title=ft.Text("Add to Group"),
            content=ft.Container(
                width=360,
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        self._dropdown,
                        ft.Row(
                            spacing=8,
                            controls=[
                                self._new_field,
                                ft.FilledButton(
                                    "Create",
                                    icon=ft.Icons.CREATE_NEW_FOLDER,
                                    on_click=self._create_group,
                                ),
                            ],
                        ),
                        self._status,
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.close()),
                ft.FilledButton("Add", on_click=self._add),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    # api

    def open_for_module(self, module) -> None:
        self._module = module
        self._status.value = ""
        self._new_field.value = ""
        self._rebuild_options()
        self.open = True
        self.update()

    def close(self) -> None:
        self.open = False
        self.update()

    # helpers

    def _rebuild_options(self) -> None:
        options = [ft.dropdown.Option(key=_HOME_KEY, text="Home")]
        for name in self._store.list_group_names():
            options.append(ft.dropdown.Option(key=name, text=name))
        self._dropdown.options = options

        current = self._module.group if self._module else None
        self._dropdown.value = current or _HOME_KEY

    def _create_group(self, e=None) -> None:
        name = (self._new_field.value or "").strip()
        if not name:
            self._status.value = "Enter a group name."
            self.update()
            return
        try:
            folder = self._store.create_group(name)
        except ValueError as ex:
            self._status.value = str(ex)
            self.update()
            return
        self._new_field.value = ""
        self._status.value = ""
        self._rebuild_options()
        self._dropdown.value = folder
        self.update()

    def _add(self, e=None) -> None:
        if self._module is None:
            self.close()
            return
        target = self._dropdown.value
        if target in (None, "", _HOME_KEY):
            target = None
        try:
            self._store.move_module_to_group(self._module, target)
        except ValueError as ex:
            self._status.value = str(ex)
            self.update()
            return
        self.close()
        if self._on_moved:
            self._on_moved()
