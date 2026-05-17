import flet as ft
from ui.module_detail import ModuleDetail
from ui.module_sidebar import ModuleSidebar
from app_storage.module_store import ModuleStore
from app_storage.app_config import AppConfig


def main(page: ft.Page):
    cfg = AppConfig()
    store = ModuleStore(root=cfg.unidocs_location)
    module_card = ModuleDetail(store=store)
    page.title = "UniDocs"
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