"""
ui/components/icon_selector.py
------------------------------
Icon picker for modules.

A small trigger box previews the current icon; clicking it opens a modal
picker (``AlertDialog``) with a search field and a grid grouped into
categories. Picking an icon closes the dialog and fires ``on_change``.

    selector = IconSelector(on_change=...)
    selector.value              # the chosen icon name, or None
    selector.set_value(ft.Icons.SCHOOL)   # set silently, no on_change
    selector.reset()            # back to no icon

Icons are grouped by theme so the list stays browsable; the search field
still matches across every category. More icons:
https://examples.flet.dev/icons_browser/
"""

import flet as ft

# Icons per row in the popup grid, and their size in pixels.
ICON_COLUMNS = 8
ICON_SIZE = 26

# (category title, [(label, icon)]) in the order they are shown.
CATEGORIES: list[tuple[str, list[tuple[str, str]]]] = [
    ("Study & Writing", [
        ("Article", ft.Icons.ARTICLE),
        ("Assignment", ft.Icons.ASSIGNMENT),
        ("Auto Stories", ft.Icons.AUTO_STORIES),
        ("Sticky Note", ft.Icons.STICKY_NOTE_2_ROUNDED),
        ("Desk", ft.Icons.DESK),
        ("Newspaper", ft.Icons.NEWSPAPER),
        ("Translate", ft.Icons.TRANSLATE_ROUNDED),
        ("Library", ft.Icons.LOCAL_LIBRARY_ROUNDED),
        ("School", ft.Icons.SCHOOL),
        ("Backup Table", ft.Icons.BACKUP_TABLE_ROUNDED),
    ]),
    ("Science & Health", [
        ("Biotech", ft.Icons.BIOTECH),
        ("Vaccines", ft.Icons.VACCINES),
        ("Heart Monitor", ft.Icons.MONITOR_HEART),
        ("Hospital", ft.Icons.LOCAL_HOSPITAL_ROUNDED),
        ("Thermostat", ft.Icons.DEVICE_THERMOSTAT),
        ("CO2", ft.Icons.CO2),
        ("Manufacturing", ft.Icons.PRECISION_MANUFACTURING),
    ]),
    ("Finance & Business", [
        ("Bank", ft.Icons.ACCOUNT_BALANCE),
        ("Account Tree", ft.Icons.ACCOUNT_TREE_OUTLINED),
        ("Balance", ft.Icons.BALANCE),
        ("Business Center", ft.Icons.BUSINESS_CENTER),
        ("Business", ft.Icons.BUSINESS),
        ("Calculator", ft.Icons.CALCULATE),
        ("Bitcoin", ft.Icons.CURRENCY_BITCOIN),
        ("Discount", ft.Icons.DISCOUNT),
        ("Money", ft.Icons.MONETIZATION_ON_OUTLINED),
        ("Percent", ft.Icons.PERCENT),
        ("Gavel", ft.Icons.GAVEL),
        ("Apartment", ft.Icons.APARTMENT),
    ]),
    ("Charts & Data", [
        ("Analytics", ft.Icons.ANALYTICS),
        ("Area Chart", ft.Icons.AREA_CHART),
        ("Bar Chart", ft.Icons.BAR_CHART),
        ("Bubble Chart", ft.Icons.BUBBLE_CHART_OUTLINED),
        ("Candlestick Chart", ft.Icons.CANDLESTICK_CHART),
        ("Pie Chart", ft.Icons.PIE_CHART),
        ("Assessment", ft.Icons.ASSESSMENT),
        ("Data Array", ft.Icons.DATA_ARRAY),
        ("Data Exploration", ft.Icons.DATA_EXPLORATION),
        ("Data Object", ft.Icons.DATA_OBJECT),
        ("Dataset", ft.Icons.DATASET),
        ("Functions", ft.Icons.FUNCTIONS),
        ("Legend Toggle", ft.Icons.LEGEND_TOGGLE_ROUNDED),
        ("Dashboard", ft.Icons.DASHBOARD),
        ("Exposure", ft.Icons.EXPOSURE),
        ("Numbers", ft.Icons.NUMBERS),
    ]),
    ("Tech & Code", [
        ("Code", ft.Icons.CODE),
        ("Javascript", ft.Icons.JAVASCRIPT),
        ("Developer Board", ft.Icons.DEVELOPER_BOARD),
        ("Device Hub", ft.Icons.DEVICE_HUB),
        ("DNS", ft.Icons.DNS_ROUNDED),
        ("Memory", ft.Icons.MEMORY),
        ("Hub", ft.Icons.HUB),
        ("LAN", ft.Icons.LAN_ROUNDED),
        ("Https", ft.Icons.HTTPS),
        ("Cable", ft.Icons.CABLE),
        ("Computer", ft.Icons.COMPUTER),
        ("Monitor", ft.Icons.MONITOR),
        ("Key", ft.Icons.KEY_OUTLINED),
        ("Keyboard Option Key", ft.Icons.KEYBOARD_OPTION_KEY),
        ("Import Export", ft.Icons.IMPORT_EXPORT),
        ("Link", ft.Icons.INSERT_LINK),
        ("Perm Data Setting", ft.Icons.PERM_DATA_SETTING),
        ("Data Saver Off", ft.Icons.DATA_SAVER_OFF),
        ("Electric Bolt", ft.Icons.ELECTRIC_BOLT),
        ("Bolt", ft.Icons.BOLT),
        ("All Inbox", ft.Icons.ALL_INBOX),
        ("Email", ft.Icons.EMAIL),
        ("Chat", ft.Icons.CHAT),
        ("Campaign", ft.Icons.CAMPAIGN),
    ]),
    ("Media & Music", [
        ("Audiotrack", ft.Icons.AUDIOTRACK),
        ("Art Track", ft.Icons.ART_TRACK),
        ("Collections", ft.Icons.COLLECTIONS_OUTLINED),
        ("Color Lens", ft.Icons.COLOR_LENS_OUTLINED),
        ("Camera", ft.Icons.CAMERA),
        ("Videocam", ft.Icons.VIDEOCAM_ROUNDED),
        ("Movie", ft.Icons.MOVIE),
        ("Local Movies", ft.Icons.LOCAL_MOVIES_OUTLINED),
        ("Library Music", ft.Icons.LIBRARY_MUSIC),
        ("Headphones", ft.Icons.HEADPHONES),
        ("Graphic Eq", ft.Icons.GRAPHIC_EQ),
        ("Piano", ft.Icons.PIANO),
        ("Radio", ft.Icons.RADIO),
        ("Mic External On", ft.Icons.MIC_EXTERNAL_ON),
        ("Keyboard Voice", ft.Icons.KEYBOARD_VOICE_OUTLINED),
        ("Nightlife", ft.Icons.NIGHTLIFE_ROUNDED),
        ("Style", ft.Icons.STYLE),
        ("Brush", ft.Icons.BRUSH),
        ("Border Color", ft.Icons.BORDER_COLOR_ROUNDED),
        ("Gesture", ft.Icons.GESTURE),
    ]),
    ("Food & Drink", [
        ("Coffee", ft.Icons.COFFEE),
        ("Cafe", ft.Icons.LOCAL_CAFE_OUTLINED),
        ("Food", ft.Icons.EMOJI_FOOD_BEVERAGE),
        ("Ramen Dining", ft.Icons.RAMEN_DINING_OUTLINED),
        ("Bar", ft.Icons.LOCAL_BAR),
        ("Drink", ft.Icons.LOCAL_DRINK_OUTLINED),
        ("Cookie", ft.Icons.COOKIE),
    ]),
    ("Nature & Places", [
        ("Eco", ft.Icons.ECO_OUTLINED),
        ("Compost", ft.Icons.COMPOST),
        ("Grass", ft.Icons.GRASS),
        ("Wind Power", ft.Icons.WIND_POWER),
        ("Fire Department", ft.Icons.LOCAL_FIRE_DEPARTMENT),
        ("Filter Hdr", ft.Icons.FILTER_HDR),
        ("Landscape", ft.Icons.LANDSCAPE_ROUNDED),
        ("Villa", ft.Icons.VILLA_OUTLINED),
        ("Church", ft.Icons.CHURCH),
    ]),
    ("Travel & Leisure", [
        ("Flight", ft.Icons.FLIGHT),
        ("Explore", ft.Icons.EXPLORE),
        ("Language", ft.Icons.LANGUAGE),
        ("Flag", ft.Icons.FLAG),
        ("Hotel Class", ft.Icons.HOTEL_CLASS_OUTLINED),
        ("Family Restroom", ft.Icons.FAMILY_RESTROOM),
        ("Offer", ft.Icons.LOCAL_OFFER_OUTLINED),
        ("Interests", ft.Icons.INTERESTS_OUTLINED),
    ]),
    ("Tools & Building", [
        ("Build", ft.Icons.BUILD),
        ("Construction", ft.Icons.CONSTRUCTION),
        ("Handyman", ft.Icons.HANDYMAN),
        ("Carpenter", ft.Icons.CARPENTER),
        ("Architecture", ft.Icons.ARCHITECTURE),
        ("Engineering", ft.Icons.ENGINEERING),
        ("Electrical Services", ft.Icons.ELECTRICAL_SERVICES),
        ("Home Repair", ft.Icons.HOME_REPAIR_SERVICE),
        ("Miscellaneous Services", ft.Icons.MISCELLANEOUS_SERVICES),
        ("Design Services", ft.Icons.DESIGN_SERVICES),
        ("Factory", ft.Icons.FACTORY),
        ("Conveyor Belt", ft.Icons.CONVEYOR_BELT),
        ("Shelves", ft.Icons.SHELVES),
        ("Widgets", ft.Icons.WIDGETS_OUTLINED),
        ("Extension", ft.Icons.EXTENSION),
        ("Category", ft.Icons.CATEGORY),
        ("Category Outlined", ft.Icons.CATEGORY_OUTLINED),
        ("Cut", ft.Icons.CONTENT_CUT),
    ]),
    ("Life & Fun", [
        ("Favorite", ft.Icons.FAVORITE),
        ("Favorite Border", ft.Icons.FAVORITE_BORDER),
        ("Fitness Center", ft.Icons.FITNESS_CENTER),
        ("Basketball", ft.Icons.SPORTS_BASKETBALL),
        ("Casino", ft.Icons.CASINO),
        ("Catching Pokemon", ft.Icons.CATCHING_POKEMON),
        ("Videogame Asset", ft.Icons.VIDEOGAME_ASSET),
        ("Diversity", ft.Icons.DIVERSITY_1),
        ("Cruelty Free", ft.Icons.CRUELTY_FREE_OUTLINED),
        ("Emoji Objects", ft.Icons.EMOJI_OBJECTS),
        ("Emoji Symbols", ft.Icons.EMOJI_SYMBOLS),
    ]),
    ("General", [
        ("Calendar Month", ft.Icons.CALENDAR_MONTH),
        ("Hourglass", ft.Icons.HOURGLASS_EMPTY_ROUNDED),
        ("Tips And Updates", ft.Icons.TIPS_AND_UPDATES),
        ("Diamond", ft.Icons.DIAMOND),
        ("Auto Awesome", ft.Icons.AUTO_AWESOME_OUTLINED),
        ("Incomplete Circle", ft.Icons.INCOMPLETE_CIRCLE),
        ("Lens Blur", ft.Icons.LENS_BLUR),
        ("Pattern", ft.Icons.PATTERN),
    ]),
]


class IconSelector(ft.Container):
    """Trigger box + modal picker for choosing a module icon."""

    def __init__(
        self,
        icons: list[tuple[str, str]] | None = None,
        icon_size: int = ICON_SIZE,
        columns: int = ICON_COLUMNS,
        on_change=None,
        **kwargs,
    ):
        kwargs.pop("value", None)
        super().__init__(**kwargs)

        # A caller-supplied flat list is shown as one unnamed group; the
        # grouped default comes from CATEGORIES.
        if icons:
            self._categories = [(None, list(icons))]
        else:
            self._categories = CATEGORIES
        self._all_icons = [entry for _, entries in self._categories for entry in entries]

        self._icon_size = icon_size
        self._columns = columns
        self._on_change = on_change

        self._selected: str | None = None

        #  trigger 
        self._selected_icon_display = ft.Icon(ft.Icons.STAR, size=icon_size)

        self._trigger = ft.Container(
            content=self._selected_icon_display,
            width=icon_size + 16,
            height=icon_size + 16,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=6,
            tooltip="Select icon",
            ink=True,
            on_click=self._open_picker,
        )

        #  picker 
        self._search_field = ft.TextField(
            hint_text="Search icons…",
            dense=True,
            autofocus=False,
            prefix_icon=ft.Icons.SEARCH,
            on_change=self._on_search,
        )

        self._grid_column = ft.Column(
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            height=380,
        )

        self._dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                spacing=8,
                controls=[
                    ft.Icon(ft.Icons.CATEGORY_OUTLINED, size=20),
                    ft.Text("Choose an icon", size=18, weight=ft.FontWeight.BOLD),
                ],
            ),
            content=ft.Container(
                width=440,
                content=ft.Column(
                    controls=[self._search_field, self._grid_column],
                    tight=True,
                    spacing=12,
                ),
            ),
            actions=[
                ft.TextButton(
                    "No icon",
                    icon=ft.Icons.CLEAR,
                    on_click=self._clear,
                ),
                ft.TextButton("Close", on_click=self._close_picker),
            ],
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        self.content = self._trigger

        # Build the grid once so it is ready before the dialog is ever opened.
        self._rebuild_grid("")

    #  picker lifecycle 

    def _open_picker(self, e=None):
        page = self.page
        if page is None:
            return
        if self._dialog not in page.overlay:
            page.overlay.append(self._dialog)

        self._search_field.value = ""
        self._rebuild_grid("")
        self._dialog.open = True
        page.update()

    def _close_picker(self, e=None):
        self._dialog.open = False
        self._safe_update(self._dialog)

    #  selection 

    def _select(self, icon_value: str) -> None:
        self._set_display(icon_value)
        self._rebuild_grid(self._search_field.value or "")
        self._close_picker()
        if self._on_change:
            self._on_change(icon_value)

    def _clear(self, e=None):
        self._set_display(None)
        self._rebuild_grid(self._search_field.value or "")
        self._close_picker()
        if self._on_change:
            self._on_change(None)

    def _set_display(self, icon_value: str | None) -> None:
        self._selected = icon_value
        self._selected_icon_display.icon = icon_value or ft.Icons.STAR
        self._safe_update(self._trigger)

    #  search + grid rendering 

    def _on_search(self, e):
        self._rebuild_grid(e.control.value or "")

    def _rebuild_grid(self, query: str) -> None:
        self._grid_column.controls = self._build_grid(query)
        self._safe_update(self._grid_column)

    def _build_grid(self, query: str):
        q = (query or "").strip().lower()

        if q:
            matches = [
                (label, icon)
                for label, icon in self._all_icons
                if q in label.lower()
            ]
            if not matches:
                return [
                    ft.Container(
                        padding=ft.Padding.symmetric(vertical=24),
                        content=ft.Text(
                            "No icons match.",
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            size=13,
                        ),
                    )
                ]
            return self._icon_rows(matches)

        controls = []
        for title, entries in self._categories:
            if title:
                controls.append(
                    ft.Text(
                        title,
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    )
                )
            controls.extend(self._icon_rows(entries))
        return controls

    def _icon_rows(self, entries: list[tuple[str, str]]) -> list[ft.Row]:
        rows = []
        for i in range(0, len(entries), self._columns):
            chunk = entries[i : i + self._columns]
            rows.append(
                ft.Row(
                    spacing=2,
                    controls=[self._cell(label, icon) for label, icon in chunk],
                )
            )
        return rows

    def _cell(self, label: str, icon_value: str) -> ft.IconButton:
        is_selected = self._selected == icon_value
        return ft.IconButton(
            icon=icon_value,
            icon_size=self._icon_size,
            tooltip=label,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.PRIMARY_CONTAINER if is_selected else None,
                color=ft.Colors.ON_PRIMARY_CONTAINER if is_selected else None,
            ),
            on_click=lambda e, ic=icon_value: self._select(ic),
        )

    #  helpers 

    @staticmethod
    def _safe_update(control) -> None:
        try:
            control.update()
        except RuntimeError:
            pass

    #  public api 

    def set_value(self, icon_value=None) -> None:
        """Show *icon_value* as the selection without firing ``on_change``."""
        self._set_display(icon_value)

    def reset(self, default: str = ft.Icons.STAR) -> None:
        self._set_display(None)
        self._selected_icon_display.icon = default
        self._safe_update(self._trigger)

    @property
    def icon(self) -> str | None:
        return self._selected

    @property
    def value(self) -> str | None:
        return self._selected
