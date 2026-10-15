import flet as ft
from ui.module_detail import ModuleDetail
from ui.group_home import GroupHomeDetail
from ui.module_sidebar import ModuleSidebar
from ui.theme import ThemeManager
from ui.update_prompt import StartupUpdateCheck
from app_storage.module_store import ModuleStore
from app_storage.app_config import AppConfig


def main(page: ft.Page):
    cfg = AppConfig()
    store = ModuleStore(root=cfg.unidocs_location)

    # Keep the window from being squashed so small that the sidebar and the
    # detail pane no longer fit (sidebar is fixed-width, the detail pane needs
    # room for the module grid).
    page.window.min_height = 480
    page.window.min_width = 420

    # Apply the persisted palette + appearance mode before the first paint.
    theme = ThemeManager(cfg)
    theme.attach(page)

    module_card = ModuleDetail(store=store)
    # The recent-modules widget hands a title back to the same opener the
    # sidebar uses; the lambda resolves show_module late (defined just below).
    group_home = GroupHomeDetail(
        store=store,
        on_open_module=lambda module: show_module(module),
    )
    # The detail pane starts on the group home page (see below).
    module_card.visible = False

    def show_module(module):
        """Show a module's documents in the detail pane."""
        module_card.visible = True
        group_home.visible = False
        group_home.update()
        module_card.set_module(module)

    def show_group_home(group):
        """Show a group's home page (no module selected)."""
        module_card.visible = False
        group_home.visible = True
        module_card.update()
        group_home.set_group(group)

    def on_module_update(module, previous_title):
        """Keep the detail view in sync after the sidebar edits a module.

        Only the module that is actually on screen needs refreshing; the
        comparison uses the pre-edit title because a rename changes the
        module's title before this callback runs.
        """
        if (
            module_card.module is not None
            and module_card.module.title == previous_title
            and (module_card.module.group or None) == (module.group or None)
        ):
            module_card.set_module(module)

    page.title = "UniDocs"
    sidebar = ModuleSidebar(
        store=store,
        theme=theme,
        on_module_select=show_module,
        on_module_update=on_module_update,
        on_group_select=show_group_home,
    )
    # A rename on the home page has to move the sidebar's active group with it.
    group_home.on_group_renamed = sidebar.on_group_renamed

    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Row(
                spacing=8,
                controls=[
                    sidebar,
                    group_home,
                    module_card,
                ],
            ),
        ),
    )

    # Open on the active group's home page; restore_session may then swap in a
    # module. Runs after the controls are mounted so the detail views exist.
    show_group_home(sidebar.active_group)

    # Reopen the group / module from the previous session (see Settings >
    # Startup). Runs after the controls are mounted so the detail view exists.
    sidebar.restore_session()

    # Asks GitHub in the background: silent for patch releases, at most one popup
    # per version otherwise (see ui.update_prompt).
    StartupUpdateCheck(page, cfg).start()


if __name__ == "__main__":
    ft.run(main)