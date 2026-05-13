import flet as ft
from models.module import Module


@ft.control
class ModuleCard(ft.Container):

    def __init__(self):
        super().__init__()

        self.module = None

        # UI elements
        self.title_text = ft.Text(
            value="No Module Selected",
            size=32,
            weight=ft.FontWeight.BOLD,
        )

        self.description_text = ft.Text(
            value="Select a module to display information.",
            size=16,
            color=ft.Colors.WHITE_70,
        )


        # Styling
        self.border_radius = 16
        self.padding = 16
        self.expand = 19
        self.bgcolor = ft.Colors.GREY_900

        # Content
        self.content = ft.Column(
            spacing=10,
            controls=[
                ft.Row(
                    controls=[
                        self.title_text,
                    ]
                ),
                self.description_text,
            ],
        )

    def set_module(self, module: Module):
        self.module = module

        self.title_text.value = module.title
        self.description_text.value = module.description

        self.update()