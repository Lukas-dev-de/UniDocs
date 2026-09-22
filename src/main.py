import flet as ft
from ui.module_detail import ModuleDetail
from ui.module_sidebar import ModuleSidebar
from ui.theme import ThemeManager
from app_storage.module_store import ModuleStore
from app_storage.app_config import AppConfig


def main(page: ft.Page):
    cfg = AppConfig()
    store = ModuleStore(root=cfg.unidocs_location)

    # Apply the persisted palette + appearance mode before the first paint.
    theme = ThemeManager(cfg)
    theme.attach(page)

    module_card = ModuleDetail(store=store)

    def on_module_update(module, previous_title):
        """Keep the detail view in sync after the sidebar edits a module.

        Only the module that is actually on screen needs refreshing; the
        comparison uses the pre-edit title because a rename changes the
        module's title before this callback runs.
        """
        if module_card.module is not None and module_card.module.title == previous_title:
            module_card.set_module(module)

    page.title = "UniDocs"
    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Row(
                spacing=8,
                controls=[
                    ModuleSidebar(
                        store=store,
                        theme=theme,
                        on_module_select=module_card.set_module,
                        on_module_update=on_module_update,
                    ),
                    module_card,
                ],
            ),
        ),
    )


if __name__ == "__main__":
    ft.run(main)