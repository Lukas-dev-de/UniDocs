"""
ui/components/home_widgets/progress.py
--------------------------------------
Card showing how far a period has come, e.g. a semester.

The user names the period and picks a start and an end date; the card then
shows a progress bar with the elapsed share, the percentage and "Tag X von Y".
Everything lives in the group's .home.json as widget options (``name``,
``start``, ``end``, ISO dates ``YYYY-MM-DD``) - no other storage key is needed.

The date math is a plain function (:func:`progress_fraction`) so it can be
tested without a page: broken or missing dates, start == end, a period that has
not begun and one that is over all have a defined answer.
"""

from __future__ import annotations

from datetime import date, datetime
from math import pi

import flet as ft
from flet import canvas as cv

from ui.components.home_widgets.base import HomeWidget

# Dates are stored as ISO strings ("YYYY-MM-DD") - plain text, so the value
# survives the msgpack trip to the client and a hand-edited file as well.
DATE_FORMAT = "%Y-%m-%d"
# Picker range: wide enough for any plausible period, narrow enough to be sane.
FIRST_DATE = datetime(1970, 1, 1)
LAST_DATE = datetime(2100, 12, 31)

# Chart styles for the card body. "bar" is the default and the fallback when
# the file carries no choice - or one this build does not know.
CHART_BAR = "bar"
CHART_GAUGE = "gauge"
CHARTS = (CHART_BAR, CHART_GAUGE)
CHART_LABELS = {
    CHART_BAR: "Balken",
    CHART_GAUGE: "Tacho",
}

# Gauge dial: 270 degrees with the gap at the bottom, drawn from the lower left
# clockwise over the top to the lower right.
GAUGE_SIZE = 120
GAUGE_STROKE = 10
GAUGE_START = 0.75 * pi
GAUGE_SWEEP = 1.5 * pi


def parse_date(value) -> date | None:
    """Parse a stored ISO date, or ``None`` when it is missing/broken."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), DATE_FORMAT).date()
    except ValueError:
        return None


def normalize_chart(value) -> str:
    """Map a stored chart choice onto :data:`CHARTS`, else ``"bar"``.

    A hand-edited file, an older or a newer build can leave anything behind;
    unknown values fall back to the bar so the card always draws something.
    """
    if isinstance(value, str):
        chart = value.strip().lower()
        if chart in CHARTS:
            return chart
    return CHART_BAR


def gauge_shapes(fraction: float) -> list[cv.Arc]:
    """Background arc plus progress arc for the 270-degree dial.

    ``fraction`` is clamped to ``0.0 … 1.0``. Both arcs are plain
    :class:`cv.Arc` shapes, so the result can be checked and packed without a
    page.
    """
    share = max(0.0, min(1.0, float(fraction)))
    inset = GAUGE_STROKE / 2
    side = GAUGE_SIZE - GAUGE_STROKE
    track_paint = ft.Paint(
        stroke_width=GAUGE_STROKE,
        color=ft.Colors.OUTLINE_VARIANT,
        style=ft.PaintingStyle.STROKE,
        anti_alias=True,
    )
    value_paint = ft.Paint(
        stroke_width=GAUGE_STROKE,
        color=ft.Colors.PRIMARY,
        style=ft.PaintingStyle.STROKE,
        anti_alias=True,
    )
    # A sweep of exactly 0 draws nothing; a hairline keeps the dial's start
    # visible at 0 %.
    sweep = max(0.01, GAUGE_SWEEP * share)
    return [
        cv.Arc(
            inset,
            inset,
            side,
            side,
            start_angle=GAUGE_START,
            sweep_angle=GAUGE_SWEEP,
            paint=track_paint,
        ),
        cv.Arc(
            inset,
            inset,
            side,
            side,
            start_angle=GAUGE_START,
            sweep_angle=sweep,
            paint=value_paint,
        ),
    ]


def gauge_control(fraction: float, percent: int) -> ft.Control:
    """The tacho: canvas arcs with the percentage sitting in the middle."""
    return ft.Stack(
        width=GAUGE_SIZE,
        height=GAUGE_SIZE,
        controls=[
            cv.Canvas(width=GAUGE_SIZE, height=GAUGE_SIZE, shapes=gauge_shapes(fraction)),
            ft.Container(
                alignment=ft.Alignment.CENTER,
                content=ft.Text(
                    f"{percent} %",
                    size=18,
                    weight=ft.FontWeight.W_600,
                ),
            ),
        ],
    )


def progress_fraction(start, end, today=None) -> float | None:
    """Share of the period that has passed, clamped to ``0.0 … 1.0``.

    Returns ``None`` when the period cannot be measured (a date is missing,
    broken, or the end is before the start) - the caller then shows a hint
    instead of a bar. Before the start the share is 0, after the end it is 1.
    """
    start_date = parse_date(start)
    end_date = parse_date(end)
    if start_date is None or end_date is None or end_date <= start_date:
        return None
    today = today or date.today()
    if isinstance(today, datetime):
        today = today.date()
    total = (end_date - start_date).days
    elapsed = (today - start_date).days
    return max(0.0, min(1.0, elapsed / total))


def day_counts(start, end, today=None) -> tuple[int, int] | None:
    """``(day number, total days)`` for the period, or ``None`` if unusable.

    Day 1 is the start date itself, so an ongoing period reads "Tag 12 von 120"
    and never "Tag 0".
    """
    start_date = parse_date(start)
    end_date = parse_date(end)
    if start_date is None or end_date is None or end_date <= start_date:
        return None
    today = today or date.today()
    if isinstance(today, datetime):
        today = today.date()
    total = (end_date - start_date).days
    day = (today - start_date).days + 1
    return max(1, min(total, day)), total


@ft.control
class ProgressWidget(HomeWidget):
    TITLE = "Fortschritt"
    TYPE = "progress"

    def __init__(self, store, module_store=None, on_open_module=None):
        super().__init__(store, module_store, on_open_module)

        # Built once on first open, kept in the overlay and reused (same as the
        # other cards: pulling a dialog out of the overlay upsets Flutter).
        self._name_field = None
        self._range_field = None
        self._settings_dialog = None
        self._picker = None
        # Pending pick from the range picker; only written on "Speichern".
        self._start: str = ""
        self._end: str = ""
        # Pending chart choice, same deal.
        self._chart: str = CHART_BAR
        self._chart_dropdown = None

        self.enable_body_scroll()

    #  data 

    def _options(self) -> tuple[str, str, str]:
        """(name, start, end) as currently stored."""
        name = str(self.get_option("name", "") or "").strip()
        start = str(self.get_option("start", "") or "").strip()
        end = str(self.get_option("end", "") or "").strip()
        return name, start, end

    def _chart_option(self) -> str:
        """The stored chart choice, normalised to a known style."""
        return normalize_chart(self.get_option("chart", CHART_BAR))

    def refresh(self):
        name, start, end = self._options()
        self.body.controls.clear()

        fraction = progress_fraction(start, end)
        if fraction is None:
            self.add_body_row(
                self.placeholder("Zeitraum festlegen (Stift oben rechts).")
            )
            return

        counts = day_counts(start, end)
        percent = round(fraction * 100)
        self.add_body_row(
            ft.Text(
                name or self.TITLE,
                size=14,
                weight=ft.FontWeight.W_600,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )
        # Bars span the row so they reach the card's inner edge, but the row
        # keeps the scrollbar gutter on the right free.
        self.add_body_row(self._chart_control(self._chart_option(), fraction, percent))
        info = f"{percent} %"
        if counts is not None:
            day, total = counts
            info += f" · Tag {day} von {total}"
        self.add_body_row(ft.Text(info, size=12, color=ft.Colors.OUTLINE))
        self.add_body_row(
            ft.Text(self._status_text(start, end), size=11, color=ft.Colors.OUTLINE)
        )

    @staticmethod
    def _chart_control(chart: str, fraction: float, percent: int) -> ft.Control:
        """One of the two chart styles for the given share."""
        if chart == CHART_GAUGE:
            return ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[gauge_control(fraction, percent)],
            )
        return ft.ProgressBar(
            value=fraction, height=8, border_radius=4, expand=True
        )

    @staticmethod
    def _status_text(start, end) -> str:
        """One line below the bar: before / during / after the period."""
        start_date = parse_date(start)
        end_date = parse_date(end)
        today = date.today()
        if start_date is not None and today < start_date:
            days = (start_date - today).days
            return f"Startet in {days} Tag(en) · {start_date:{DATE_FORMAT}}"
        if end_date is not None and today > end_date:
            return f"Beendet am {end_date:{DATE_FORMAT}}"
        remaining = (end_date - today).days if end_date is not None else 0
        return f"Noch {remaining} Tag(e) · bis {end_date:{DATE_FORMAT}}"

    #  settings 

    def open_settings(self, e=None):
        page = self._page()
        if page is None:
            return

        if self._settings_dialog is None:
            self._name_field = ft.TextField(
                label="Name",
                dense=True,
                hint_text="z. B. Semester 4",
            )
            self._range_field = ft.TextField(
                label="Zeitraum",
                dense=True,
                read_only=True,
                hint_text="Start – Ende wählen",
            )
            self._picker = ft.DateRangePicker(
                first_date=FIRST_DATE,
                last_date=LAST_DATE,
                help_text="Zeitraum wählen",
                save_text="Übernehmen",
                cancel_text="Abbrechen",
                confirm_text="Übernehmen",
                field_start_label_text="Start",
                field_end_label_text="Ende",
                on_change=self._on_range_picked,
            )
            self._chart_dropdown = ft.Dropdown(
                label="Darstellung",
                dense=True,
                options=[
                    ft.DropdownOption(key=chart, text=CHART_LABELS[chart])
                    for chart in CHARTS
                ],
            )
            self._settings_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Fortschritt"),
                content=ft.Container(
                    width=380,
                    content=ft.Column(
                        tight=True,
                        spacing=10,
                        controls=[
                            self._name_field,
                            ft.Row(
                                spacing=8,
                                controls=[
                                    self._range_field,
                                    ft.IconButton(
                                        icon=ft.Icons.DATE_RANGE,
                                        tooltip="Zeitraum wählen",
                                        on_click=self._open_picker,
                                    ),
                                ],
                            ),
                            self._chart_dropdown,
                            ft.Text(
                                "Ein Zeitraum wie ein Semester: der Balken zeigt, "
                                "wie viel davon vorbei ist.",
                                size=11,
                                color=ft.Colors.OUTLINE,
                            ),
                        ],
                    ),
                ),
                actions=[
                    ft.TextButton(
                        "Zurücksetzen", on_click=lambda e: self._clear()
                    ),
                    ft.TextButton(
                        "Abbrechen", on_click=lambda e: self._close_settings()
                    ),
                    ft.FilledButton("Speichern", on_click=lambda e: self._save()),
                ],
                actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
            page.overlay.append(self._settings_dialog)

        name, start, end = self._options()
        self._start, self._end = start, end
        self._name_field.value = name
        self._chart = self._chart_option()
        self._chart_dropdown.value = self._chart
        self._sync_range_field()
        self._settings_dialog.open = True
        page.update()

    def _sync_range_field(self):
        """Show the pending range in plain German date order."""
        start = parse_date(self._start)
        end = parse_date(self._end)
        if start and end:
            text = f"{start:{DATE_FORMAT}} – {end:{DATE_FORMAT}}"
        elif start:
            text = f"{start:{DATE_FORMAT}} – ?"
        else:
            text = ""
        self._range_field.value = text
        self._safe_update(self._range_field)

    def _open_picker(self, e=None):
        """Open the range picker on top of the settings dialog."""
        page = self._page()
        if page is None or self._picker is None:
            return
        start = parse_date(self._start)
        end = parse_date(self._end)
        self._picker.start_value = start
        self._picker.end_value = end
        page.show_dialog(self._picker)

    def _on_range_picked(self, e=None):
        """Picker confirmed: keep the dates pending until "Speichern"."""
        picker = self._picker
        if picker is None:
            return
        start = parse_date(picker.start_value)
        end = parse_date(picker.end_value)
        if start is None or end is None:
            return
        self._start = f"{start:{DATE_FORMAT}}"
        self._end = f"{end:{DATE_FORMAT}}"
        self._sync_range_field()

    def _save(self):
        """Write name, range and chart style, then repaint the card."""
        self.set_option("name", (self._name_field.value or "").strip())
        self.set_option("start", self._start)
        self.set_option("end", self._end)
        self.set_option(
            "chart", normalize_chart(self._chart_dropdown.value)
        )
        self._close_settings()
        self.refresh()
        self._safe_update(self)

    def _clear(self):
        """Reset the period (the name and the style stay, both still useful)."""
        self._start = ""
        self._end = ""
        self._sync_range_field()

    def _close_settings(self):
        self._settings_dialog.open = False
        self._safe_update(self._settings_dialog)
