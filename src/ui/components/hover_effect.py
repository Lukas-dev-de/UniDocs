"""Shared hover feedback for clickable tiles and rows.

Same feel as the sidebar module tiles: the control lifts a touch and gains a
rim in its own accent colour, so it reads as "under the cursor" without moving
the layout (the border is always there, just transparent when idle).
"""

from __future__ import annotations

import flet as ft

# Grow factor while the pointer is over a tile.
HOVER_SCALE = 1.05
ANIM = ft.Animation(140, ft.AnimationCurve.EASE_OUT)
RIM_WIDTH = 2
RIM_OPACITY = 0.55

# The idle border: present but invisible, so lighting it up cannot shift text.
IDLE_BORDER = ft.Border.all(RIM_WIDTH, ft.Colors.TRANSPARENT)


def hover_rim(color: str, opacity: float = RIM_OPACITY) -> ft.Border:
    """The rim a hovered control shows, in *color*."""
    return ft.Border.all(RIM_WIDTH, ft.Colors.with_opacity(opacity, color))


def attach_hover(
    control,
    *,
    body=None,
    rim_color: str = ft.Colors.PRIMARY,
    idle_border: ft.Border | None = IDLE_BORDER,
    scale: float = HOVER_SCALE,
):
    """Wire lift + rim onto *control*'s hover event and return it.

    *control* carries the scale, *body* (default: the control itself) the
    border.  ``idle_border`` is what the border falls back to on leave, so a
    selected tile can keep its own PRIMARY rim.
    """
    body = control if body is None else body
    control.animate_scale = ANIM
    control.scale = 1.0
    body.border = idle_border
    if getattr(body, "animate", None) is None:
        body.animate = ANIM
    hover_border = hover_rim(rim_color)

    def _handle_hover(e):
        hovered = str(e.data).lower() == "true"
        control.scale = scale if hovered else 1.0
        body.border = hover_border if hovered else idle_border
        control.update()

    control.on_hover = _handle_hover
    return control
