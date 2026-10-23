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

There is no edit mode: everything hangs off the pencil button in the title row.
It opens the widget
manager - one row per widget type with a checkbox to show/hide it and a pencil to
open that widget's settings, which in turn has a "Zurück" button leading back
to the manager. Rows are shown in page order and can be dragged up/down to
change that order (HomeStore.set_widget_order). A right-click on a card offers
the same settings plus move up/down and "Ausblenden".

Hiding a widget only takes it off the page - its data stays in the .home.json,
so switching it back on restores the same content.

Documents are never listed here.

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


class _WidgetManagerDialog(ft.AlertDialog):
    """Lists every widget type with a show/hide checkbox and a settings button.

    The checkbox writes to the group's .home.json (``add_widget`` /
    ``remove_widget``), so hiding a card keeps its content. The pencil opens
    that widget's own settings dialog, which gets a "Zurück" button back here.
    """

    def __init__(self, on_toggle, on_edit, on_reorder):
        self._on_toggle = on_toggle
        self._on_edit = on_edit
        self._on_reorder = on_reorder
        # Widget keys in the order the rows are shown; kept in sync on drag.
        self._order: list[str] = []
        self._list = ft.ReorderableListView(
            height=340,
            spacing=0,
            show_default_drag_handles=False,
            on_reorder=self._handle_reorder,
        )
        super().__init__(
            modal=True,
            title=ft.Text("Widgets"),
            content=ft.Container(
                width=400,
                content=ft.Column(
                    spacing=6,
                    tight=True,
                    controls=[
                        ft.Text(
                            "Reihenfolge: am Griff rechts ziehen.",
                            size=11,
                            color=ft.Colors.OUTLINE,
                        ),
                        self._list,
                    ],
                ),
            ),
            actions=[ft.TextButton("Fertig", on_click=lambda e: self.close())],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    def reset(self, shown: list[str]):
        """Rebuild one row per widget type.

        *shown* are the keys on the page, already in page order: those come
        first, the hidden types follow in their default order. So the top of
        the list always mirrors what the user sees on the page.
        """
        order = [key for key in shown if key in _WIDGET_TYPES]
        order += [key for key in _WIDGET_TYPES if key not in order]
        self._order = order
        self._list.controls.clear()
        for key in order:
            self._list.controls.append(self._row(key, key in shown))

    def _row(self, key: str, on: bool) -> ft.Row:
        """One widget line: icon, show/hide checkbox, title, settings, grip."""
        cls = _WIDGET_TYPES[key]
        return ft.Row(
            spacing=4,
            opacity=1.0 if on else 0.55,
            controls=[
                ft.Icon(
                    _WIDGET_ICONS.get(key, ft.Icons.WIDGETS),
                    size=24,
                    color=ft.Colors.PRIMARY,
                ),
                # Checkbox instead of a switch: less visual weight in a list
                # of otherwise quiet rows.
                ft.Checkbox(
                    value=on,
                    tooltip="Auf der Seite anzeigen",
                    on_change=lambda e, k=key: self._on_toggle(k, e.control.value),
                ),
                ft.Text(cls.TITLE, size=13, expand=True),
                ft.IconButton(
                    icon=ft.Icons.EDIT,
                    icon_size=18,
                    tooltip="Einstellungen",
                    on_click=lambda e, k=key: self._on_edit(k),
                ),
                # Only the grip starts a drag, so a tap on the checkbox or
                # the pencil never moves the row by accident.
                ft.ReorderableDragHandle(
                    mouse_cursor=ft.MouseCursor.GRAB,
                    content=ft.Icon(
                        ft.Icons.DRAG_INDICATOR,
                        size=18,
                        color=ft.Colors.OUTLINE,
                    ),
                ),
            ],
        )

    def _handle_reorder(self, e: ft.OnReorderEvent):
        """Apply a drag to the row list and persist the new order."""
        old, new = e.old_index, e.new_index
        if old is None or new is None or old == new:
            return
        # Reorder both the controls (UI truth) and the key list (data truth)
        # the same way, so they cannot drift apart. The index is clamped,
        # because a drop below the last row may report "one past the end".
        for seq in (self._list.controls, self._order):
            if not 0 <= old < len(seq):
                continue
            item = seq.pop(old)
            seq.insert(min(max(new, 0), len(seq)), item)
        self._on_reorder(list(self._order))
        try:
            self._list.update()
        except RuntimeError:
            pass

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
        self._manager = None
        # "Zurück" buttons injected into widget settings dialogs, keyed by
        # widget key; created the first time the manager opens one.
        self._back_buttons: dict[str, ft.TextButton] = {}
        self._widgets_grid = ft.GridView(
            expand=True,
            max_extent=360,
            spacing=12,
            run_spacing=12,
        )
        # Always-visible way in: the pencil next to the title.
        self._add_button = ft.IconButton(
            icon=ft.Icons.EDIT,
            tooltip="Widgets bearbeiten",
            on_click=self._open_manager,
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
                        self._add_button,
                    ],
                ),
                ft.Divider(color=ft.Colors.OUTLINE_VARIANT),
                self._widgets_grid,
            ],
        )

    #  public 

    def set_group(self, group: str | None):
        """Show the home page for *group* (``None`` = Home)."""
        self._group = group or None
        self._show_title_text(self._group or "Home")
        self._title_click.tooltip = "Rename group" if self._group else "Home"
        self._rebuild_widgets()
        self.update()

    def did_mount(self):
        page = self.page
        if page is None:
            return
        self._ctx_menu = ContextMenu()
        self._manager = _WidgetManagerDialog(
            on_toggle=self._toggle_widget,
            on_edit=self._open_widget_settings,
            on_reorder=self._reorder_widgets,
        )
        page.overlay.append(self._ctx_menu)
        page.overlay.append(self._manager)
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
            self._widgets_grid.controls.append(self._wrap(key, widget))
        if not self._widgets_grid.controls:
            self._widgets_grid.controls.append(self._empty_hint())

    def _wrap(self, key: str, widget: HomeWidget) -> ft.GestureDetector:
        """Card plus the right-click menu used to edit/move/hide it."""
        return ft.GestureDetector(
            content=widget,
            on_secondary_tap_down=lambda e, k=key: self._show_widget_menu(e, k),
        )

    def _empty_hint(self) -> ft.Container:
        """Shown when every widget is hidden, so the page is not blank."""
        return ft.Container(
            content=ft.Text(
                "Keine Widgets. Stift oben rechts.",
                size=13,
                color=ft.Colors.OUTLINE,
            ),
            padding=24,
            border_radius=16,
            border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
        )

    def _open_manager(self, e=None):
        """Open the widget list: pencil button in the title row."""
        if self._manager is None:
            return
        self._manager.reset(self._order())
        self._manager.open = True
        self.page.update()

    def _toggle_widget(self, key: str, on: bool):
        """Show/hide a widget type from the manager's checkbox.

        The dialog stays open so several types can be flipped in a row; the
        grid behind it is rebuilt immediately.
        """
        if on:
            self._home.add_widget(self._group, key)
        else:
            self._home.remove_widget(self._group, key)
        self._rebuild_widgets()
        self.update()

    def _reorder_widgets(self, order: list[str]):
        """Drag & drop in the manager: save the new page order.

        The manager also lists hidden types; only the keys that are on the
        page keep a position in the ``widgets`` list, so those are the ones
        written back. Hidden types stay hidden and keep their data.
        """
        shown = set(self._order())
        self._home.set_widget_order(self._group, [k for k in order if k in shown])
        self._rebuild_widgets()
        self.update()

    def _open_widget_settings(self, key: str):
        """Manager -> one widget's settings, with a way back to the manager."""
        if self._manager is not None:
            self._manager.open = False
        self._show_settings(key, with_back=True)

    def _open_card_settings(self, key: str):
        """Card right-click -> settings; there is no manager to go back to."""
        self._show_settings(key, with_back=False)

    def _show_settings(self, key: str, with_back: bool):
        """Open a widget's settings and add/show its "Zurück" button.

        The settings dialogs belong to the widgets themselves, so the back
        button is injected into their ``actions`` on first use and only made
        visible when the manager opened the dialog.
        """
        widget = self._widgets[key]
        widget.open_settings()
        back = self._back_buttons.get(key)
        if back is None and with_back:
            dialog = widget.settings_dialog()
            if dialog is not None:
                back = ft.TextButton(
                    "Zurück",
                    icon=ft.Icons.ARROW_BACK,
                    on_click=lambda e, k=key: self._back_to_manager(k),
                )
                back.visible = False
                self._back_buttons[key] = back
                dialog.actions = [back] + list(dialog.actions or [])
        if back is not None:
            back.visible = with_back
        self.page.update()

    def _back_to_manager(self, key: str):
        """Leave a widget's settings and return to the widget list."""
        dialog = self._widgets[key].settings_dialog()
        if dialog is not None:
            dialog.open = False
        back = self._back_buttons.get(key)
        if back is not None:
            back.visible = False
        self._open_manager()

    def _show_widget_menu(self, e, key: str):
        """Right-click menu on a card: settings, move, hide.

        Every entry is lambda-bound so the menu can be built once per open and
        still act on the card it was opened on.
        """
        if self._ctx_menu is None:
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
        items = []
        # "Widget bearbeiten" only for cards that have something to configure.
        # open_settings ignores the event, hence the lambda.
        widget = self._widgets[key]
        if widget.HAS_SETTINGS:
            items.append(
                (
                    "Widget bearbeiten",
                    ft.Icons.SETTINGS,
                    ft.Colors.ON_SURFACE,
                    lambda: self._open_card_settings(key),
                )
            )
        items += [
            ("Nach oben", ft.Icons.ARROW_UPWARD, ft.Colors.ON_SURFACE, move_up),
            ("Nach unten", ft.Icons.ARROW_DOWNWARD, ft.Colors.ON_SURFACE, move_down),
            (
                "Ausblenden",
                ft.Icons.VISIBILITY_OFF,
                ft.Colors.ERROR,
                lambda: self._remove_widget(key),
            ),
        ]
        self._ctx_menu.show(e.global_position.x, e.global_position.y, items)

    def _move_widget(self, key: str, delta: int):
        self._home.move_widget(self._group, key, delta)
        self._rebuild_widgets()
        self.update()

    def _remove_widget(self, key: str):
        """Hide a widget - its data stays in the .home.json.

        Nothing is deleted: the widget's options and its entries survive, so
        switching the type back on in the manager shows the same content.
        """
        self._home.remove_widget(self._group, key)
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
