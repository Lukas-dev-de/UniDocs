import flet as ft
from models.module import Module
from ui.theme import on_color

# Hover feedback: the tile lifts a touch and gains a rim in its own text
# colour, so it reads as "under the cursor" without moving the layout.
_HOVER_SCALE = 1.05
_ANIM = ft.Animation(140, ft.AnimationCurve.EASE_OUT)

@ft.control
class ModuleTile(ft.IconButton):
    def __init__(self, module: Module, on_select=None):  # neu: on_select
        super().__init__()
        self.module = module
        self._on_select = on_select

        self.align = ft.Alignment.CENTER
        
        self.border_radius = 8
        self.bgcolor = module.color or ft.Colors.PRIMARY_CONTAINER
        # A module without a colour follows the theme; with a colour, that colour
        # becomes the tile background and the foreground is derived from it.
        foreground = (
            on_color(module.color) if module.color else ft.Colors.ON_PRIMARY_CONTAINER
        )
        self._hover_rim = ft.Colors.with_opacity(0.55, foreground)
        self.icon = module.icon
        self.tooltip = module.title
        self.on_click = self._handle_click 
        self.on_hover = self._handle_hover

        # Animated grow on hover (see _handle_hover).
        self.animate_scale = _ANIM
        self.scale = 1.0

        self.content = ft.Container(
            padding=16,
            # 2px rim, transparent when idle: the border is always there, so
            # lighting it up on hover cannot shift the text by a pixel.
            border=ft.Border.all(2, ft.Colors.TRANSPARENT),
            border_radius=6,
            animate=_ANIM,
            content=ft.Column(
                expand=True,
                controls=[
                    ft.Icon(module.icon, size=48, color=foreground),
                    ft.Text(
                        value=module.title,
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color=foreground,
                    ),
                    ft.Text(value=module.description, size=14, color=foreground),
                ],
            ),
        )

    def _handle_click(self, e):
        if self._on_select:
            self._on_select(self.module)

    def _handle_hover(self, e):
        hovered = str(e.data).lower() == "true"
        self.scale = _HOVER_SCALE if hovered else 1.0
        self.content.border = ft.Border.all(
            2, self._hover_rim if hovered else ft.Colors.TRANSPARENT
        )
        self.update()