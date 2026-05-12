import flet as ft
from ui.module_card import ModuleCard
from ui.module_list_card import ModuleListCard

def main(page: ft.Page):
    
    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Row(
                spacing=8,
                controls=[
                    ModuleListCard(),
                    ModuleCard()
                ],
            ),
        ),
    )
    


if __name__ == "__main__":
    ft.run(main)