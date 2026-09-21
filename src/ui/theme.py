"""
ui/theme.py
-----------
Central theme definitions and runtime switching for UniDocs.

Design
------
* A **palette** is a named colour family that ships a light and a dark variant.
* Widgets never hardcode colours. They use Flet's *semantic* colour tokens
  (``ft.Colors.SURFACE``, ``ON_SURFACE_VARIANT``, ``PRIMARY``, ``ERROR`` ...).
  Flet resolves those against the active ``ColorScheme`` while rendering, so
  switching theme at runtime repaints the whole UI without rebuilding a single
  widget.
* ``ThemeManager`` owns the active palette + appearance mode, pushes them onto
  the ``Page`` and persists the selection through ``AppConfig``.

Usage
-----
    theme = ThemeManager(cfg)
    theme.attach(page)          # applies the stored palette + mode
    theme.set_palette("nord")   # persists and repaints immediately
    theme.set_mode("dark")
"""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from app_storage.app_config import AppConfig

DEFAULT_PALETTE = "unidocs"
DEFAULT_MODE = "system"

MODES: dict[str, ft.ThemeMode] = {
    "system": ft.ThemeMode.SYSTEM,
    "light": ft.ThemeMode.LIGHT,
    "dark": ft.ThemeMode.DARK,
}

MODE_LABELS: dict[str, str] = {
    "system": "System",
    "light": "Light",
    "dark": "Dark",
}


# ---------------------------------------------------------------------------
# colour helpers
# ---------------------------------------------------------------------------

def _rgb(color: str) -> tuple[int, int, int]:
    h = str(color).lstrip("#")
    if len(h) == 3:                      # #abc -> #aabbcc
        h = "".join(ch * 2 for ch in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def mix(a: str, b: str, t: float) -> str:
    """Blend ``a`` towards ``b`` (``t``: 0 -> a, 1 -> b)."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(round(x + (y - x) * t) for x, y in zip(ra, rb)))


def _luminance(color: str) -> float:
    r, g, b = _rgb(color)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def on_color(background: str) -> str:
    """Best black/white foreground for ``background``.

    Used where a colour is *data* (e.g. a user-chosen tag colour) rather than
    a theme role, so the text stays readable whatever the tag looks like.

    Non-hex input (a ``ft.Colors`` token, ``None``, ...) falls back to white,
    which matches the dark pill background used in that case.
    """
    try:
        luminance = _luminance(background)
    except (ValueError, AttributeError, TypeError):
        return "#FFFFFF"
    return "#000000" if luminance > 0.55 else "#FFFFFF"


# ---------------------------------------------------------------------------
# palette definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Variant:
    """The handful of role colours that define one appearance."""

    surface: str              # page / sidebar background
    surface_raised: str       # cards, tiles, chips
    primary: str              # accent
    primary_container: str    # tinted surfaces (sidebar tiles)
    on_surface: str           # primary text
    on_surface_variant: str   # secondary text
    error: str                # destructive / errors


@dataclass(frozen=True)
class Palette:
    id: str
    label: str
    light: Variant
    dark: Variant

    def variant(self, dark: bool) -> Variant:
        return self.dark if dark else self.light

    def scheme(self, dark: bool) -> ft.ColorScheme:
        return _build_scheme(self.variant(dark), dark=dark)


def _build_scheme(v: Variant, *, dark: bool) -> ft.ColorScheme:
    """Expand a compact ``Variant`` into a full Material 3 ``ColorScheme``."""
    surface = v.surface
    raised = v.surface_raised

    # Elevation ladder: each step blends a little further towards the
    # foreground colour so containers gain prominence as they "rise".
    lift = 0.03 if dark else 0.04
    container_lowest = mix(surface, v.on_surface, lift * 0.5)
    container_low = mix(surface, v.on_surface, lift)
    container = mix(surface, v.on_surface, lift * 2)
    container_highest = mix(raised, v.on_surface, lift * 2)

    secondary = mix(v.primary, v.on_surface_variant, 0.55)
    secondary_container = mix(v.primary_container, v.on_surface_variant, 0.35)
    error_container = mix(v.error, surface, 0.8)

    if dark:
        surface_dim = mix(surface, "#000000", 0.2)
        surface_bright = mix(surface, "#FFFFFF", 0.06)
    else:
        surface_dim = mix(surface, "#000000", 0.06)
        surface_bright = "#FFFFFF"

    return ft.ColorScheme(
        primary=v.primary,
        on_primary=on_color(v.primary),
        primary_container=v.primary_container,
        on_primary_container=on_color(v.primary_container),
        secondary=secondary,
        on_secondary=on_color(secondary),
        secondary_container=secondary_container,
        on_secondary_container=on_color(secondary_container),
        tertiary=v.primary,
        on_tertiary=on_color(v.primary),
        tertiary_container=secondary_container,
        on_tertiary_container=on_color(secondary_container),
        error=v.error,
        on_error=on_color(v.error),
        error_container=error_container,
        on_error_container=mix(v.error, v.on_surface, 0.35),
        surface=surface,
        on_surface=v.on_surface,
        on_surface_variant=v.on_surface_variant,
        outline=mix(v.on_surface, surface, 0.45),
        outline_variant=mix(v.on_surface, surface, 0.8),
        shadow="#000000",
        scrim="#000000",
        inverse_surface=v.on_surface,
        on_inverse_surface=surface,
        inverse_primary=mix(v.primary, v.on_surface, 0.25),
        surface_tint=v.primary,
        surface_dim=surface_dim,
        surface_bright=surface_bright,
        surface_container_lowest=container_lowest,
        surface_container_low=container_low,
        surface_container=container,
        surface_container_high=raised,
        surface_container_highest=container_highest,
    )


PALETTES: dict[str, Palette] = {}


def _register(palette: Palette) -> None:
    PALETTES[palette.id] = palette


_register(Palette(
    id="unidocs",
    label="UniDocs Blue",
    light=Variant(
        surface="#F6F8FB",
        surface_raised="#E7EDF6",
        primary="#1A5FB4",
        primary_container="#D3E2F7",
        on_surface="#11181F",
        on_surface_variant="#4C5866",
        error="#C62828",
    ),
    dark=Variant(
        surface="#0F141A",
        surface_raised="#1A222C",
        primary="#7EB6FF",
        primary_container="#1B3557",
        on_surface="#E4E8EE",
        on_surface_variant="#9DA9B6",
        error="#FF6B6B",
    ),
))

_register(Palette(
    id="nord",
    label="Nord",
    light=Variant(
        surface="#ECEFF4",
        surface_raised="#DEE4EE",
        primary="#5E81AC",
        primary_container="#D8DEE9",
        on_surface="#2E3440",
        on_surface_variant="#4C566A",
        error="#BF616A",
    ),
    dark=Variant(
        surface="#2E3440",
        surface_raised="#3B4252",
        primary="#88C0D0",
        primary_container="#434C5E",
        on_surface="#ECEFF4",
        on_surface_variant="#A9B4C4",
        error="#BF616A",
    ),
))

_register(Palette(
    id="dracula",
    label="Dracula",
    light=Variant(
        surface="#F8F8F5",
        surface_raised="#EAEAF2",
        primary="#7C4DFF",
        primary_container="#E1D9F8",
        on_surface="#23222C",
        on_surface_variant="#55536B",
        error="#C2364B",
    ),
    dark=Variant(
        surface="#282A36",
        surface_raised="#343746",
        primary="#BD93F9",
        primary_container="#44475A",
        on_surface="#F8F8F2",
        on_surface_variant="#B0B3C6",
        error="#FF5555",
    ),
))

_register(Palette(
    id="solarized",
    label="Solarized",
    light=Variant(
        surface="#FDF6E3",
        surface_raised="#F0E8D2",
        primary="#1F7FBF",
        primary_container="#DCE8F2",
        on_surface="#3B4A50",
        on_surface_variant="#6B7F85",
        error="#DC322F",
    ),
    dark=Variant(
        surface="#002B36",
        surface_raised="#07414F",
        primary="#4FB3E8",
        primary_container="#0A4C5E",
        on_surface="#B9C9C9",
        on_surface_variant="#8299A0",
        error="#FF6E67",
    ),
))

_register(Palette(
    id="mono",
    label="Monochrome",
    light=Variant(
        surface="#FAFAFA",
        surface_raised="#EFEFEF",
        primary="#37474F",
        primary_container="#E0E4E7",
        on_surface="#1B1B1B",
        on_surface_variant="#5A5A5A",
        error="#C62828",
    ),
    dark=Variant(
        surface="#101012",
        surface_raised="#1C1C1F",
        primary="#DCDCDC",
        primary_container="#2C2C31",
        on_surface="#EDEDED",
        on_surface_variant="#9A9A9F",
        error="#FF6B6B",
    ),
))


# ---------------------------------------------------------------------------
# manager
# ---------------------------------------------------------------------------

class ThemeManager:
    """Owns the active palette / appearance mode and keeps a ``Page`` in sync."""

    def __init__(self, config: AppConfig | None = None):
        self._cfg = config or AppConfig()
        self._page: ft.Page | None = None
        self._palette_id = self._cfg.theme_palette
        self._mode = self._cfg.theme_mode

    #  state 

    @property
    def attached(self) -> bool:
        return self._page is not None

    @property
    def palette_id(self) -> str:
        return self._palette_id if self._palette_id in PALETTES else DEFAULT_PALETTE

    @property
    def palette(self) -> Palette:
        return PALETTES[self.palette_id]

    @property
    def mode(self) -> str:
        return self._mode if self._mode in MODES else DEFAULT_MODE

    #  wiring 

    def attach(self, page: ft.Page) -> None:
        """Bind to a page and apply the stored theme immediately."""
        self._page = page
        self.apply()

    def apply(self) -> None:
        """Push the active palette + mode onto the page."""
        page = self._page
        if page is None:
            return

        palette = self.palette
        page.theme = ft.Theme(
            color_scheme=palette.scheme(dark=False),
            use_material3=True,
        )
        page.dark_theme = ft.Theme(
            color_scheme=palette.scheme(dark=True),
            use_material3=True,
        )
        page.theme_mode = MODES[self.mode]
        page.update()

    #  mutations (persisted) 

    def set_palette(self, palette_id: str) -> None:
        if palette_id not in PALETTES or palette_id == self._palette_id:
            return
        self._palette_id = palette_id
        self._cfg.theme_palette = palette_id
        self.apply()

    def set_mode(self, mode: str) -> None:
        if mode not in MODES or mode == self._mode:
            return
        self._mode = mode
        self._cfg.theme_mode = mode
        self.apply()
