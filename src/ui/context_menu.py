"""
ui/context_menu.py
------------------
Shared floating right-click context menu for use across the app.

Usage
-----
    menu = ContextMenu()
    page.overlay.append(menu)

    # on right-click (GestureDetector.on_secondary_tap_down):
    menu.show(e.global_position.x, e.global_position.y, [
        ("Rename", ft.Icons.DRIVE_FILE_RENAME_OUTLINE, ft.Colors.WHITE, rename_fn),
        ("Delete", ft.Icons.DELETE_OUTLINE, ft.Colors.RED_400, delete_fn),
    ])
"""

import flet as ft


class ContextMenu(ft.Container):
    """
    Lightweight floating context menu rendered in page.overlay.
    Positioned at cursor coordinates passed to .show().
    Dismisses itself when an item is selected.
    """

    def __init__(self):
        super().__init__()
        self._items_col = ft.Column(spacing=0, tight=True)
        self.visible = False
        self.left = 0
        self.top = 0
        self.bgcolor = ft.Colors.GREY_900
        self.border_radius = 8
        self.border = ft.Border.all(1, ft.Colors.OUTLINE_VARIANT)
        self.shadow = ft.BoxShadow(blur_radius=12, color=ft.Colors.BLACK_54)
        self.padding = ft.Padding.symmetric(vertical=4)
        self.content = self._items_col
        self.z_index = 9999

    def show(self, x: float, y: float, items: list[tuple]):
        """
        Display the menu at (x, y).

        items: list of (label: str, icon: ft.Icons, color, callback: callable)
        """
        self._items_col.controls.clear()
        for label, icon, color, cb in items:
            self._items_col.controls.append(
                ft.TextButton(
                    content=ft.Row(
                        spacing=10,
                        controls=[
                            ft.Icon(icon, size=16, color=color),
                            ft.Text(label, color=color, size=13),
                        ],
                    ),
                    style=ft.ButtonStyle(
                        padding=ft.Padding.symmetric(horizontal=14, vertical=6),
                        shape=ft.RoundedRectangleBorder(radius=0),
                        overlay_color=ft.Colors.WHITE_10,
                    ),
                    on_click=lambda e, fn=cb: self._select(fn),
                )
            )
        self.left = x
        self.top = y
        self.visible = True
        self.update()

    def hide(self):
        self.visible = False
        self.update()

    def _select(self, cb):
        self.hide()
        cb()
