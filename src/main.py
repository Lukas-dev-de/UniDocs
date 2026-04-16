import flet as ft


def main(page: ft.Page):
    page.title = "UniDocs"
    page.bgcolor = "#1a1a2e"
    page.padding = 16
    page.spacing = 0

    sidebar = ft.Container(
        width=64,
        bgcolor="#16213e",
        border_radius=16,
        padding=ft.padding.symmetric(vertical=12, horizontal=10),
        content=ft.Column(
            controls=[
                ft.IconButton(
                    icon=ft.Icons.ADD,
                    icon_color="#e94560",
                    icon_size=24,
                    style=ft.ButtonStyle(
                        bgcolor={"": "#0f3460"},
                        shape={"": ft.RoundedRectangleBorder(radius=10)},
                        overlay_color={"hovered": "#e9456022"},
                    ),
                    tooltip="Add Module",
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    main_area = ft.Container(
        expand=True,
        bgcolor="#16213e",
        border_radius=16,
    )

    page.add(
        ft.Row(
            controls=[sidebar, main_area],
            spacing=12,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )
    )


ft.app(target=main)