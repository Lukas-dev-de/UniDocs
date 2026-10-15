"""
ui/components/home_widgets/todos.py
-----------------------------------
Card with the group's todo list (local, stored in the group's .home.json).

Rows are built once per refresh; the "new todo" field lives outside that
column so typing in it survives a tick or a delete. Done todos only differ by
colour - the checkbox is the single source of truth for the state. The gear
opens a small dialog that can hide done todos from the card; they stay saved
(option ``hide_done`` in the group's .home.json).
"""

from __future__ import annotations

import flet as ft

from ui.components.home_widgets.base import HomeWidget


@ft.control
class TodosWidget(HomeWidget):
    TITLE = "Todos"
    TYPE = "todos"

    def __init__(self, store, module_store=None, on_open_module=None):
        super().__init__(store, module_store, on_open_module)

        # Built once on first open, then kept in the overlay and reused.
        self._settings_dialog = None
        self._hide_done_switch = None

        self._list_column = ft.Column(spacing=0, tight=True)
        self._add_field = ft.TextField(
            hint_text="Neues Todo…",
            dense=True,
            expand=True,
            border=ft.InputBorder.NONE,
            on_submit=self._add,
        )

        self.body.controls.append(self._list_column)
        self.body.controls.append(
            ft.Row(
                spacing=4,
                controls=[
                    self._add_field,
                    ft.IconButton(
                        icon=ft.Icons.ADD,
                        tooltip="Hinzufügen",
                        on_click=self._add,
                    ),
                ],
            )
        )

    def refresh(self):
        hide_done = bool(self.get_option("hide_done", False))
        todos = [
            todo
            for todo in self._store.load(self._group).get("todos", [])
            if isinstance(todo, dict) and todo.get("text")
        ]
        visible = [
            todo for todo in todos if not (hide_done and todo.get("done"))
        ]
        self._list_column.controls.clear()
        if not visible:
            self._list_column.controls.append(
                self.placeholder(
                    "Keine offenen Todos." if hide_done else "Noch keine Todos."
                )
            )
            return
        for todo in visible:
            self._list_column.controls.append(self._todo_row(todo))

    def _todo_row(self, todo: dict) -> ft.Row:
        done = bool(todo.get("done"))
        todo_id = todo.get("id")
        return ft.Row(
            spacing=4,
            controls=[
                ft.Checkbox(
                    value=done,
                    on_change=lambda e, tid=todo_id: self._toggle(tid),
                ),
                ft.Text(
                    todo["text"],
                    size=13,
                    expand=True,
                    color=ft.Colors.OUTLINE if done else None,
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_size=16,
                    tooltip="Entfernen",
                    on_click=lambda e, tid=todo_id: self._remove(tid),
                ),
            ],
        )

    #  actions 

    def _add(self, e=None):
        text = (self._add_field.value or "").strip()
        if not text:
            return
        self._store.add_todo(self._group, text)
        self._add_field.value = ""
        self.refresh()
        self.update()

    def _toggle(self, todo_id):
        self._store.toggle_todo(self._group, todo_id)
        self.refresh()
        self.update()

    def _remove(self, todo_id):
        self._store.remove_todo(self._group, todo_id)
        self.refresh()
        self.update()

    #  settings 

    def open_settings(self, e=None):
        page = self._page()
        if page is None:
            return
        if self._settings_dialog is None:
            self._hide_done_switch = ft.Switch(
                label="Erledigte ausblenden",
                value=False,
                on_change=self._save_hide_done,
            )
            self._settings_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Todos"),
                content=ft.Container(
                    width=320,
                    content=ft.Column(
                        tight=True,
                        spacing=10,
                        controls=[
                            self._hide_done_switch,
                            ft.Text(
                                "Ausgeblendete Todos bleiben gespeichert.",
                                size=11,
                                color=ft.Colors.OUTLINE,
                            ),
                        ],
                    ),
                ),
                actions=[
                    ft.TextButton("Fertig", on_click=lambda e: self._close_settings())
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.overlay.append(self._settings_dialog)

        self._hide_done_switch.value = bool(self.get_option("hide_done", False))
        self._settings_dialog.open = True
        page.update()

    def _save_hide_done(self, e=None):
        self.set_option("hide_done", bool(self._hide_done_switch.value))
        self.refresh()
        self._safe_update(self)

    def _close_settings(self):
        self._settings_dialog.open = False
        self._safe_update(self._settings_dialog)
