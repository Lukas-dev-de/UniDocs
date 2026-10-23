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
another zone is off by its offset).

Repeating events (``RRULE``) are expanded by :func:`expand` for FREQ=DAILY,
WEEKLY (with BYDAY) and MONTHLY, honouring INTERVAL, COUNT and UNTIL, plus the
skipped dates in ``EXDATE`` and single-instance overrides (``RECURRENCE-ID``).
Expansion is bounded: at most ``HORIZON_DAYS`` into the future and
``MAX_OCCURRENCES`` per event. Not implemented: BYSETPOS / BYMONTHDAY /
BYYEARDAY / FREQ=YEARLY, VALARM.

    events = upcoming(parse_ics(fetch_ics("https://example.org/cal.ics")))
"""

from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

try:  # zoneinfo ships with Python 3.9+, but the tz data may be absent.
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - only very old Pythons
    ZoneInfo = None

# Weekday abbreviations, indexed like datetime.weekday() (Monday = 0).
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# How far ahead repeating events are unrolled, and how many instances of one
# event are produced at most (a timetable never needs more than that).
HORIZON_DAYS = 400
MAX_OCCURRENCES = 500

# RRULE BYDAY codes -> datetime.weekday().
_BYDAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


@dataclass
class ICSEvent:
    """One VEVENT, reduced to what the calendar card shows."""

    summary: str
    start: datetime
    end: datetime | None = None
    location: str = ""
    all_day: bool = False
    # Recurrence data straight from the feed (see :func:`expand`).
    rrule: str = ""
    exdates: tuple[datetime, ...] = ()
    uid: str = ""
    # Set on an event that replaces one instance of a series.
    recurrence_id: datetime | None = None

    def ends_after(self, moment: datetime) -> bool:
        """True while the event is still running (or has not started)."""
        return (self.end or self.start) >= moment


def local_tz():
    """The machine's local timezone (falls back to UTC).

    A real ``ZoneInfo`` is preferred over the fixed offset
    ``datetime.now().astimezone().tzinfo`` returns: a timetable that runs from
    October into November must keep its wall-clock time across the DST switch.
    """
    name = _local_zone_name()
    if name and ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    return datetime.now().astimezone().tzinfo or timezone.utc


def zone_for(tzid: str):
    """Timezone for an iCal ``TZID`` parameter, falling back to local time."""
    if tzid and ZoneInfo is not None:
        try:
            return ZoneInfo(tzid)
        except Exception:
            pass
    return local_tz()


def _local_zone_name() -> str | None:
    """Best guess at the machine's IANA zone name (``Europe/Berlin``)."""
    env = os.environ.get("TZ", "").lstrip(":")
    if env and "/" in env:
        return env
    try:
        # /etc/localtime is usually a symlink into .../zoneinfo/Europe/Berlin.
        target = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in target:
            return target.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    try:
        name = Path("/etc/timezone").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return name or None


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
        if key not in (
            "DTSTART",
            "DTEND",
            "SUMMARY",
            "LOCATION",
            "RRULE",
            "EXDATE",
            "UID",
            "RECURRENCE-ID",
        ):
            continue
        params = {}
        for part in parts[1:]:
            param_key, _, param_value = part.partition("=")
            params[param_key.upper()] = param_value
        if key == "EXDATE":
            # The same key may appear on several lines; keep all of them.
            current.setdefault(key, []).append((value, params))
        else:
            current[key] = (value, params)

    return events


def upcoming(
    events: list[ICSEvent],
    now: datetime | None = None,
    limit: int | None = None,
) -> list[ICSEvent]:
    """Return the events still running or in the future, soonest first.

    Repeating events are unrolled first (:func:`expand`), so a weekly timetable
    whose DTSTART lies months in the past still yields upcoming dates.
    """
    moment = now or datetime.now(local_tz())
    result = [
        event
        for event in sorted(expand(events, moment), key=lambda e: e.start)
        if event.ends_after(moment)
    ]
    return result[:limit] if limit else result


def expand(
    events: list[ICSEvent], now: datetime | None = None
) -> list[ICSEvent]:
    """Unroll RRULE series into single occurrences up to the horizon.

    *now* only anchors the horizon, so a series that ended long ago produces
    nothing while a running one yields its next dates. Occurrences listed in
    EXDATE are dropped; a series instance replaced by a RECURRENCE-ID event is
    skipped in favour of that event (which is kept as a normal, single entry).
    """
    moment = now or datetime.now(local_tz())
    horizon = moment + timedelta(days=HORIZON_DAYS)

    overrides: dict[str, set[int]] = {}
    for event in events:
        if event.recurrence_id is not None and event.uid:
            overrides.setdefault(event.uid, set()).add(_stamp(event.recurrence_id))

    result: list[ICSEvent] = []
    for event in events:
        rule = _parse_rrule(event.rrule)
        if rule is None:
            # Single occurrence, or an override that stands in for its own.
            result.append(event)
            continue

        skipped = {_stamp(exdate) for exdate in event.exdates}
        skipped |= overrides.get(event.uid, set())
        for start in _occurrences(event, rule, horizon):
            if _stamp(start) in skipped:
                continue
            result.append(_shift(event, start))
    return result


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
    recurrence_id, _ = _parse_dt(*raw.get("RECURRENCE-ID", ("", {})))
    return ICSEvent(
        summary=_unescape(raw.get("SUMMARY", ("", {}))[0]) or "(ohne Titel)",
        start=start,
        end=end,
        location=_unescape(raw.get("LOCATION", ("", {}))[0]),
        all_day=all_day,
        rrule=(raw.get("RRULE", ("", {}))[0] or "").strip(),
        exdates=tuple(_parse_list(raw.get("EXDATE") or [])),
        uid=(raw.get("UID", ("", {}))[0] or "").strip(),
        recurrence_id=recurrence_id,
    )


def _parse_list(items: list[tuple[str, dict]]) -> list[datetime]:
    """All datetimes of one or more EXDATE lines (values comma-separated)."""
    moments: list[datetime] = []
    for value, params in items:
        for part in value.split(","):
            moment, _ = _parse_dt(part, params)
            if moment is not None:
                moments.append(moment)
    return moments


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
    if is_utc:
        return parsed.replace(tzinfo=timezone.utc), False
    return parsed.replace(tzinfo=zone_for(params.get("TZID", ""))), False


#  recurrence ----------------------------------------------------------------


def _parse_rrule(value: str) -> dict | None:
    """Split ``FREQ=WEEKLY;INTERVAL=2;BYDAY=MO`` into a dict (None if empty)."""
    text = (value or "").strip()
    if not text:
        return None
    rule: dict[str, str] = {}
    for part in text.split(";"):
        key, _, val = part.partition("=")
        if key:
            rule[key.strip().upper()] = val.strip()
    return rule or None


def _occurrences(event: ICSEvent, rule: dict, horizon: datetime):
    """Yield the start datetimes of *event*, DTSTART included, ascending."""
    start = event.start
    try:
        interval = max(1, int(rule.get("INTERVAL", "1") or 1))
    except ValueError:
        interval = 1
    try:
        count = int(rule.get("COUNT", "0") or 0)
    except ValueError:
        count = 0
    until = _until(rule.get("UNTIL"))
    # COUNT is a total including DTSTART; without it the horizon bounds the run.
    budget = min(count or MAX_OCCURRENCES, MAX_OCCURRENCES)

    freq = (rule.get("FREQ") or "").upper()
    emitted = 0
    for candidate in _candidates(start, freq, interval, rule):
        if until is not None and candidate > until:
            return
        if candidate > horizon:
            return
        yield candidate
        emitted += 1
        if emitted >= budget:
            return


def _candidates(start: datetime, freq: str, interval: int, rule: dict):
    """Iterator over all possible start times of the series, ascending."""
    if freq == "WEEKLY":
        days = sorted(
            {
                _BYDAY[code]
                for code in (rule.get("BYDAY") or "").upper().split(",")
                if code in _BYDAY
            }
        ) or [start.weekday()]
        # Anchor on the Monday of DTSTART's week so INTERVAL counts whole weeks.
        anchor = (start - timedelta(days=start.weekday())).date()
        step = 0
        while True:
            week = anchor + timedelta(weeks=step * interval)
            for day in days:
                candidate = datetime.combine(week + timedelta(days=day), start.timetz())
                if candidate >= start:
                    yield candidate
            step += 1
    elif freq == "MONTHLY":
        step = 0
        while True:
            candidate = _add_months(start, step * interval)
            if candidate is None:
                # The month has no such day (e.g. 31st) - RFC 5545 skips it.
                if step > MAX_OCCURRENCES:
                    return
                step += 1
                continue
            yield candidate
            step += 1
    else:
        # DAILY and anything not understood: keep the plain day/week step.
        step_days = 1 if freq == "DAILY" else 7
        step = 0
        while True:
            yield start + timedelta(days=step * interval * step_days)
            step += 1


def _until(value: str | None) -> datetime | None:
    """RRULE UNTIL is inclusive; a date-only value covers its whole day."""
    if not value:
        return None
    moment, all_day = _parse_dt(value, {})
    if moment is None:
        return None
    return moment + timedelta(days=1) - timedelta(seconds=1) if all_day else moment


def _add_months(start: datetime, months: int) -> datetime | None:
    """Shift by whole months, or ``None`` when that month is too short."""
    index = start.month - 1 + months
    year = start.year + index // 12
    month = index % 12 + 1
    try:
        return start.replace(year=year, month=month)
    except ValueError:
        return None


def _shift(event: ICSEvent, start: datetime) -> ICSEvent:
    """One occurrence of a series: same length, moved to *start*."""
    delta = start - event.start
    return replace(
        event,
        start=start,
        end=event.end + delta if event.end is not None else None,
        rrule="",
        exdates=(),
        recurrence_id=None,
    )


def _stamp(moment: datetime) -> int:
    """Comparable key for exdates / recurrence-ids (whole seconds)."""
    return int(moment.timestamp())


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
