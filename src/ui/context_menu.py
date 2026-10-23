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

import asyncio

import flet as ft

# Pop-in when the menu is opened: it fades and grows from the cursor corner.
_POP_IN = ft.Animation(120, ft.AnimationCurve.EASE_OUT)
_POP_SCALE = ft.Scale(scale=0.94, alignment=ft.Alignment.TOP_LEFT)
_POP_OPEN_SCALE = ft.Scale(scale=1.0, alignment=ft.Alignment.TOP_LEFT)
# One frame (16 ms) is enough for the client to build the menu in its closed
# state; only then does changing opacity/scale animate instead of snap.
_POP_FRAME = 0.016

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
            opacity=0.0,
            scale=_POP_SCALE,
            animate_opacity=_POP_IN,
            animate_scale=_POP_IN,
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

        # Start from the "closed" state so every open animates, not just the
        # first one. The 0-opacity frame is invisible, so no flicker.
        self.menu_container.opacity = 0.0
        self.menu_container.scale = _POP_SCALE
        self.visible = True
        self.update()

        # A hidden control is built fresh on the client, so setting the target
        # values in the same batch would just render it open - no transition.
        # Animating one frame later gives the client time to show the closed
        # state first.
        page = self.page
        if page is not None:
            page.run_task(self._play_pop_in)
        else:
            self._open_now()

    def _open_now(self):
        self.menu_container.opacity = 1.0
        self.menu_container.scale = _POP_OPEN_SCALE
        self.update()

    async def _play_pop_in(self):
        await asyncio.sleep(_POP_FRAME)
        self._open_now()

    def hide(self):
        self.visible = False
        self.update()

    def _select(self, cb):
        self.hide()
        if cb is not None:
            cb()
