import flet as ft

# find more icons here: https://examples.flet.dev/icons_browser/
ICONS: list[tuple[str, str]] = [
    ("Account Balance", ft.Icons.ACCOUNT_BALANCE),
    ("Account Tree", ft.Icons.ACCOUNT_TREE_OUTLINED),
    ("All Inbox", ft.Icons.ALL_INBOX),
    ("Analytics", ft.Icons.ANALYTICS),
    ("Apartment", ft.Icons.APARTMENT),
    ("Area Chart", ft.Icons.AREA_CHART),
    ("Article", ft.Icons.ARTICLE),
    ("Art Track", ft.Icons.ART_TRACK),
    ("Architecture", ft.Icons.ARCHITECTURE),
    ("Assessment", ft.Icons.ASSESSMENT),
    ("Assignment", ft.Icons.ASSIGNMENT),
    ("Audiotrack", ft.Icons.AUDIOTRACK),
    ("Auto Awesome", ft.Icons.AUTO_AWESOME_OUTLINED),
    ("Auto Stories", ft.Icons.AUTO_STORIES),
    ("Balance", ft.Icons.BALANCE),
    ("Backup Table", ft.Icons.BACKUP_TABLE_ROUNDED),
    ("Bar Chart", ft.Icons.BAR_CHART),
    ("Biotech", ft.Icons.BIOTECH),
    ("Bolt", ft.Icons.BOLT),
    ("Border Color", ft.Icons.BORDER_COLOR_ROUNDED),
    ("Brush", ft.Icons.BRUSH),
    ("Bubble Chart", ft.Icons.BUBBLE_CHART_OUTLINED),
    ("Build", ft.Icons.BUILD),
    ("Business Center", ft.Icons.BUSINESS_CENTER),
    ("Business", ft.Icons.BUSINESS),
    ("Cable", ft.Icons.CABLE),
    ("Calculate", ft.Icons.CALCULATE),
    ("Calendar Month", ft.Icons.CALENDAR_MONTH),
    ("Camera", ft.Icons.CAMERA),
    ("Campaign", ft.Icons.CAMPAIGN),
    ("Candlestick Chart", ft.Icons.CANDLESTICK_CHART),
    ("Carpenter", ft.Icons.CARPENTER),
    ("Casino", ft.Icons.CASINO),
    ("Catching Pokemon", ft.Icons.CATCHING_POKEMON),
    ("Category", ft.Icons.CATEGORY),
    ("Category", ft.Icons.CATEGORY_OUTLINED),
    ("Chat", ft.Icons.CHAT),
    ("Church", ft.Icons.CHURCH),
    ("Co2", ft.Icons.CO2),
    ("Code", ft.Icons.CODE),
    ("Coffee", ft.Icons.COFFEE),
    ("Coffee", ft.Icons.COFFEE_OUTLINED),
    ("Color Lens", ft.Icons.COLOR_LENS_OUTLINED),
    ("Collections", ft.Icons.COLLECTIONS_OUTLINED),
    ("Compost", ft.Icons.COMPOST),
    ("Computer", ft.Icons.COMPUTER),
    ("Construction", ft.Icons.CONSTRUCTION),
    ("Content Cut", ft.Icons.CONTENT_CUT),
    ("Cookie", ft.Icons.COOKIE),
    ("Conveyor Belt", ft.Icons.CONVEYOR_BELT),
    ("Cruelty Free", ft.Icons.CRUELTY_FREE_OUTLINED),
    ("Currency Bitcoin", ft.Icons.CURRENCY_BITCOIN),
    ("Dashboard", ft.Icons.DASHBOARD),
    ("Data Array", ft.Icons.DATA_ARRAY),
    ("Data Exploration", ft.Icons.DATA_EXPLORATION),
    ("Data Object", ft.Icons.DATA_OBJECT),
    ("Data Saver Off", ft.Icons.DATA_SAVER_OFF),
    ("Dataset", ft.Icons.DATASET),
    ("Design Services", ft.Icons.DESIGN_SERVICES),
    ("Desk", ft.Icons.DESK),
    ("Developer Board", ft.Icons.DEVELOPER_BOARD),
    ("Device Hub", ft.Icons.DEVICE_HUB),
    ("Device Thermostat", ft.Icons.DEVICE_THERMOSTAT),
    ("Diamond", ft.Icons.DIAMOND),
    ("Discount", ft.Icons.DISCOUNT),
    ("Diversity 1", ft.Icons.DIVERSITY_1),
    ("Dns", ft.Icons.DNS_ROUNDED),
    ("Eco", ft.Icons.ECO_OUTLINED),
    ("Electric Bolt", ft.Icons.ELECTRIC_BOLT),
    ("Electrical Services", ft.Icons.ELECTRICAL_SERVICES),
    ("Email", ft.Icons.EMAIL),
    ("Emoji Food Beverage", ft.Icons.EMOJI_FOOD_BEVERAGE),
    ("Emoji Objects", ft.Icons.EMOJI_OBJECTS),
    ("Emoji Symbols", ft.Icons.EMOJI_SYMBOLS),
    ("Engineering", ft.Icons.ENGINEERING),
    ("Exposure", ft.Icons.EXPOSURE),
    ("Explore", ft.Icons.EXPLORE),
    ("Extension", ft.Icons.EXTENSION),
    ("Factory", ft.Icons.FACTORY),
    ("Family Restroom", ft.Icons.FAMILY_RESTROOM),
    ("Favorite", ft.Icons.FAVORITE),
    ("Favorite Border", ft.Icons.FAVORITE_BORDER),
    ("Filter Hdr", ft.Icons.FILTER_HDR),
    ("Fitness Center", ft.Icons.FITNESS_CENTER),
    ("Flag", ft.Icons.FLAG),
    ("Flight", ft.Icons.FLIGHT),
    ("Functions", ft.Icons.FUNCTIONS),
    ("Gavel", ft.Icons.GAVEL),
    ("Hotel Class", ft.Icons.HOTEL_CLASS_OUTLINED),
    ("Hourglass Empty", ft.Icons.HOURGLASS_EMPTY_ROUNDED),
    ("Hub", ft.Icons.HUB),
    ("Https", ft.Icons.HTTPS),
    ("Incomplete Circle", ft.Icons.INCOMPLETE_CIRCLE),
    ("Import Export", ft.Icons.IMPORT_EXPORT),
    ("Insert Link", ft.Icons.INSERT_LINK),
    ("Interests", ft.Icons.INTERESTS_OUTLINED),
    ("Javascript", ft.Icons.JAVASCRIPT),
    ("Key", ft.Icons.KEY_OUTLINED),
    ("Keyboard Option Key", ft.Icons.KEYBOARD_OPTION_KEY),
    ("Keyboard Voice", ft.Icons.KEYBOARD_VOICE_OUTLINED),
    ("Lan", ft.Icons.LAN_ROUNDED),
    ("Numbers", ft.Icons.NUMBERS),
    ("Pattern", ft.Icons.PATTERN),
    ("Percent", ft.Icons.PERCENT),
    ("Perm Data Setting", ft.Icons.PERM_DATA_SETTING),
    ("Piano", ft.Icons.PIANO),
    ("Pie Chart", ft.Icons.PIE_CHART),
    ("Precision Manufacturing", ft.Icons.PRECISION_MANUFACTURING),
    ("Radio", ft.Icons.RADIO),
    ("Ramen Dining", ft.Icons.RAMEN_DINING_OUTLINED),
    ("School", ft.Icons.SCHOOL),
    ("Shelves", ft.Icons.SHELVES),
    ("Sports Basketball", ft.Icons.SPORTS_BASKETBALL),
    ("Sticky Note 2", ft.Icons.STICKY_NOTE_2_ROUNDED),
    ("Style", ft.Icons.STYLE),
    ("Tips And Updates", ft.Icons.TIPS_AND_UPDATES),
    ("Translate", ft.Icons.TRANSLATE_ROUNDED),
    ("Vaccines", ft.Icons.VACCINES),
    ("Videocam", ft.Icons.VIDEOCAM_ROUNDED),
    ("Videogame Asset", ft.Icons.VIDEOGAME_ASSET),
    ("Villa", ft.Icons.VILLA_OUTLINED),
    ("Widgets", ft.Icons.WIDGETS_OUTLINED),
    ("Wind Power", ft.Icons.WIND_POWER),
    ("Language", ft.Icons.LANGUAGE),
    ("Landscape", ft.Icons.LANDSCAPE_ROUNDED),
    ("Legend Toggle", ft.Icons.LEGEND_TOGGLE_ROUNDED),
    ("Lens Blur", ft.Icons.LENS_BLUR),
    ("Library Music", ft.Icons.LIBRARY_MUSIC),
    ("Local Bar", ft.Icons.LOCAL_BAR),
    ("Local Cafe", ft.Icons.LOCAL_CAFE_OUTLINED),
    ("Local Fire Department", ft.Icons.LOCAL_FIRE_DEPARTMENT),
    ("Local Drink", ft.Icons.LOCAL_DRINK_OUTLINED),
    ("Local Hospital", ft.Icons.LOCAL_HOSPITAL_ROUNDED),
    ("Local Offer", ft.Icons.LOCAL_OFFER_OUTLINED),
    ("Local Library", ft.Icons.LOCAL_LIBRARY_ROUNDED),
    ("Memory", ft.Icons.MEMORY),
    ("Mic External On", ft.Icons.MIC_EXTERNAL_ON),
    ("Miscellaneous Services", ft.Icons.MISCELLANEOUS_SERVICES),
    ("Monetization On", ft.Icons.MONETIZATION_ON_OUTLINED),
    ("Monitor Heart", ft.Icons.MONITOR_HEART),
    ("Monitor", ft.Icons.MONITOR),
    ("Movie", ft.Icons.MOVIE),
    ("Newspaper", ft.Icons.NEWSPAPER),
    ("Nightlife", ft.Icons.NIGHTLIFE_ROUNDED),
    ("Local Movies", ft.Icons.LOCAL_MOVIES_OUTLINED),
    ("Gesture", ft.Icons.GESTURE),
    ("Grass", ft.Icons.GRASS),
    ("Graphic Eq", ft.Icons.GRAPHIC_EQ),
    ("Handyman", ft.Icons.HANDYMAN),
    ("Headphones", ft.Icons.HEADPHONES),
    ("Home Repair Service", ft.Icons.HOME_REPAIR_SERVICE),
]


class IconSelector(ft.Container):
    """
    A grid icon picker that opens in a ft.PopupMenuButton.

    Usage:
        selector = IconSelector()
        ft.IconButton(icon=selector.icon)

    Properties:
        .icon   - the selected ft.Icons value
        .value  - same as .icon

    Methods:
        .reset()  - clears selection and resets the displayed icon

    Constructor args (all optional):
        icons       - list of (label, ft.Icons.*) tuples
        icon_size   - size of icons in the grid (default 22)
        columns     - number of columns (default 6)
        on_change   - callback(icon_value) fired when selection changes
        **kwargs    - forwarded to the outer ft.Container
    """

    def __init__(
        self,
        icons: list[tuple[str, str]] | None = None,
        icon_size: int = 22,
        columns: int = 6,
        on_change=None,
        **kwargs,
    ):
        kwargs.pop("value", None)
        super().__init__(**kwargs)
        self._icons = icons or ICONS
        self._icon_size = icon_size
        self._columns = columns
        self._on_change = on_change
        self._selected: str | None = None
        self._selected_button: ft.IconButton | None = None

        

        self._selected_icon_display = ft.Icon(ft.Icons.STAR, size=icon_size)

        self._trigger_container = ft.Container(
            content=self._selected_icon_display,
            width=icon_size + 16,
            height=icon_size + 16,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=6,
            tooltip="Select icon",
        )

        self._grid = ft.PopupMenuButton(
            content=self._trigger_container,
            menu_position=ft.PopupMenuPosition.UNDER,
            items=self._build_items(),
        )
        self.content = self._grid

    def _build_items(self):
        rows = []

        for i in range(0, len(self._icons), self._columns):
            chunk = self._icons[i : i + self._columns]

            rows.append(
                ft.Row(
                    spacing=2,
                    controls=[
                        ft.IconButton(
                            icon=icon_value,
                            icon_size=self._icon_size,
                            tooltip=label,
                            style=ft.ButtonStyle(
                                bgcolor=ft.Colors.PRIMARY_CONTAINER
                                if self._selected == icon_value
                                else None,
                            ),
                            on_click=lambda e, ic=icon_value, lbl=label: self._select(e, lbl, ic),
                        )
                        for label, icon_value in chunk
                    ],
                )
            )

        return [ft.PopupMenuItem(content=ft.Column(rows, spacing=2, tight=True))]

    def _select(self, e: ft.ControlEvent, label: str, icon_value: str):
        # icon button highlighting
        if self._selected_button:
            self._selected_button.style = ft.ButtonStyle(bgcolor=None)
            self._selected_button.update()

        e.control.style = ft.ButtonStyle(bgcolor=ft.Colors.PRIMARY_CONTAINER)
        e.control.update()
        self._selected_button = e.control  
        
        self._selected = icon_value
        self._trigger_container.content = ft.Icon(icon_value, size=self._icon_size)
        self._trigger_container.update()

        if self._on_change:
            self._on_change(icon_value)
    def reset(self, default: str = ft.Icons.STAR):
        """Reset selection and display back to default icon."""
        self._selected = None
        self._selected_icon_display.name = default
        self._trigger_container.update()

    @property
    def icon(self) -> str | None:
        return self._selected

    @property
    def value(self) -> str | None:
        return self._selected