import flet as ft

# find more icons here: https://examples.flet.dev/icons_browser/
ICONS: list[tuple[str, str]] = [
    ("Home", ft.Icons.HOME),
    ("Search", ft.Icons.SEARCH),
    ("Settings", ft.Icons.SETTINGS),
    ("Person", ft.Icons.PERSON),
    ("Star", ft.Icons.STAR),
    ("Heart", ft.Icons.FAVORITE),
    ("Bell", ft.Icons.NOTIFICATIONS),
    ("Mail", ft.Icons.MAIL),
    ("Camera", ft.Icons.CAMERA_ALT),
    ("Edit", ft.Icons.EDIT),
    ("Delete", ft.Icons.DELETE),
    ("Add", ft.Icons.ADD_CIRCLE),
    ("Check", ft.Icons.CHECK_CIRCLE),
    ("Close", ft.Icons.CANCEL),
    ("Info", ft.Icons.INFO),
    ("Warning", ft.Icons.WARNING),
    ("Lock", ft.Icons.LOCK),
    ("Share", ft.Icons.SHARE),
    ("Download", ft.Icons.DOWNLOAD),
    ("Upload", ft.Icons.UPLOAD),
    ("Cloud", ft.Icons.CLOUD),
    ("Folder", ft.Icons.FOLDER),
    ("Chart", ft.Icons.BAR_CHART),
    ("Calendar", ft.Icons.CALENDAR_TODAY),
    ("Clock", ft.Icons.ACCESS_TIME),
    ("Phone", ft.Icons.PHONE),
    ("Mic", ft.Icons.MIC),
    ("Music", ft.Icons.MUSIC_NOTE),
    ("Code", ft.Icons.CODE),
    ("Rocket", ft.Icons.ROCKET_LAUNCH),
    ("ELECTRIC_BOLT", ft.Icons.ELECTRIC_BOLT),
    ("PRECISION_MANUFACTURING", ft.Icons.PRECISION_MANUFACTURING),
    ("APPLE", ft.Icons.APPLE)
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