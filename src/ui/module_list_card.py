import flet as ft
from ui.module_icon_card import ModuleIconCard
from models.module import Module

@ft.control
class ModuleListCard(ft.Container):
    expand : int = 1
    padding : int = 8
    border_radius : int = 8
    bgcolor : ft.Colors = ft.Colors.RED
    

    def __init__(self):
        super().__init__()

        self.modules_list = ft.Column(scroll=ft.ScrollMode.AUTO)
        def get_options() -> list[ft.DropdownOption]:
            icons = [
                {"name": "Smile", "icon": ft.Icons.SENTIMENT_SATISFIED_OUTLINED},
                {"name": "Cloud", "icon": ft.Icons.CLOUD_OUTLINED},
                {"name": "Brush", "icon": ft.Icons.BRUSH_OUTLINED},
                {"name": "Heart", "icon": ft.Icons.FAVORITE},
            ]
            return [
                ft.DropdownOption(key=icon["name"], leading_icon=icon["icon"])
                for icon in icons
        ]
        self.dropdown_module_icons = ft.Dropdown(
            key="icon_dropdown",
            border=ft.InputBorder.UNDERLINE,
            enable_filter=True,
            editable=True,
            leading_icon=ft.Icons.SEARCH,
            label="Icon",
            options=get_options()
        )
        self.textField_module_title = ft.TextField(
            hint_text="New Module",
            on_submit=self.add_module
        )
        self.textField_module_desctiption = ft.TextField(
            hint_text="Desctiption",
            on_submit=self.add_module
        )

        self.content = ft.Column(
            controls=[
                ft.PopupMenuButton(
                    icon=ft.Icons.ADD_BOX,
                    tooltip="Add Module",
                    items=[
                        ft.PopupMenuItem(
                            content=self.dropdown_module_icons
                        ),
                        ft.PopupMenuItem(
                            content=self.textField_module_title
                        ),
                        ft.PopupMenuItem(
                            content=self.textField_module_desctiption
                        )
                    ],
                ),
                self.modules_list
            ]
        )

    def add_module(self, e: ft.ControlEvent):
        name = self.textField_module_title.value

        if not name:
            print("Name must not be empty!")
            return

        module = Module(title=self.textField_module_title.value, description=self.textField_module_desctiption.value)
        self.modules_list.controls.append(ModuleIconCard())

        # clear fields
        self.dropdown_module_icons.value = ""
        self.textField_module_title.value = ""
        self.textField_module_desctiption.value = ""


        self.update()