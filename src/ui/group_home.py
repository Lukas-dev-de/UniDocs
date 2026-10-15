"""
ui/group_home.py
----------------
Landing page for a group (and for the UniDocs root, shown as "Home").

Shown in the detail pane whenever a group is opened and no module is selected.
The group name at the top can be clicked to rename the group, exactly like the
module title does (except for Home, which has no folder and cannot be renamed).

Below the title sits a grid of widgets (quick links, recent modules, todos,
calendar, timetable - see ui/components/home_widgets/). Each group has its own
widget config, stored in the group's ``.home.json`` (app_storage.home_store).
The floating button in the bottom right switches the page between read-only and
edit mode; in edit mode every configurable card shows a gear that opens its
settings dialog. Documents are never listed here.

    home = GroupHomeDetail(store=store, on_group_renamed=cb, on_open_module=cb2)
    home.set_group("School")   # or None for Home
"""

import flet as ft

from app_storage.module_store import ModuleStore
from app_storage.home_store import HomeStore
from ui.components.home_widgets.base import HomeWidget
from ui.components.home_widgets.quick_links import QuickLinksWidget
from ui.components.home_widgets.recent_modules import RecentModulesWidget
from ui.components.home_widgets.todos import TodosWidget
from ui.components.home_widgets.calendar import CalendarWidget
from ui.components.home_widgets.schedule import ScheduleWidget
from ui.context_menu import ContextMenu

# Widget type name (as stored in .home.json) -> card class.
_WIDGET_TYPES = {
    "quick_links": QuickLinksWidget,
    "recent_modules": RecentModulesWidget,
    "todos": TodosWidget,
    "calendar": CalendarWidget,
    "schedule": ScheduleWidget,
}

# Icon shown for each type in the "add widget" picker.
_WIDGET_ICONS = {
    "quick_links": ft.Icons.LINK,
    "recent_modules": ft.Icons.HISTORY,
    "todos": ft.Icons.CHECKLIST,
    "calendar": ft.Icons.CALENDAR_MONTH,
    "schedule": ft.Icons.CALENDAR_VIEW_WEEK,
}


class _WidgetPickerDialog(ft.AlertDialog):
    """Lets the user add a widget type that is not on the page yet.

    Only the still-available types are listed; every row adds on click. Adding
    reopens the dialog with a refreshed list, so several can be added in a row.
    """

    def __init__(self, on_add):
        self._on_add = on_add
        self._column = ft.Column(
            spacing=0, tight=True, scroll=ft.ScrollMode.AUTO, height=320
        )
        super().__init__(
            modal=True,
            title=ft.Text("Widget hinzufügen"),
            content=ft.Container(width=380, content=self._column),
            actions=[
                ft.TextButton("Schließen", on_click=lambda e: self.close())
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    def reset(self, available: list[tuple[str, str, str]]):
        self._column.controls.clear()
        if not available:
            self._column.controls.append(
                ft.Text(
                    "Alle Widgets sind schon auf der Seite.",
                    size=13,
                    color=ft.Colors.OUTLINE,
                )
            )
            return
        for key, title, icon in available:
            self._column.controls.append(
                ft.ListTile(
                    leading=ft.Icon(icon, color=ft.Colors.PRIMARY),
                    title=ft.Text(title),
                    trailing=ft.Icon(ft.Icons.ADD),
                    on_click=lambda e, k=key: self._on_add(k),
                )
            )

    def close(self):
        self.open = False
        try:
            self.update()
        except RuntimeError:
            pass


@ft.control
class GroupHomeDetail(ft.Container):

    def __init__(self, store: ModuleStore, on_group_renamed=None, on_open_module=None):
        super().__init__()

        self._store = store
        self._on_group_renamed = on_group_renamed
        self._on_open_module = on_open_module
        # Folder name of the group on screen; ``None`` = Home (UniDocs root).
        self._group: str | None = None
        # Edit mode reveals the per-widget gear buttons; off = read-only.
        self._edit_mode = False

        #  Title: text display + inline editor 
        self.title_text = ft.Text(
            value="Home",
            size=32,
            weight=ft.FontWeight.BOLD,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        self.title_field = ft.TextField(
            text_size=32,
            border=ft.InputBorder.UNDERLINE,
            expand=True,
            visible=False,
            on_submit=self._commit_title,
            on_blur=self._commit_title,
        )
        self._title_click = ft.GestureDetector(
            content=self.title_text,
            on_tap=self._start_title_edit,
            mouse_cursor=ft.MouseCursor.TEXT,
            expand=True,
        )

        #  Home page widgets 
        self._home = HomeStore(store)
        self._widgets: dict[str, HomeWidget] = {
            key: cls(
                store=self._home,
                module_store=store,
                on_open_module=on_open_module,
            )
            for key, cls in _WIDGET_TYPES.items()
        }
        # Widget-management helpers; built in did_mount (they need the page).
        self._ctx_menu = None
        self._picker = None
        self._widgets_grid = ft.GridView(
            expand=True,
            max_extent=360,
            spacing=12,
            run_spacing=12,
        )
        self._edit_button = ft.FilledButton(
            "Bearbeiten",
            icon=ft.Icons.EDIT,
            on_click=self._toggle_edit,
        )
        # The edit toggle floats above the grid in the bottom right corner.
        self._grid_stack = ft.Stack(
            expand=True,
            controls=[
                self._widgets_grid,
                ft.Container(content=self._edit_button, right=16, bottom=16),
            ],
        )

        #  Styling mirrors ModuleDetail so switching between the two is seamless. 
        self.border_radius = 16
        self.padding = 16
        self.expand = 19
        self.bgcolor = ft.Colors.SURFACE

        self.content = ft.Column(
            spacing=10,
            expand=True,
            controls=[
                ft.Row(
                    controls=[
                        ft.Column(
                            spacing=4,
                            expand=True,
                            controls=[
                                ft.Row(controls=[self._title_click, self.title_field]),
                            ],
                        ),
                    ],
                ),
                ft.Divider(color=ft.Colors.OUTLINE_VARIANT),
                self._grid_stack,
            ],
        )

    #  public 

    def set_group(self, group: str | None):
        """Show the home page for *group* (``None`` = Home)."""
        self._group = group or None
        self._show_title_text(self._group or "Home")
        self._title_click.tooltip = "Rename group" if self._group else "Home"
        # Every group page starts read-only; staying in edit mode across a
        # group switch would be surprising. _set_edit_mode rebuilds the grid.
        self._set_edit_mode(False)

    def did_mount(self):
        page = self.page
        if page is None:
            return
        self._ctx_menu = ContextMenu()
        self._picker = _WidgetPickerDialog(self._add_widget)
        page.overlay.append(self._ctx_menu)
        page.overlay.append(self._picker)
        page.update()

    #  widgets 

    def _order(self) -> list[str]:
        """Widget keys to show, in saved order.

        The saved "widgets" list is the single source of truth for what is on
        the page - a widget removed in edit mode stays off until it is added
        back. Keys with no matching class are dropped.
        """
        data = self._home.load(self._group)
        return [key for key in data.get("widgets", []) if key in self._widgets]

    def _rebuild_widgets(self):
        """Fill the grid with the cards named in the group's .home.json."""
        self._widgets_grid.controls.clear()
        for key in self._order():
            widget = self._widgets[key]
            widget.set_group(self._group)
            widget.set_edit_mode(self._edit_mode)
            self._widgets_grid.controls.append(self._wrap(key, widget))
        if self._edit_mode:
            self._widgets_grid.controls.append(self._add_tile())

    def _wrap(self, key: str, widget: HomeWidget) -> ft.GestureDetector:
        """Card plus the right-click menu used to reorder/remove it."""
        return ft.GestureDetector(
            content=widget,
            on_secondary_tap_down=lambda e, k=key: self._show_widget_menu(e, k),
        )

    def _add_tile(self) -> ft.Container:
        """Edit-mode-only cell that opens the widget picker."""
        return ft.Container(
            content=ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6,
                controls=[
                    ft.Icon(ft.Icons.ADD, color=ft.Colors.OUTLINE),
                    ft.Text("Widget hinzufügen", size=13, color=ft.Colors.OUTLINE),
                ],
            ),
            padding=ft.padding.symmetric(vertical=32, horizontal=16),
            border_radius=16,
            bgcolor=ft.Colors.SURFACE,
            border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
            ink=True,
            tooltip="Widget hinzufügen",
            on_click=self._open_picker,
        )

    def _available(self) -> list[tuple[str, str, str]]:
        """(key, title, icon) for every widget type not on the page yet."""
        shown = set(self._order())
        return [
            (key, cls.TITLE, _WIDGET_ICONS.get(key, ft.Icons.WIDGETS))
            for key, cls in _WIDGET_TYPES.items()
            if key not in shown
        ]

    def _open_picker(self, e=None):
        if self._picker is None:
            return
        self._picker.reset(self._available())
        self._picker.open = True
        self.page.update()

    def _show_widget_menu(self, e, key: str):
        """Right-click menu on a card: move up/down, remove (edit mode only)."""
        if not self._edit_mode or self._ctx_menu is None:
            return
        order = self._order()
        if key not in order:
            return
        index = order.index(key)
        # A card at either end gets a greyed-out entry, so the menu keeps the
        # same shape wherever it is opened.
        move_up = (lambda: self._move_widget(key, -1)) if index > 0 else None
        move_down = (
            (lambda: self._move_widget(key, +1))
            if index < len(order) - 1
            else None
        )
        self._ctx_menu.show(
            e.global_position.x,
            e.global_position.y,
            [
                ("Nach oben", ft.Icons.ARROW_UPWARD, ft.Colors.ON_SURFACE, move_up),
                ("Nach unten", ft.Icons.ARROW_DOWNWARD, ft.Colors.ON_SURFACE, move_down),
                (
                    "Entfernen",
                    ft.Icons.VISIBILITY_OFF,
                    ft.Colors.ERROR,
                    lambda: self._remove_widget(key),
                ),
            ],
        )

    def _move_widget(self, key: str, delta: int):
        self._home.move_widget(self._group, key, delta)
        self._rebuild_widgets()
        self.update()

    def _remove_widget(self, key: str):
        """Hide a widget again - its data stays in the .home.json."""
        self._home.remove_widget(self._group, key)
        self._rebuild_widgets()
        self.update()

    def _add_widget(self, key: str):
        self._home.add_widget(self._group, key)
        self._rebuild_widgets()
        self.update()
        if self._picker is not None:
            self._picker.reset(self._available())

    def _toggle_edit(self, e):
        self._set_edit_mode(not self._edit_mode)

    def _set_edit_mode(self, on: bool):
        """Show/hide every card's gear and label the toggle accordingly.

        Also rebuilds the grid, because the "add widget" tile only exists
        while editing.
        """
        self._edit_mode = on
        self._edit_button.text = "Fertig" if on else "Bearbeiten"
        self._edit_button.icon = ft.Icons.CHECK if on else ft.Icons.EDIT
        self._rebuild_widgets()
        self.update()

    #  inline TITLE editing 

    async def _start_title_edit(self, e):
        if self._group is None:  # Home / root has no folder to rename
            return
        self.title_field.value = self._group
        self._title_click.visible = False
        self.title_field.visible = True
        self.update()
        await self.title_field.focus()

    def _commit_title(self, e):
        if self._group is None:
            self._show_title_text("Home")
            self.update()
            return

        new_title = (self.title_field.value or "").strip()
        if not new_title or new_title == self._group:
            self._show_title_text(self._group)
            self.update()
            return

        if self._store.group_rename_conflict(self._group, new_title):
            # Refuse rather than clobber the other folder.
            self._show_title_text(self._group)
            self.update()
            self.show_error(f'"{new_title}" already exists.')
            return

        old_name = self._group
        try:
            new_name = self._store.rename_group(old_name, new_title)
        except Exception as ex:
            print(f"Rename failed: {ex}")
            self._show_title_text(self._group)
            self.update()
            return

        # Show the stored folder name: _safe_name may have dropped characters.
        self._group = new_name
        self._show_title_text(new_name)
        self.update()
        if self._on_group_renamed:
            self._on_group_renamed(old_name, new_name)

    def _show_title_text(self, value: str):
        self.title_text.value = value
        self._title_click.visible = True
        self.title_field.visible = False

    def show_error(self, message: str):
            self.page.show_snack_bar(ft.SnackBar(content=ft.Text(message)))
