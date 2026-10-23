"""
ui/components/home_widgets/schedule.py
--------------------------------------
Card with the group's weekly timetable.

Entries are plain rows in the group's .home.json (weekday, from/to, title,
room, colour); nothing is fetched from the network. The card lists the next
upcoming entries with their time, the maximize button opens the whole week as
a real week calendar: an hour gutter on the left, one column per day, and every
entry drawn at its clock time with a height for its duration (Monday to Friday
always, Saturday/Sunday only when they hold entries). In edit mode the gear
opens a dialog that adds, edits and removes entries.

    entry = {"id": ..., "day": 0, "start": "08:15", "end": "09:45",
             "title": "Analysis", "room": "HS 2", "color": "#1565C0"}
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import flet as ft

from app_storage.ics import WEEKDAYS
from ui.components.home_widgets.base import HomeWidget

# Rows shown on the card; the overlay lists the whole week. The card body
# scrolls when the card is too short for that many rows (the grid gives every
# card the same cell height), so nothing gets clipped at the bottom.
CARD_ROWS = 4

# Colour choices for an entry; the hex value is what gets stored.
PALETTE = [
    ("Blau", "#1565C0"),
    ("Grün", "#2E7D32"),
    ("Orange", "#EF6C00"),
    ("Rot", "#C62828"),
    ("Lila", "#6A1B9A"),
    ("Grau", "#546E7A"),
]

# Accent used when an entry carries no (valid) colour.
DEFAULT_COLOR = "#1565C0"

#  week overlay geometry 

# Width of the week grid inside the overlay; the day columns are computed from
# it, so the Stack inside each column has a known width for its positioned
# children (left=0/right=0 needs a bounded Stack).
WEEK_WIDTH = 820
# Height of one hour on the grid: an entry sits at its start and is as tall as
# its duration.
HOUR_HEIGHT = 52
# Hour labels left of the day columns.
TIME_GUTTER_WIDTH = 44
# Gap between the columns; the hour lines of each day stop at the gap.
DAY_GAP = 6
# An entry box never gets thinner than this, or the title would vanish.
MIN_SLOT_HEIGHT = 26


#  time helpers 


def _norm_time(value: str) -> str | None:
    """Normalise ``"8:5"`` / ``"08.15"`` / ``"08:15"`` to ``"08:15"``.

    Returns ``None`` for anything that is not a readable wall-clock time.
    """
    text = (value or "").strip().replace(".", ":").replace("h", ":")
    parts = text.split(":")
    if len(parts) != 2:
        return None
    hours, minutes = parts
    if not (hours.isdigit() and minutes.isdigit()):
        return None
    h, m = int(hours), int(minutes)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f"{h:02d}:{m:02d}"


def _minutes(value: str) -> int:
    """Minutes since midnight for an ``"HH:MM"`` string."""
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def _next_start(entry: dict, now: datetime) -> datetime:
    """Next datetime this weekly entry starts (today or within seven days)."""
    day = int(entry.get("day", 0))
    total = _minutes(entry["start"])
    start = now.replace(hour=total // 60, minute=total % 60, second=0, microsecond=0)
    start += timedelta(days=(day - now.weekday()) % 7)
    if start < now:
        start += timedelta(days=7)
    return start


#  dialog 


class ScheduleDialog(ft.AlertDialog):
    """Edits the whole timetable at once; Save writes it back.

    Rows live straight in a scrollable column (like the quick-link dialog), so
    removing one is a plain control removal. Completely empty rows are dropped
    on save. An invalid row (missing title, bad time, end not after start)
    keeps the dialog open and shows the reason in the status line.
    """

    def __init__(self, entries: list[dict], on_save, on_close=None):
        self._on_save = on_save
        self._on_close = on_close
        self._rows: list[dict] = []

        self._rows_column = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, height=380)
        self._status = ft.Text("", size=12, color=ft.Colors.ERROR)

        super().__init__(
            modal=True,
            title=ft.Text("Stundenplan"),
            content=ft.Container(
                width=720,
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        self._rows_column,
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.TextButton(
                                    "Eintrag hinzufügen",
                                    icon=ft.Icons.ADD,
                                    on_click=self._add_row,
                                ),
                                self._status,
                            ],
                        ),
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda e: self.close()),
                ft.FilledButton("Speichern", on_click=self._save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.reset(entries)

    def reset(self, entries: list[dict]) -> None:
        """Rebuild the rows for a fresh edit session (the dialog is reused)."""
        self._rows = []
        self._rows_column.controls.clear()
        self._status.value = ""
        for entry in entries:
            if isinstance(entry, dict):
                self._add_row(entry=entry)
        if not self._rows:
            self._add_row()

    #  rows 

    def _build_row(self, entry: dict) -> dict:
        day = ft.Dropdown(
            width=92,
            text_size=13,
            options=[
                ft.dropdown.Option(key=str(i), text=WEEKDAYS[i]) for i in range(7)
            ],
            value=str(int(entry.get("day", 0))),
        )
        start = ft.TextField(
            label="Von", width=84, dense=True, value=entry.get("start", ""),
            hint_text="08:15",
        )
        end = ft.TextField(
            label="Bis", width=84, dense=True, value=entry.get("end", ""),
            hint_text="09:45",
        )
        title = ft.TextField(
            label="Titel", expand=True, dense=True, value=entry.get("title", ""),
        )
        room = ft.TextField(
            label="Raum", width=110, dense=True, value=entry.get("room", ""),
        )
        color = ft.Dropdown(
            width=130,
            text_size=13,
            options=[
                ft.dropdown.Option(key=hex_value, text=name)
                for name, hex_value in PALETTE
            ],
            value=entry.get("color") or DEFAULT_COLOR,
        )
        row = ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[day, start, end, title, room, color],
        )
        item = {
            "id": entry.get("id") or str(uuid.uuid4()),
            "day": day,
            "start": start,
            "end": end,
            "title": title,
            "room": room,
            "color": color,
            "control": row,
        }
        row.controls.append(
            ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE,
                tooltip="Entfernen",
                on_click=lambda e, it=item: self._remove_row(it),
            )
        )
        return item

    def _add_row(self, e=None, entry=None):
        item = self._build_row(entry or {})
        self._rows.append(item)
        self._rows_column.controls.append(item["control"])
        self._safe_update(self._rows_column)

    def _remove_row(self, item: dict):
        if item in self._rows:
            self._rows.remove(item)
        if item["control"] in self._rows_column.controls:
            self._rows_column.controls.remove(item["control"])
        self._safe_update(self._rows_column)

    #  save 

    def _collect(self) -> tuple[list[dict] | None, str | None]:
        """Validate every row into ``(entries, None)`` or ``(None, message)``.

        Empty rows are skipped silently; the first real mistake stops the save
        and returns a German message for the status line.
        """
        entries: list[dict] = []
        for item in self._rows:
            title = (item["title"].value or "").strip()
            start_raw = (item["start"].value or "").strip()
            end_raw = (item["end"].value or "").strip()
            if not (title or start_raw or end_raw):
                continue

            start = _norm_time(start_raw)
            if start is None:
                return None, "Beginn als HH:MM angeben (z. B. 08:15)."
            end = _norm_time(end_raw)
            if end is None:
                return None, "Ende als HH:MM angeben (z. B. 09:45)."
            if _minutes(end) <= _minutes(start):
                return None, "Ende muss nach dem Beginn liegen."
            if not title:
                return None, "Bitte einen Titel angeben."

            entries.append(
                {
                    "id": item["id"],
                    "day": int(item["day"].value or 0),
                    "start": start,
                    "end": end,
                    "title": title,
                    "room": (item["room"].value or "").strip(),
                    "color": item["color"].value or DEFAULT_COLOR,
                }
            )
        return entries, None

    def _save(self, e=None):
        entries, error = self._collect()
        if error:
            self._status.value = error
            self._safe_update(self._status)
            return
        self._on_save(entries)
        self.close()

    #  helpers 

    def _safe_update(self, control):
        try:
            control.update()
        except RuntimeError:
            pass

    def close(self):
        self.open = False
        self._safe_update(self)
        if self._on_close:
            self._on_close(self)


#  widget 


@ft.control
class ScheduleWidget(HomeWidget):
    TITLE = "Stundenplan"
    TYPE = "schedule"

    def __init__(self, store, module_store=None, on_open_module=None):
        super().__init__(store, module_store, on_open_module)

        # Dialog and overlay are built once, then only shown/hidden again
        # (removing a dialog from the overlay upsets Flutter - see calendar.py).
        self._dialog = None
        self._week_column = None
        self._week_dialog = None

        # The card's cell height comes from the grid, not from the row count,
        # so a fourth entry would otherwise be cut off at the bottom. The body
        # scrolls edge to edge, so the scrollbar sits on the card's right side.
        self.enable_body_scroll()

        self._maximize_btn = ft.IconButton(
            icon=ft.Icons.OPEN_IN_FULL,
            icon_size=18,
            tooltip="Maximieren",
            on_click=self._open_week_view,
        )
        self._actions_row.controls.insert(0, self._maximize_btn)

    #  data 

    def _entries(self) -> list[dict]:
        """The stored timetable, reduced to rows that can actually be shown."""
        raw = self._store.load(self._group).get("schedule", [])
        entries: list[dict] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            start = _norm_time(item.get("start", ""))
            end = _norm_time(item.get("end", ""))
            if not title or start is None or end is None:
                continue
            if _minutes(end) <= _minutes(start):
                continue
            try:
                day = int(item.get("day", 0))
            except (TypeError, ValueError):
                day = 0
            entries.append(
                {
                    "id": item.get("id"),
                    "day": day % 7,
                    "start": start,
                    "end": end,
                    "title": title,
                    "room": (item.get("room") or "").strip(),
                    "color": item.get("color") or DEFAULT_COLOR,
                }
            )
        return entries

    #  card 

    def refresh(self):
        entries = self._entries()
        self.body.controls.clear()
        if not entries:
            self.body.controls.append(self.placeholder("Kein Stundenplan."))
            return
        now = datetime.now()
        upcoming = sorted(entries, key=lambda entry: _next_start(entry, now))
        for entry in upcoming[:CARD_ROWS]:
            self.add_body_row(self._entry_row(entry, now))

    def _entry_row(self, entry: dict, now: datetime) -> ft.Container:
        today = _next_start(entry, now).date() == now.date()
        day_label = "Heute" if today else WEEKDAYS[entry["day"]]
        meta = f"{day_label} · {entry['start']}–{entry['end']}"
        if entry["room"]:
            meta += f" · {entry['room']}"
        return ft.Container(
            padding=ft.padding.symmetric(vertical=8, horizontal=10),
            border_radius=8,
            border=ft.border.all(
                1, entry["color"] if today else ft.Colors.OUTLINE_VARIANT
            ),
            content=ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    ft.Text(
                        entry["title"],
                        size=13,
                        weight=ft.FontWeight.BOLD if today else ft.FontWeight.W_500,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(meta, size=11, color=ft.Colors.OUTLINE),
                ],
            ),
        )

    #  week overlay 

    def _open_week_view(self, e=None):
        page = self._page()
        if page is None:
            return

        if self._week_dialog is None:
            # Fixed height so the grid body can scroll on its own; the weekday
            # header sits above it and stays put while scrolling.
            self._week_column = ft.Column(expand=True, spacing=0)
            self._week_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Stundenplan"),
                content=ft.Container(
                    width=WEEK_WIDTH,
                    height=520,
                    content=self._week_column,
                ),
                actions=[
                    ft.TextButton(
                        "Schließen", on_click=lambda e: self._close_week_view()
                    )
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.overlay.append(self._week_dialog)

        self._week_dialog.title.value = f"Stundenplan · {self._group or 'Home'}"
        self._week_column.controls.clear()
        self._week_column.controls.append(self._week_grid())
        self._week_dialog.open = True
        page.update()

    @staticmethod
    def _time_window(entries: list[dict]) -> tuple[int, int]:
        """First and last minute the grid has to cover (full hours)."""
        if not entries:
            return 8 * 60, 18 * 60
        first = min(_minutes(entry["start"]) for entry in entries) // 60 * 60
        last_raw = max(_minutes(entry["end"]) for entry in entries)
        last = -(-last_raw // 60) * 60  # round up to the next full hour
        return first, max(last, first + 60)

    def _week_grid(self) -> ft.Column:
        """Week overlay as a time grid: vertical position = clock time."""
        entries = self._entries()
        now = datetime.now()
        # Monday to Friday always; the weekend only when something sits there.
        days = [0, 1, 2, 3, 4]
        days += [d for d in (5, 6) if any(entry["day"] == d for entry in entries)]

        first, last = self._time_window(entries)
        height = (last - first) / 60 * HOUR_HEIGHT
        day_width = (
            WEEK_WIDTH - TIME_GUTTER_WIDTH - DAY_GAP * len(days)
        ) / len(days)

        header = ft.Row(
            spacing=DAY_GAP,
            controls=[ft.Container(width=TIME_GUTTER_WIDTH)]
            + [
                ft.Container(
                    width=day_width,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text(
                        WEEKDAYS[day],
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color=(
                            ft.Colors.PRIMARY
                            if day == now.weekday()
                            else ft.Colors.ON_SURFACE_VARIANT
                        ),
                    ),
                )
                for day in days
            ],
        )

        gutter = ft.Container(
            width=TIME_GUTTER_WIDTH,
            height=height,
            content=ft.Stack(
                width=TIME_GUTTER_WIDTH,
                height=height,
                controls=[
                    ft.Container(
                        top=max((hour * 60 - first) / 60 * HOUR_HEIGHT - 7, 0),
                        right=6,
                        content=ft.Text(
                            f"{hour:02d}", size=10, color=ft.Colors.OUTLINE
                        ),
                    )
                    for hour in range(first // 60, last // 60 + 1)
                ],
            ),
        )

        columns = [gutter]
        for day in days:
            columns.append(
                ft.Container(
                    width=day_width,
                    height=height,
                    content=ft.Stack(
                        width=day_width,
                        height=height,
                        controls=self._day_slots(entries, day, first, last, height),
                    ),
                )
            )

        # Header outside the scroller: the weekday row must stay visible while
        # the grid body scrolls (in Flet 0.84 only Row/Column scroll, Container
        # does not).
        return ft.Column(
            expand=True,
            spacing=6,
            controls=[
                header,
                ft.Column(
                    expand=True,
                    spacing=0,
                    scroll=ft.ScrollMode.AUTO,
                    controls=[
                        ft.Row(
                            spacing=DAY_GAP,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                            controls=columns,
                        )
                    ],
                ),
            ],
        )

    def _day_slots(
        self,
        entries: list[dict],
        day: int,
        first: int,
        last: int,
        height: float,
    ) -> list[ft.Control]:
        """Hour lines plus the entries of one day, positioned by their time."""
        controls: list[ft.Control] = [
            ft.Container(
                top=(hour * 60 - first) / 60 * HOUR_HEIGHT,
                left=0,
                right=0,
                height=1,
                bgcolor=ft.Colors.OUTLINE_VARIANT,
            )
            for hour in range(first // 60, last // 60 + 1)
        ]

        for entry in sorted(
            (entry for entry in entries if entry["day"] == day),
            key=lambda entry: entry["start"],
        ):
            start = _minutes(entry["start"])
            end = _minutes(entry["end"])
            controls.append(
                self._slot(
                    entry,
                    top=(start - first) / 60 * HOUR_HEIGHT,
                    height=max((end - start) / 60 * HOUR_HEIGHT, MIN_SLOT_HEIGHT),
                )
        )
        return controls

    def _slot(self, entry: dict, top: float, height: float) -> ft.Container:
        """One entry drawn at its clock time and as tall as its duration.

        Small boxes drop the time and room lines so the title always fits; the
        container clips instead of overflowing.
        """
        details = [
            ft.Text(
                entry["title"],
                size=11,
                weight=ft.FontWeight.W_500,
                max_lines=2 if height >= 44 else 1,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        ]
        if height >= 36:
            details.append(
                ft.Text(
                    f"{entry['start']}–{entry['end']}",
                    size=10,
                    color=ft.Colors.OUTLINE,
                    max_lines=1,
                )
            )
        if height >= 62 and entry["room"]:
            details.append(
                ft.Text(
                    entry["room"],
                    size=10,
                    color=ft.Colors.OUTLINE,
                    max_lines=1,
                )
            )

        return ft.Container(
            top=top,
            left=0,
            right=0,
            height=height,
            padding=ft.padding.symmetric(horizontal=6, vertical=2),
            border_radius=6,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border=ft.border.only(left=ft.BorderSide(3, entry["color"])),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Column(spacing=0, tight=True, controls=details),
        )

    def _close_week_view(self):
        self._week_dialog.open = False
        self._safe_update(self._week_dialog)

    #  settings 

    def open_settings(self, e=None):
        page = self._page()
        if page is None:
            return
        if self._dialog is None:
            self._dialog = ScheduleDialog(
                [],
                on_save=self._save_entries,
                on_close=self._close_dialog,
            )
            page.overlay.append(self._dialog)
        self._dialog.reset(self._entries())
        self._dialog.open = True
        page.update()

    def _save_entries(self, entries: list[dict]):
        self._store.set_schedule_entries(self._group, entries)
        self.refresh()
        self._safe_update(self)

    def _close_dialog(self, dialog):
        # Hide only: a dialog pulled out of the overlay makes Flutter complain
        # about a removed view. The instance is reused on the next open.
        dialog.open = False
        page = self._page()
        if page is not None:
            page.update()
