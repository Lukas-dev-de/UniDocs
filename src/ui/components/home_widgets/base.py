"""
ui/components/home_widgets/base.py
----------------------------------
Base card for the widgets on a group's home page (see ui/group_home.py).

A widget is a rounded surface card with a title row and a body. In edit mode
the title row shows a gear that opens the widget's settings dialog; outside
edit mode the card is read-only (or plain interactive, e.g. ticking a todo).

Subclasses fill ``self.body`` in their ``__init__`` and override
:meth:`refresh` (rebuild from the store) and optionally :meth:`open_settings`.
"""

from __future__ import annotations

import flet as ft

from app_storage.home_store import HomeStore


@ft.control
class HomeWidget(ft.Container):
    # Title shown in the card header.
    TITLE = "Widget"
    # Key of the widget type in .home.json (namespaces the widget's options).
    TYPE = ""
    # False hides the gear even in edit mode (nothing to configure).
    HAS_SETTINGS = True

    def __init__(self, store: HomeStore, module_store=None, on_open_module=None):
        super().__init__()

        self._store = store
        # The module store lets "recent modules" look up live Module objects
        # for the current group; widgets that only need .home.json ignore it.
        self._modules = module_store
        self._on_open_module = on_open_module
        # Folder name of the group on screen; ``None`` = Home.
        self._group: str | None = None
        self._edit_mode = False

        self.border_radius = 16
        # The home page itself paints SURFACE, so the card takes the next
        # elevation step up ("raised") to stand out from it in both modes.
        # Its inner items use SURFACE_CONTAINER_HIGHEST, one step above this.
        self.bgcolor = ft.Colors.SURFACE_CONTAINER_HIGH
        self.border = ft.border.all(1, ft.Colors.OUTLINE_VARIANT)
        self.padding = 16

        self._settings_btn = ft.IconButton(
            icon=ft.Icons.SETTINGS,
            icon_size=18,
            tooltip="Einstellungen",
            visible=False,
            on_click=self.open_settings,
        )
        # Title-row buttons; subclasses may insert their own in front of the
        # gear (e.g. the calendar's "maximize").
        self._actions_row = ft.Row(spacing=0, controls=[self._settings_btn])
        self.body = ft.Column(spacing=8, expand=True)
        self.content = ft.Column(
            spacing=8,
            expand=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(self.TITLE, size=16, weight=ft.FontWeight.BOLD),
                        self._actions_row,
                    ],
                ),
                self.body,
            ],
        )

    #  public 

    def set_group(self, group: str | None):
        """Point the widget at *group* (``None`` = Home) and reload its data."""
        self._group = group
        self.refresh()

    def set_edit_mode(self, on: bool):
        self._edit_mode = on
        self._settings_btn.visible = on and self.HAS_SETTINGS

    def refresh(self):
        """Rebuild the body from the store. Subclasses override.

        Must not call ``update()`` itself: the home page calls it once after
        refreshing every card, which also works before the page is mounted.
        """

    def open_settings(self, e):
        """Open the widget's settings dialog. Subclasses override."""

    #  options 

    def get_option(self, key: str, default=None):
        """Read one of this card's options from the group's .home.json.

        Options are keyed by widget type (``HomeWidget.TYPE``), so two cards
        never clash. A missing key yields *default*.
        """
        return self._store.get_widget_options(self._group, self.TYPE).get(key, default)

    def set_option(self, key: str, value) -> None:
        """Persist one of this card's options (leaves the other keys alone)."""
        self._store.set_widget_option(self._group, self.TYPE, key, value)

    #  helpers 

    def placeholder(self, text: str) -> ft.Text:
        """Grey one-liner used while a widget has nothing to show."""
        return ft.Text(text, size=13, color=ft.Colors.OUTLINE)

    @staticmethod
    def _safe_update(control) -> None:
        """``update()`` a control that may not be on the page yet."""
        try:
            control.update()
        except RuntimeError:
            pass

    def _page(self):
        """The host page, or ``None`` while the card is not mounted yet."""
        try:
            return self.page
        except RuntimeError:
            return None
