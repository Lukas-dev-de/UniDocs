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
        ("Rename", ft.Icons.DRIVE_FILE_RENAME_OUTLINE, ft.Colors.ON_SURFACE, rename_fn),
        ("Delete", ft.Icons.DELETE_OUTLINE, ft.Colors.ERROR, delete_fn),
    ])
"""

import flet as ft

class ContextMenu(ft.Stack):
    def __init__(self):
        super().__init__()
        self.visible = False
        self.z_index = 9999
        
        self._items_col = ft.Column(spacing=0, tight=True)

        self.menu_container = ft.Container(
            content=self._items_col,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=8,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            shadow=ft.BoxShadow(blur_radius=12, color=ft.Colors.SHADOW),
            padding=ft.Padding.symmetric(vertical=4),
            left=0,
            top=0,
        )

        # full-screen click catcher
        self.scrim = ft.Container(
            expand=True,
            bgcolor=ft.Colors.TRANSPARENT,
            on_click=lambda e: self.hide(),
        )

        self.controls = [self.scrim, self.menu_container]

    def show(self, x: float, y: float, items: list[tuple]):
        """*items* are ``(label, icon, color, callback)`` tuples.

        A ``callback`` of ``None`` renders the entry dimmed and unclickable,
        which is how a caller shows an action that is unavailable where the
        menu was opened ("Move up" on the module that is already first).
        """
        self._items_col.controls.clear()

        for label, icon, color, cb in items:
            enabled = cb is not None
            # Leave the colour unset when disabled so the children inherit the
            # button's own greyed-out foreground instead of fighting it.
            tint = color if enabled else None
            self._items_col.controls.append(
                ft.TextButton(
                    content=ft.Row(
                        spacing=10,
                        controls=[
                            ft.Icon(icon, size=16, color=tint),
                            ft.Text(label, color=tint, size=13),
                        ],
                    ),
                    disabled=not enabled,
                    on_click=lambda e, fn=cb: self._select(fn),
                )
            )

        self.menu_container.left = x
        self.menu_container.top = y

        self.visible = True
        self.update()

    def hide(self):
        self.visible = False
        self.update()

    def _select(self, cb):
        self.hide()
        if cb is not None:
            cb()
