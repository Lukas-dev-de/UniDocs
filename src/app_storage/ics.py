"""
app_storage/ics.py
------------------
Minimal read-only iCal/ICS reader for the home page calendar widget.

Only what a "next appointments" card needs is implemented:

* line unfolding and VEVENT blocks
* DTSTART / DTEND / SUMMARY / LOCATION
* DATE (all-day) and DATE-TIME values, ``Z`` (UTC) or a TZID parameter
* ``fetch_ics`` for http(s)/webcal feeds and the pure ``parse_ics``

Everything is returned timezone-aware: ``Z`` stamps become UTC, everything
else is treated as local time (the TZID itself is not resolved - a feed in
another zone is off by its offset). Not implemented: RRULE expansion
(recurring events show up once, at their DTSTART), EXDATE and VALARM.

    events = upcoming(parse_ics(fetch_ics("https://example.org/cal.ics")))
"""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

# Weekday abbreviations, indexed like datetime.weekday() (Monday = 0).
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


@dataclass
class ICSEvent:
    """One VEVENT, reduced to what the calendar card shows."""

    summary: str
    start: datetime
    end: datetime | None = None
    location: str = ""
    all_day: bool = False

    def ends_after(self, moment: datetime) -> bool:
        """True while the event is still running (or has not started)."""
        return (self.end or self.start) >= moment


def local_tz():
    """The machine's local timezone (falls back to UTC)."""
    return datetime.now().astimezone().tzinfo or timezone.utc


#  fetching ------------------------------------------------------------------


def fetch_ics(url: str, timeout: float = 10.0) -> str:
    """Download an ICS feed and return its text.

    ``webcal://`` links (what most calendar apps hand out) are rewritten to
    ``https://``. Anything that is not http(s) raises ``ValueError`` so the
    widget can show a readable message instead of a traceback.
    """
    target = (url or "").strip()
    if target.lower().startswith("webcal://"):
        target = "https://" + target[len("webcal://") :]
    if not target.lower().startswith(("http://", "https://")):
        raise ValueError("Nur http(s)- oder webcal-Links werden unterstützt.")
    request = urllib.request.Request(target, headers={"User-Agent": "UniDocs"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


#  parsing -------------------------------------------------------------------


def parse_ics(text: str) -> list[ICSEvent]:
    """Parse every VEVENT in *text* (events without a DTSTART are skipped)."""
    events: list[ICSEvent] = []
    current: dict | None = None

    for line in _unfold(text):
        upper = line.upper()
        if upper.startswith("BEGIN:VEVENT"):
            current = {}
            continue
        if upper.startswith("END:VEVENT"):
            if current is not None:
                event = _build_event(current)
                if event is not None:
                    events.append(event)
            current = None
            continue
        if current is None or ":" not in line:
            continue

        name, _, value = line.partition(":")
        parts = name.split(";")
        key = parts[0].upper()
        if key not in ("DTSTART", "DTEND", "SUMMARY", "LOCATION"):
            continue
        params = {}
        for part in parts[1:]:
            param_key, _, param_value = part.partition("=")
            params[param_key.upper()] = param_value
        current[key] = (value, params)

    return events


def upcoming(
    events: list[ICSEvent],
    now: datetime | None = None,
    limit: int | None = None,
) -> list[ICSEvent]:
    """Return the events still running or in the future, soonest first."""
    moment = now or datetime.now(local_tz())
    result = [
        event
        for event in sorted(events, key=lambda e: e.start)
        if event.ends_after(moment)
    ]
    return result[:limit] if limit else result


def format_when(event: ICSEvent) -> str:
    """Short German date/time label: ``Mo 24.06.`` or ``Mo 24.06. 14:00``."""
    day = WEEKDAYS[event.start.weekday()]
    if event.all_day:
        return f"{day} {event.start:%d.%m.}"
    return f"{day} {event.start.astimezone():%d.%m. %H:%M}"


#  internals -----------------------------------------------------------------


def _unfold(text: str) -> list[str]:
    """Split into lines, gluing RFC 5545 continuation lines back together."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _build_event(raw: dict) -> ICSEvent | None:
    start, all_day = _parse_dt(*raw.get("DTSTART", ("", {})))
    if start is None:
        return None
    end, _ = _parse_dt(*raw.get("DTEND", ("", {})))
    return ICSEvent(
        summary=_unescape(raw.get("SUMMARY", ("", {}))[0]) or "(ohne Titel)",
        start=start,
        end=end,
        location=_unescape(raw.get("LOCATION", ("", {}))[0]),
        all_day=all_day,
    )


def _parse_dt(value: str, params: dict) -> tuple[datetime | None, bool]:
    """Turn a DTSTART/DTEND value into ``(datetime, all_day)``."""
    value = (value or "").strip()
    if not value:
        return None, False

    is_date = params.get("VALUE", "").upper() == "DATE" or (
        len(value) == 8 and value.isdigit()
    )
    if is_date:
        try:
            day = datetime.strptime(value[:8], "%Y%m%d")
        except ValueError:
            return None, False
        return datetime.combine(day.date(), time.min, local_tz()), True

    is_utc = value.endswith("Z")
    stamp = value[:-1] if is_utc else value
    parsed = None
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            parsed = datetime.strptime(stamp, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        return None, False
    return parsed.replace(tzinfo=timezone.utc if is_utc else local_tz()), False


def _unescape(value: str) -> str:
    """Undo the TEXT escapes iCal uses for commas, semicolons and newlines."""
    return (
        (value or "")
        .replace("\\n", " ")
        .replace("\\N", " ")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )
