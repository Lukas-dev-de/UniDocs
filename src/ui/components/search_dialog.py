"""
ui/components/search_dialog.py
-------------------------------
Global search over every module of every group.

Hit sources are the module title, its description and the document titles.
The matching itself lives in :func:`search_modules` so it can be tested
without mounting a dialog; the dialog only renders the hits and reports the
clicked module through ``on_open_module``.

    dialog = SearchDialog(on_open_module=cb)
    dialog.show(store.load_all())
"""

import flet as ft

from models.module import Module

# Total number of rows the dialog renders. Keeps a one-letter query from
# pushing thousands of controls into the overlay.
MAX_RESULTS = 50


def search_modules(
    modules: list[Module],
    query: str,
) -> tuple[list[Module], list[tuple[Module, object]]]:
    """Split the modules matching *query* into module and document hits.

    Case-insensitive substring match. A module hits on its title or
    description, a document on its title. The two lists stay separate so the
    dialog can group them; module hits keep the store order (Home first).
    """
    needle = (query or "").strip().casefold()
    if not needle:
        return [], []

    module_hits: list[Module] = []
    document_hits: list[tuple[Module, object]] = []
    for module in modules:
        if needle in module.title.casefold() or needle in (
            module.description or ""
        ).casefold():
            module_hits.append(module)
        for document in module.documents:
            if needle in (document.title or "").casefold():
                document_hits.append((module, document))
    return module_hits, document_hits


def _group_label(module: Module) -> str:
    """Group name as shown to the user; the UniDocs root is "Home"."""
    return module.group or "Home"


class SearchDialog(ft.AlertDialog):
    def __init__(self, on_open_module=None):
        self._on_open_module = on_open_module
        self._modules: list[Module] = []

        self._field = ft.TextField(
            label="Module or document",
            dense=True,
            autofocus=True,
            prefix_icon=ft.Icons.SEARCH,
            on_change=self._on_change,
            on_submit=self._open_first,
        )
        self._hint = ft.Text(
            "",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        self._results = ft.Column(
            spacing=2,
            tight=True,
            height=340,
            scroll=ft.ScrollMode.AUTO,
        )

        super().__init__(
            modal=True,
            title=ft.Text("Search"),
            content=ft.Container(
                width=440,
                content=ft.Column(
                    spacing=8,
                    tight=True,
                    controls=[self._field, self._hint, self._results],
                ),
            ),
            actions=[
                ft.TextButton("Close", on_click=lambda e: self.close()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    #  api 

    def show(self, modules=None) -> None:
        """Open the dialog with the modules to search through."""
        self._modules = list(modules or [])
        self._field.value = ""
        self._hint.value = "Type to search across every module."
        self._results.controls.clear()
        self.open = True
        self.update()

    def close(self) -> None:
        self.open = False
        self.update()

    #  search + rendering 

    def _on_change(self, e=None) -> None:
        self._render(self._field.value)

    def _render(self, query: str) -> None:
        module_hits, document_hits = search_modules(self._modules, query)
        self._results.controls.clear()

        if not module_hits and not document_hits:
            typed = bool((query or "").strip())
            self._hint.value = "No matches." if typed else (
                "Type to search across every module."
            )
            self.update()
            return

        self._hint.value = (
            f"{len(module_hits)} module(s), {len(document_hits)} document(s)"
        )

        budget = MAX_RESULTS
        if module_hits:
            self._results.controls.append(self._section("Modules"))
            for module in module_hits[:budget]:
                budget -= 1
                self._results.controls.append(self._module_row(module))
        if document_hits and budget > 0:
            self._results.controls.append(self._section("Documents"))
            for module, document in document_hits[:budget]:
                budget -= 1
                self._results.controls.append(self._doc_row(module, document))
        self.update()

    def _section(self, title: str) -> ft.Text:
        return ft.Text(
            title,
            size=12,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )

    def _module_row(self, module: Module) -> ft.ListTile:
        return ft.ListTile(
            dense=True,
            leading=ft.Icon(module.icon or ft.Icons.FOLDER),
            title=ft.Text(module.title, size=13),
            subtitle=ft.Text(_group_label(module), size=11),
            on_click=lambda e, m=module: self._open(m),
        )

    def _doc_row(self, module: Module, document) -> ft.ListTile:
        return ft.ListTile(
            dense=True,
            leading=ft.Icon(ft.Icons.DESCRIPTION_OUTLINED),
            title=ft.Text(document.title, size=13),
            subtitle=ft.Text(
                f"{module.title} · {_group_label(module)}",
                size=11,
            ),
            on_click=lambda e, m=module: self._open(m),
        )

    #  actions 

    def _open_first(self, e=None) -> None:
        """Enter opens the first hit: modules are listed before documents."""
        module_hits, document_hits = search_modules(self._modules, self._field.value)
        if module_hits:
            self._open(module_hits[0])
        elif document_hits:
            self._open(document_hits[0][0])

    def _open(self, module: Module) -> None:
        self.close()
        if self._on_open_module:
            self._on_open_module(module)
