"""
ui/components/home_widgets/calendar.py
--------------------------------------
Card showing the next appointments from the group's iCal/ICS feed.

The feed URL is set behind the gear (HomeStore.set_calendar_ics_url) and
edited read-only: nothing is ever written back to the calendar. Fetching runs
on a worker thread, so a slow or unreachable feed cannot freeze the UI - the
card shows "Lade Termine…" until the result (or the error) lands. The
maximize button opens the same list, with more rows, as an overlay.
"""

from __future__ import annotations

import threading

import flet as ft

from app_storage.ics import ICSEvent, fetch_ics, format_when, parse_ics, upcoming
from ui.components.home_widgets.base import HomeWidget

# Rows on the card; the maximize overlay lists the full feed. The card body
# scrolls when the card is too short for that many rows (the grid gives every
# card the same cell height), so nothing gets clipped at the bottom.
CARD_ROWS = 4
FULL_ROWS = 100
# Range the "visible events" card option may take.
MIN_ROWS = 1
MAX_ROWS = 12


@ft.control
class CalendarWidget(HomeWidget):
    TITLE = "Kalender"
    TYPE = "calendar"

    def __init__(self, store, module_store=None, on_open_module=None):
        super().__init__(store, module_store, on_open_module)

        self._url = ""
        self._events: list[ICSEvent] = []
        self._status = ""

        # Dialogs are built once and kept in the overlay, then only shown and
        # hidden again: removing one flips a Flutter view out from under the
        # engine, so open/close just toggles ``.open`` (same as the sidebar
        # dialogs). Cached as attributes so the instance survives a reopen.
        self._settings_field = None
        self._rows_dd = None
        self._settings_status = None
        self._settings_dialog = None
        self._full_column = None
        self._full_dialog = None

        # The card's cell height comes from the grid, not from the row count,
        # so the last entry would otherwise be cut off at the bottom.
        self.body.scroll = ft.ScrollMode.AUTO

        self._maximize_btn = ft.IconButton(
            icon=ft.Icons.OPEN_IN_FULL,
            icon_size=18,
            tooltip="Maximieren",
            on_click=self._open_full_view,
        )
        self._actions_row.controls.insert(0, self._maximize_btn)

    #  data 

    def refresh(self):
        self._url = (self._store.load(self._group).get("calendar_ics_url") or "").strip()
        if not self._url:
            self._events = []
            self._render("Kein Kalender verbunden.")
            return
        self._render("Lade Termine…")
        threading.Thread(target=self._fetch, args=(self._url,), daemon=True).start()

    def _fetch(self, url: str):
        """Worker-thread half: download + parse, then repaint on the UI thread."""
        try:
            events = upcoming(parse_ics(fetch_ics(url)), limit=FULL_ROWS)
            status = "" if events else "Keine anstehenden Termine."
        except Exception as ex:
            events, status = [], self._message(ex)
        self._apply(url, events, status)

    def _apply(self, url: str, events: list[ICSEvent], status: str):
        """Land a fetch result - unless the card moved on to another group.

        Called from the worker thread, so the repaint hops back onto the
        page's event loop (``run_task`` needs a coroutine function).
        """
        page = self._page()
        if page is None:
            self._land(url, events, status)
        else:
            page.run_task(self._land_async, url, events, status)

    async def _land_async(self, url: str, events: list[ICSEvent], status: str):
        """Event-loop half of :meth:`_apply`."""
        self._land(url, events, status)

    def _land(self, url: str, events: list[ICSEvent], status: str):
        if url != self._url:
            return
        self._events = events
        self._status = status
        self._render(status or None)
        self._safe_update(self)

    @staticmethod
    def _message(ex: Exception) -> str:
        """Readable one-liner for the (unavoidably) long urllib messages."""
        text = str(ex).strip()
        if isinstance(ex, ValueError):
            return text
        return f"Kalender nicht erreichbar ({text or type(ex).__name__})."

    #  rendering 

    def _row_limit(self) -> int:
        """Rows to show on the card (option ``card_rows``, clamped)."""
        try:
            value = int(self.get_option("card_rows", CARD_ROWS))
        except (TypeError, ValueError):
            return CARD_ROWS
        return max(MIN_ROWS, min(MAX_ROWS, value))

    def _selected_rows(self) -> int:
        """Rows currently picked in the settings dropdown (clamped)."""
        raw = self._rows_dd.value if self._rows_dd is not None else None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return self._row_limit()
        return max(MIN_ROWS, min(MAX_ROWS, value))

    def _render(self, empty_text: str | None):
        self.body.controls.clear()
        if empty_text:
            self.body.controls.append(self.placeholder(empty_text))
            return
        limit = self._row_limit()
        for event in self._events[:limit]:
            self.body.controls.append(self._event_row(event))
        if len(self._events) > limit:
            self.body.controls.append(
                ft.Text(
                    f"+{len(self._events) - limit} weitere",
                    size=11,
                    color=ft.Colors.OUTLINE,
                )
            )

    def _event_row(self, event: ICSEvent) -> ft.Row:
        details = [
            ft.Text(event.summary, size=13, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)
        ]
        if event.location:
            details.append(ft.Text(event.location, size=11, color=ft.Colors.OUTLINE))
        return ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Text(format_when(event), size=12, color=ft.Colors.ON_SURFACE_VARIANT, width=92),
                ft.Column(spacing=0, tight=True, expand=True, controls=details),
            ],
        )

    #  settings 

    def open_settings(self, e=None):
        page = self._page()
        if page is None:
            return

        if self._settings_dialog is None:
            self._settings_field = ft.TextField(
                label="ICS-URL",
                dense=True,
                hint_text="https://…/calendar.ics",
                on_submit=lambda e: self._store_url(),
            )
            self._rows_dd = ft.Dropdown(
                label="Sichtbare Termine",
                dense=True,
                width=200,
                options=[
                    ft.dropdown.Option(key=str(n), text=str(n))
                    for n in range(MIN_ROWS, MAX_ROWS + 1)
                ],
            )
            self._settings_status = ft.Text("", size=12, color=ft.Colors.ERROR)
            self._settings_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Kalender verbinden"),
                content=ft.Container(
                    width=440,
                    content=ft.Column(
                        tight=True,
                        spacing=10,
                        controls=[
                            self._settings_field,
                            self._rows_dd,
                            ft.Text(
                                "Nur lesen: UniDocs zeigt die Termine, ändert nie den Kalender.",
                                size=11,
                                color=ft.Colors.OUTLINE,
                            ),
                            self._settings_status,
                        ],
                    ),
                ),
                actions=[
                    ft.TextButton(
                        "Trennen",
                        icon=ft.Icons.LINK_OFF,
                        on_click=lambda e: self._store_url(""),
                    ),
                    ft.TextButton("Abbrechen", on_click=lambda e: self._close_settings()),
                    ft.FilledButton("Speichern", on_click=lambda e: self._store_url()),
                ],
                actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
            page.overlay.append(self._settings_dialog)

        self._settings_field.value = self._url
        self._settings_field.error_text = None
        self._rows_dd.value = str(self._row_limit())
        self._settings_status.value = ""
        self._settings_dialog.open = True
        page.update()

    def _close_settings(self):
        self._settings_dialog.open = False
        self._safe_update(self._settings_dialog)

    def _store_url(self, url: str | None = None):
        # No argument = use the field (Save / Enter); "" = disconnect.
        value = (
            (self._settings_field.value or "").strip()
            if url is None
            else url.strip()
        )
        if value and not value.lower().startswith(("http://", "https://", "webcal://")):
            self._settings_field.error_text = "http(s)- oder webcal-Link erwartet"
            self._safe_update(self._settings_field)
            return
        self._store.set_calendar_ics_url(self._group, value)
        # The row count is an option and survives even a disconnect.
        self.set_option("card_rows", self._selected_rows())
        self._close_settings()
        self.refresh()
        self._safe_update(self)

    #  full view 

    def _open_full_view(self, e=None):
        page = self._page()
        if page is None:
            return

        if self._full_dialog is None:
            self._full_column = ft.Column(
                spacing=10, scroll=ft.ScrollMode.AUTO, height=520
            )
            self._full_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Kalender"),
                content=ft.Container(width=760, content=self._full_column),
                actions=[
                    ft.TextButton("Schließen", on_click=lambda e: self._close_full_view())
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.overlay.append(self._full_dialog)

        self._full_dialog.title.value = f"Kalender · {self._group or 'Home'}"
        self._full_column.controls.clear()
        if self._events:
            self._full_column.controls.extend(
                self._event_row(event) for event in self._events
            )
        else:
            self._full_column.controls.append(
                self.placeholder(self._status or "Keine anstehenden Termine.")
            )
        self._full_dialog.open = True
        page.update()

    def _close_full_view(self):
        self._full_dialog.open = False
        self._safe_update(self._full_dialog)
