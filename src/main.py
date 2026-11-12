import flet as ft
from app_logging import get_logger, setup_logging
from ui.module_detail import ModuleDetail
from ui.group_home import GroupHomeDetail
from ui.module_sidebar import ModuleSidebar
from ui.theme import ThemeManager
from ui.update_prompt import StartupUpdateCheck
from app_storage.module_store import ModuleStore
from app_storage.app_config import AppConfig
from sync.service import SyncService

log = get_logger(__name__)


def main(page: ft.Page):
    # Writes swallowed UI errors to the per-user log file (see app_logging).
    setup_logging()
    log.info("UniDocs starting")

    cfg = AppConfig()
    store = ModuleStore(
        root=cfg.unidocs_location,
        device_id=cfg.device_id,
        device_name=cfg.device_name,
    )
    sync_service = SyncService(page, cfg, store)

    # Release the filesystem watcher when the window closes. Its observer
    # thread is a daemon, so the process would exit anyway - this just closes
    # the inotify / FSEvents handle instead of leaving it to the OS.
    def _on_close(e):
        sync_service.shutdown()
        store.stop_watching()
        log.debug("window closed, filesystem watcher stopped")

    page.on_close = _on_close

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

        Matched by the module's stable id, so a rename (or a rename plus a
        group change) still finds the module that is on screen. Only that
        module needs refreshing; ``previous_title`` is no longer needed for
        the match but stays part of the callback contract.
        """
        shown = module_card.module
        if shown is not None and shown.id == module.id:
            module_card.set_module(module)

    def refresh_after_external_change():
        """Sync/trash changed files: reload sidebar and the visible detail pane."""
        sidebar._reload_and_update()
        shown = module_card.module
        if module_card.visible and shown is not None:
            match = next((m for m in store.load_all() if m.id == shown.id), None)
            if match is not None:
                module_card.set_module(match)
            else:
                show_group_home(sidebar.active_group)
        else:
            group_home.set_group(sidebar.active_group)

    page.title = "UniDocs"
    sidebar = ModuleSidebar(
        store=store,
        theme=theme,
        on_module_select=show_module,
        on_module_update=on_module_update,
        on_group_select=show_group_home,
        sync_service=sync_service,
        on_sync_finished=refresh_after_external_change,
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

    if cfg.sync_on_start and cfg.sync_provider != "off":
        sync_service.start()

    # Asks GitHub in the background: silent for patch releases, at most one popup
    # per version otherwise (see ui.update_prompt).
    StartupUpdateCheck(page, cfg).start()


if __name__ == "__main__":
    ft.run(main)