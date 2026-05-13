import flet as ft
from ui.components.module_icon_card import ModuleIconCard
from ui.components.icon_selector import IconSelector
from models.module import Module

@ft.control
class ModuleListCard(ft.Container):
    expand : int = 1
    padding : int = 8
    border_radius : int = 16
    bgcolor : ft.Colors = ft.Colors.GREY_900
    selected_module : Module = None

    def __init__(self, on_module_select=None):
        super().__init__()
        self._on_module_select = on_module_select

        self.modules_list = ft.Column(scroll=ft.ScrollMode.AUTO)

        self.icon_selector = IconSelector()
        self.textField_module_title = ft.TextField(hint_text="New Module", on_submit=self.add_module, expand=True)
        self.textField_module_desctiption = ft.TextField(hint_text="Desctiption", on_submit=self.add_module)

        ### UI-LAYOUT ###
        self.content = ft.Column(
            controls=[
                ft.PopupMenuButton(
                    icon=ft.Icons.ADD_BOX,
                    tooltip="Add Module",
                    items=[
                        ft.PopupMenuItem(
                            content=ft.Row(controls=[self.icon_selector, self.textField_module_title]),
                            padding=8
                        ),
                        ft.PopupMenuItem(
                            content=self.textField_module_desctiption,
                            padding=8
                        )
                    ],
                    align=ft.Alignment.TOP_CENTER,
                    
                ),
                self.modules_list
            ]
        )
        #################


    def add_module(self, e: ft.ControlEvent):
        _module = Module(
            title=self.textField_module_title.value,
            description=self.textField_module_desctiption.value,
            icon=self.icon_selector.value
        )
        self.modules_list.controls.append(
            ModuleIconCard(_module, on_select=self._on_module_select)
        )
        self.icon_selector.reset()
        self.textField_module_title.value = ""
        self.textField_module_desctiption.value = ""
        self.update()