import flet as ft
from ui.module_detail import ModuleDetail
from ui.module_sidebar import ModuleSidebar
from storage.module_store import ModuleStore


def main(page: ft.Page):
    store = ModuleStore()          # UniDocs/ next to main.py
    module_card = ModuleDetail(store=store)

    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Row(
                spacing=8,
                controls=[
                    ModuleSidebar(store=store, on_module_select=module_card.set_module),
                    module_card,
                ],
            ),
        ),
    )


if __name__ == "__main__":
    ft.run(main)
