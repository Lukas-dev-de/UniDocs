"""
ui/components/color_selector.py
-------------------------------
Swatch picker for module accent colours.

Mirrors :class:`ui.components.icon_selector.IconSelector`: a small trigger that
previews the current colour and opens a popup grid of swatches.

    selector = ColorSelector(on_change=...)
    selector.value          # "#1A5FB4" or None for "follow the theme"
    selector.set_value("#2E7D32")
    selector.reset()        # back to no colour
"""

import flet as ft

from ui.theme import MODULE_COLORS, on_color


class ColorSelector(ft.Container):
    def __init__(
        self,
        colors: list[tuple[str, str]] | None = None,
        swatch_size: int = 22,
        columns: int = 4,
        on_change=None,
        **kwargs,
    ):
        kwargs.pop("value", None)
        super().__init__(**kwargs)

        self._colors = colors or MODULE_COLORS
        self._swatch_size = swatch_size
        self._columns = columns
        self._on_change = on_change

        self._selected: str | None = None

        #  trigger 
        self._preview = ft.Container(
            width=swatch_size,
            height=swatch_size,
            border_radius=4,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        )

        self._trigger = ft.Container(
            content=self._preview,
            width=swatch_size + 16,
            height=swatch_size + 16,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=6,
            tooltip="Select color",
        )

        #  popup 
        self._grid_column = ft.Column(spacing=2, tight=True)

        popup_content = ft.Container(
            width=180,
            padding=10,
            content=ft.Column(
                spacing=8,
                tight=True,
                controls=[
                    self._grid_column,
                    ft.TextButton(
                        "Use theme color",
                        icon=ft.Icons.FORMAT_COLOR_RESET,
                        on_click=lambda e: self._clear(),
                    ),
                ],
            ),
        )

        self._grid = ft.PopupMenuButton(
            content=self._trigger,
            menu_position=ft.PopupMenuPosition.UNDER,
            items=[ft.PopupMenuItem(content=popup_content)],
        )

        self.content = self._grid

        self._refresh_grid()
        self._update_preview()

    #  rendering 

    def _swatch(self, label: str, value: str) -> ft.Container:
        is_selected = self._selected == value
        return ft.Container(
            content=ft.Container(
                width=self._swatch_size,
                height=self._swatch_size,
                bgcolor=value,
                border_radius=4,
            ),
            padding=2,
            border_radius=6,
            border=ft.Border.all(2, ft.Colors.PRIMARY) if is_selected else None,
            tooltip=label,
            on_click=lambda e, v=value: self._select(v),
        )

    def _refresh_grid(self) -> None:
        rows = []
        for i in range(0, len(self._colors), self._columns):
            chunk = self._colors[i : i + self._columns]
            rows.append(
                ft.Row(
                    spacing=2,
                    controls=[self._swatch(label, value) for label, value in chunk],
                )
            )

        self._grid_column.controls = rows
        try:
            self._grid_column.update()
        except RuntimeError:
            pass

    def _update_preview(self) -> None:
        self._preview.bgcolor = self._selected
        if self._selected:
            self._preview.content = None
            self._preview.border = ft.Border.all(1, ft.Colors.OUTLINE_VARIANT)
        else:
            self._preview.content = ft.Icon(
                ft.Icons.PALETTE,
                size=self._swatch_size - 8,
                color=ft.Colors.OUTLINE,
            )
        self._trigger.tooltip = self._selected or "No color (follows theme)"
        try:
            self._trigger.update()
        except RuntimeError:
            pass

    #  interaction 

    def _select(self, value: str) -> None:
        self._selected = value
        self._update_preview()
        self._refresh_grid()
        if self._on_change:
            self._on_change(value)

    def _clear(self) -> None:
        self._selected = None
        self._update_preview()
        self._refresh_grid()
        if self._on_change:
            self._on_change(None)

    #  api 

    def set_value(self, color: str | None) -> None:
        """Show *color* without firing ``on_change``."""
        self._selected = color
        self._update_preview()
        self._refresh_grid()

    def reset(self) -> None:
        self.set_value(None)

    @property
    def value(self) -> str | None:
        return self._selected
