import flet as ft

@ft.control
class ModuleCard(ft.Container):
    border_radius : int = 8
    padding : int = 8
    expand : int = 19

    align=ft.Alignment.TOP_LEFT

    bgcolor : ft.Colors = ft.Colors.BLUE_500
    
    content : any = ft.Column(
        expand=True,
        controls=[
            ft.Text(value="Title", size=70, align=ft.Alignment.TOP_LEFT),
            ft.Text(value="Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet.")
        ]
    )