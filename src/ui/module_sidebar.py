import flet as ft
from ui.components.module_tile import ModuleTile
from ui.components.module_create_dialog import ModuleCreateDialog
from ui.components.module_edit_dialog import ModuleEditDialog
from ui.components.group_dialog import GroupDialog
from ui.settings_dialog import SettingsDialog
from ui.context_menu import ContextMenu
from models.module import Module
from app_storage.app_config import AppConfig
from app_storage.module_store import ModuleStore
from app_storage.home_store import HomeStore
from ui.theme import ThemeManager


@ft.control
class ModuleSidebar(ft.Container):
    padding: int = 8
    border_radius: int = 16
    bgcolor: ft.Colors = ft.Colors.SURFACE

    def __init__(
        self,
        store: ModuleStore,
        on_module_select=None,
        on_module_update=None,
        theme: ThemeManager | None = None,
        on_group_select=None,
    ):
        super().__init__()
        self._store = store
        self._on_module_select = on_module_select
        self._on_module_update = on_module_update
        self._theme = theme
        self._on_group_select = on_group_select
        self._cfg = AppConfig()
        # Writes the "recent modules" list the group home page reads back.
        self._home = HomeStore(store)

        # Currently selected group filter: None = Home (the UniDocs root).
        # With "reopen in the last group" on, start on the remembered group
        # again (a group that has since been removed falls back to Home).
        self._active_group: str | None = None
        if self._cfg.restore_group:
            saved_group = self._cfg.last_group
            if saved_group and saved_group in self._store.list_group_names():
                self._active_group = saved_group

        self.modules_list = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)

        # Compact group selector: an icon button that drops a menu with
        # "Home", every group (checkmarked) and a "New group…" entry. The
        # active group name is only shown in the hover tooltip.
        self._group_select = ft.PopupMenuButton(
            icon=ft.Icons.FOLDER_SPECIAL,
            icon_color=ft.Colors.ON_SURFACE_VARIANT,
            tooltip="Home",
            items=self._group_menu_items(),
        )

        # Back to the group's home page when a module is open. The group menu
        # does the same when the active group is picked again, this just makes
        # it a one-click "up".
        self._home_button = ft.IconButton(
            icon=ft.Icons.HOME_OUTLINED,
            tooltip="Group home",
            on_click=self._go_home,
        )

        # The sidebar sits in the main Row as a non-flexible child, so it gets
        # an unbounded width during layout - a plain ft.Divider draws nothing
        # there (it paints on maxWidth). A fixed-width line avoids that.
        self._separator = ft.Container(
            width=40,
            height=1,
            bgcolor=ft.Colors.OUTLINE_VARIANT,
            margin=ft.margin.symmetric(vertical=8),
        )

        self.content = ft.Column(
            expand=True,
            alignment="CENTER",
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.IconButton(
                    icon=ft.Icons.ADD_BOX,
                    tooltip="Add Module",
                    on_click=self._open_create_dialog,
                ),
                self._group_select,
                self._separator,
                self._home_button,
                self.modules_list,
                ft.IconButton(
                    icon=ft.Icons.SETTINGS,
                    tooltip="Settings",
                    on_click=self._open_settings,
                ),
            ],
        )

        self._load_from_store()
        self._store._on_change = self._on_fs_change
        self._store.start_watching()

    #  lifecycle 

    def did_mount(self):
        self._settings_dialog = SettingsDialog(
            store=self._store,
            theme=self._theme,
            on_location_change=self._on_location_change,
        )

        self._ctx_menu = ContextMenu()
        self._create_dialog = ModuleCreateDialog(on_create=self._on_create_module)
        self._edit_dialog = ModuleEditDialog(
            store=self._store,
            on_saved=self._on_module_edited,
        )
        self._group_dialog = GroupDialog(
            store=self._store,
            on_moved=self._on_module_moved,
        )

        # New group prompt (opened from the group selector's "New group…").
        self._new_group_field = ft.TextField(
            label="Group name",
            dense=True,
            autofocus=True,
            on_submit=self._commit_new_group,
        )
        self._new_group_status = ft.Text("", color=ft.Colors.ERROR, size=12)
        self._new_group_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("New Group"),
            content=ft.Container(
                width=320,
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[self._new_group_field, self._new_group_status],
                ),
            ),
            actions=[
                ft.TextButton(
                    "Cancel",
                    on_click=lambda e: self._close_dialog(self._new_group_dialog),
                ),
                ft.FilledButton("Create", on_click=self._commit_new_group),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        # Delete confirm dialog
        self._delete_label = ft.Text("")
        self._delete_confirm_cb = None
        self._delete_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Delete Module"),
            content=self._delete_label,
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self._close_dialog(self._delete_dialog)),
                ft.FilledButton(
                    "Delete",
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.ERROR,
                        color=ft.Colors.ON_ERROR,
                    ),
                    on_click=self._commit_delete,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        for item in (
            self._settings_dialog,
            self._ctx_menu,
            self._delete_dialog,
            self._create_dialog,
            self._edit_dialog,
            self._group_dialog,
            self._new_group_dialog,
        ):
            self.page.overlay.append(item)
        self.page.update()

    def will_unmount(self):
        page = self.page
        if page is None:
            return
        for item in (
            self._settings_dialog,
            self._ctx_menu,
            self._delete_dialog,
            self._create_dialog,
            self._edit_dialog,
            self._group_dialog,
            self._new_group_dialog,
        ):
            if hasattr(self, "_settings_dialog") and item in page.overlay:
                page.overlay.remove(item)

    #  settings 

    def _open_settings(self, e):
        self._settings_dialog.show()

    def _on_location_change(self, new_path):
        self._store.stop_watching()
        self._store.root = new_path
        self._store._on_change = self._on_fs_change
        self._store.start_watching()
        self._reload_and_update()

    #  store helpers 

    def _load_from_store(self):
        self.modules_list.controls.clear()
        for module in self._store.load_modules(self._active_group):
            self.modules_list.controls.append(self._make_tile(module))
        self._group_select.items = self._group_menu_items()
        self._group_select.tooltip = self._active_group or "Home"

    def _make_tile(self, module: Module):
        tile = ModuleTile(module, on_select=self._on_tile_select)
        return ft.GestureDetector(
            content=tile,
            on_secondary_tap_down=lambda e, m=module: self._show_module_menu(e, m),
        )

    def _on_tile_select(self, module: Module):
        """Remember the opened module, then hand it to the detail view."""
        self._cfg.last_module = module.title
        # Feed the group's "recent modules" home widget; the active group is
        # exactly the folder the module was picked from.
        self._home.record_module_open(self._active_group, module.title)
        if self._on_module_select:
            self._on_module_select(module)

    @property
    def active_group(self) -> str | None:
        """Group folder currently shown in the sidebar (``None`` = Home)."""
        return self._active_group

    def on_group_renamed(self, old_name: str, new_name: str):
        """Follow a group rename done on the group home page.

        The active group is a folder name, so it has to move with the rename -
        otherwise the sidebar would keep listing (and saving into) a folder that
        no longer exists.
        """
        if self._active_group == old_name:
            self._active_group = new_name
            self._cfg.last_group = new_name
        self._reload_and_update()

    def _go_home(self, e=None):
        """Show the active group's home page in the detail pane."""
        if self._on_group_select:
            self._on_group_select(self._active_group)

    #  session restore 

    def restore_session(self):
        """Reopen the last module after mount (main.py calls this).

        Only runs when both switches are on: a restored group picks the right
        list, and only then is the remembered module looked up inside it. A
        module that no longer exists simply leaves the group on screen.
        """
        if not (self._cfg.restore_group and self._cfg.restore_module):
            return
        title = self._cfg.last_module
        if not title or not self._on_module_select:
            return
        for module in self._store.load_modules(self._active_group):
            if module.title == title:
                self._on_module_select(module)
                return

    @staticmethod
    def _tile_module(control) -> Module | None:
        """Dig the Module back out of a tile built by ``_make_tile``."""
        return getattr(getattr(control, "content", None), "module", None)

    def _open_create_dialog(self, e=None):
        self._create_dialog.show(
            groups=self._store.list_group_names(),
            current_group=self._active_group,
        )

    def _on_create_module(self, title, description, icon, color, group):
        """Store a module the create dialog handed back and show its tile."""
        _module = Module(
            title=title,
            description=description,
            icon=icon or ft.Icons.FOLDER,
            color=color,
            group=group,
        )

        self._store.save_module(_module)
        if group == self._active_group:
            self.modules_list.controls.append(self._make_tile(_module))
            # Keep the new module where the list just put it (at the end)
            # rather than letting it jump once the sidebar reloads.
            self._persist_order()
            self.update()
        else:
            # Created in a group that is not the one on screen: just reload.
            self._reload_and_update()

    #  ordering 

    def _persist_order(self):
        self._store.save_order(
            [
                module.title
                for module in (
                    self._tile_module(c) for c in self.modules_list.controls
                )
                if module
            ],
            self._active_group,
        )

    def _module_index(self, module: Module) -> int | None:
        """Position of *module* in the sidebar, or None if it is not shown."""
        for index, control in enumerate(self.modules_list.controls):
            tile = self._tile_module(control)
            if tile is not None and tile.title == module.title:
                return index
        return None

    def _move_module(self, module: Module, offset: int):
        """Swap *module* with its neighbour above (-1) or below (+1)."""
        controls = self.modules_list.controls
        index = self._module_index(module)
        if index is None:
            return
        target = index + offset
        if not 0 <= target < len(controls):
            return

        controls.insert(target, controls.pop(index))
        self.modules_list.update()
        self._persist_order()

    #  context menu 

    def _show_module_menu(self, e: ft.TapEvent, module: Module):
        index = self._module_index(module)
        # A module at one end of the list gets a greyed-out entry rather than a
        # missing one, so the menu keeps the same shape wherever it is opened.
        move_up = (
            (lambda m=module: self._move_module(m, -1))
            if index is not None and index > 0
            else None
        )
        move_down = (
            (lambda m=module: self._move_module(m, +1))
            if index is not None and index < len(self.modules_list.controls) - 1
            else None
        )

        self._ctx_menu.show(
            e.global_position.x,
            e.global_position.y,
            [
                ("Edit", ft.Icons.EDIT_OUTLINED, ft.Colors.ON_SURFACE, lambda m=module: self._module_edit(m)),
                ("Move up", ft.Icons.ARROW_UPWARD, ft.Colors.ON_SURFACE, move_up),
                ("Move down", ft.Icons.ARROW_DOWNWARD, ft.Colors.ON_SURFACE, move_down),
                ("Add to Group", ft.Icons.DRIVE_FILE_MOVE, ft.Colors.ON_SURFACE, lambda m=module: self._module_add_to_group(m)),
                ("Delete", ft.Icons.DELETE_OUTLINE, ft.Colors.ERROR, lambda m=module: self._module_delete(m)),
            ],
        )

    #  groups 

    def _group_menu_items(self):
        """Build the items for the group selector (Home + groups + New group…)."""
        items = [
            ft.PopupMenuItem(
                content=ft.Text("Home"),
                checked=self._active_group is None,
                on_click=lambda e: self._select_group(None),
            )
        ]
        for name in self._store.list_group_names():
            items.append(
                ft.PopupMenuItem(
                    content=ft.Text(name),
                    checked=self._active_group == name,
                    on_click=lambda e, n=name: self._select_group(n),
                )
            )
        items.append(ft.PopupMenuItem())  # divider
        items.append(
            ft.PopupMenuItem(
                icon=ft.Icons.CREATE_NEW_FOLDER,
                content=ft.Text("New group…"),
                on_click=lambda e: self._open_new_group_dialog(),
            )
        )
        return items

    def _select_group(self, name: str | None):
        self._active_group = name
        self._cfg.last_group = name or ""
        self._reload_and_update()
        # Opening a group shows its home page (no module is selected yet).
        if self._on_group_select:
            self._on_group_select(name)

    def _open_new_group_dialog(self):
        self._new_group_field.value = ""
        self._new_group_field.error_text = None
        self._new_group_status.value = ""
        self._new_group_dialog.open = True
        self._new_group_dialog.update()

    def _commit_new_group(self, e=None):
        name = (self._new_group_field.value or "").strip()
        if not name:
            self._new_group_field.error_text = "Name cannot be empty"
            self._new_group_dialog.update()
            return
        try:
            folder = self._store.create_group(name)
        except ValueError as ex:
            self._new_group_status.value = str(ex)
            self._new_group_dialog.update()
            return
        self._close_dialog(self._new_group_dialog)
        self._select_group(folder)

    def _module_add_to_group(self, module: Module):
        self._group_dialog.open_for_module(module)

    def _on_module_moved(self):
        self._reload_and_update()

    #  dialog helpers 

    def _close_dialog(self, dlg):
        dlg.open = False
        dlg.update()

    def _open_delete_dialog(self, label: str, on_confirm):
        self._delete_label.value = label
        self._delete_confirm_cb = on_confirm
        self._delete_dialog.open = True
        self._delete_dialog.update()

    def _commit_delete(self, e):
        self._close_dialog(self._delete_dialog)
        if self._delete_confirm_cb:
            self._delete_confirm_cb()

    #  module actions 

    def _module_edit(self, module: Module):
        self._edit_dialog.open_for(module)

    def _on_module_edited(self, module: Module, previous_title: str | None):
        """Re-render the sidebar, and let the detail view refresh itself.

        ``previous_title`` is what the module was called before the edit, so
        the detail view can tell whether *it* was the module being edited.
        """
        self._reload_and_update()
        if self._on_module_update:
            self._on_module_update(module, previous_title)

    def _module_delete(self, module: Module):
        def on_confirm():
            try:
                self._store.delete_module(module)
            except Exception as ex:
                print(f"Delete failed: {ex}")
            self._reload_and_update()
        self._open_delete_dialog(
            f'Delete "{module.title}" and all its documents? This cannot be undone.',
            on_confirm,
        )

    #  live-sync 

    def _on_fs_change(self):
        try:
            page = self.page
            if page is None:
                return
            # Called from the watchdog thread: hop onto the page's event loop
            # (``run_task`` needs a coroutine function).
            page.run_task(self._reload_and_update_async)
        except Exception:
            pass

    async def _reload_and_update_async(self):
        self._reload_and_update()

    def _reload_and_update(self):
        self._load_from_store()
        self.update()

