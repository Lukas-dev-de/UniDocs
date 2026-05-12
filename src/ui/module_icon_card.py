import flet as ft

@ft.control
class ModuleIconCard(ft.IconButton):
    expand = True
    border_radius : int = 8
    bgcolor : ft.Colors =ft.Colors.BLUE_900
    icon : ft.Icon = ft.Icons.SQUARE
    content : any = ft.Column(
        expand=True,
        controls=[
        ft.Text(value="Title", size=70)
        ]
    )