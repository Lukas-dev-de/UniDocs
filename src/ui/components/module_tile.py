import flet as ft
from models.module import Module

@ft.control
class ModuleTile(ft.IconButton):
    def __init__(self, module: Module, on_select=None):  # neu: on_select
        super().__init__()
        self.module = module
        self._on_select = on_select

        self.align = ft.Alignment.CENTER
        
        self.border_radius = 8
        self.bgcolor = ft.Colors.BLUE_900
        self.icon = module.icon
        self.tooltip = module.title
        self.on_click = self._handle_click 

        self.content = ft.Container(
            padding=16,
            content=ft.Column(
                expand=True,
                controls=[
                    ft.Icon(module.icon, size=48),
                    ft.Text(value=module.title, size=24, weight=ft.FontWeight.BOLD),
                    ft.Text(value=module.description, size=14, color=ft.Colors.WHITE_70),
                ],
            ),
        )

    def _handle_click(self, e):
        if self._on_select:
            self._on_select(self.module)