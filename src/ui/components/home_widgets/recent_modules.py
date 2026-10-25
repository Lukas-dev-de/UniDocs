"""
ui/components/home_widgets/recent_modules.py
--------------------------------------------
Card listing the modules most recently opened in the current group.

The list itself lives in the group's .home.json and is written by the sidebar
(HomeStore.record_module_open) whenever a module is opened. Titles that no
longer match a module in the group are dropped, so a deleted module cannot
haunt the list. Clicking a row reopens the module (``on_open_module``).
"""

from __future__ import annotations

import flet as ft

from ui.components.home_widgets.base import HomeWidget


@ft.control
class RecentModulesWidget(HomeWidget):
    TITLE = "Zuletzt geöffnet"
    TYPE = "recent_modules"
    # Nothing to configure.
    HAS_SETTINGS = False

    def __init__(self, store, module_store=None, on_open_module=None):
        super().__init__(store, module_store, on_open_module)

    def refresh(self):
        self.body.controls.clear()
        if self._modules is None:
            return
        existing = {m.title: m for m in self._modules.load_modules(self._group)}
        modules = [
            existing[title]
            for title in self._store.recent_modules(self._group)
            if title in existing
        ]
        if not modules:
            self.body.controls.append(self.placeholder("Noch keine Module geöffnet."))
            return
        for module in modules:
            self.body.controls.append(self._module_row(module))

    def _module_row(self, module) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                spacing=8,
                controls=[
                    ft.Icon(module.icon or ft.Icons.FOLDER, size=18, color=ft.Colors.PRIMARY),
                    ft.Text(
                        module.title,
                        size=13,
                        expand=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
            border_radius=8,
            ink=True,
            tooltip=module.title,
            on_click=lambda e, m=module: self._open(m),
        )

    def _open(self, module):
        if self._on_open_module:
            self._on_open_module(module)
