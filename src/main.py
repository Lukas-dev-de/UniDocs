import flet as ft
from ui.module_card import ModuleCard
from ui.module_list_card import ModuleListCard

def main(page: ft.Page):
    module_card = ModuleCard()

    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Row(
                spacing=8,
                controls=[
                    ModuleListCard(on_module_select=module_card.set_module),
                    module_card
                ],
            ),
        ),
    )

if __name__ == "__main__":
    ft.run(main)