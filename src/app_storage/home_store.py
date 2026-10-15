"""
app_storage/home_store.py
-------------------------
Per-group home page config, stored as ``.home.json`` inside the group folder
(the UniDocs root for Home).

Layout
------
UniDocs/
├ .home.json          ← widget config of the Home page
└ School/
    └ .home.json      ← widget config of the "School" group page

Unknown keys are ignored and missing ones fall back to defaults, so a file
written by an older version keeps working. Renaming a group moves its folder
(and with it the ``.home.json``), so the page config travels with the group.

    home = HomeStore(module_store)
    data = home.load("School")
    home.add_quick_link("School", "Moodle", "https://moodle.example.org")
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from app_storage.module_store import HOME_FILENAME, _safe_name

# Widget order a page starts with when it has no .home.json yet.
DEFAULT_WIDGETS = ["quick_links", "recent_modules", "todos", "calendar", "schedule"]

# How many entries the "recent modules" widget remembers.
RECENT_LIMIT = 3

# Quick links without a chosen icon fall back to this one.
DEFAULT_LINK_ICON = "LINK"


def _default_data() -> dict:
    return {
        "widgets": list(DEFAULT_WIDGETS),
        "quick_links": [],
        "recent_modules": [],
        "todos": [],
        "calendar_ics_url": "",
        "schedule": [],
        "widget_options": {},
    }


class HomeStore:
    """Reads and writes the per-group ``.home.json``.

    Parameters
    ----------
    module_store : ModuleStore
        Used only to locate the group folder (and thus the file).
    """

    def __init__(self, module_store):
        self._modules = module_store

    @property
    def root(self) -> Path:
        """The UniDocs root (Home's folder)."""
        return self._modules.root

    #  load / save 

    def load(self, group: str | None) -> dict:
        """Return the page config for *group* (``None`` = Home).

        Missing file, broken JSON or unknown keys all fall back to defaults,
        so callers never have to guard against a half-written file.
        """
        data = _default_data()
        try:
            raw = json.loads(self._path(group).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return data
        if isinstance(raw, dict):
            for key in data:
                if key in raw:
                    data[key] = raw[key]
        if not isinstance(data["widgets"], list):
            data["widgets"] = list(DEFAULT_WIDGETS)
        return data

    def save(self, group: str | None, data: dict) -> None:
        path = self._path(group)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    #  widgets 

    def add_widget(self, group: str | None, key: str) -> None:
        """Show *key* again (appends to the end; no-op if already shown)."""
        data = self.load(group)
        widgets = list(data["widgets"])
        if key not in widgets:
            widgets.append(key)
        data["widgets"] = widgets
        self.save(group, data)

    def remove_widget(self, group: str | None, key: str) -> None:
        """Hide *key* without touching its data (links/todos stay in the file).

        This is what makes removing a card reversible: only the "widgets"
        visibility list changes, everything else in the file is left alone.
        """
        data = self.load(group)
        data["widgets"] = [w for w in data["widgets"] if w != key]
        self.save(group, data)

    def move_widget(self, group: str | None, key: str, delta: int) -> None:
        """Swap *key* with its neighbour above (-1) or below (+1)."""
        data = self.load(group)
        widgets = list(data["widgets"])
        if key not in widgets:
            return
        index = widgets.index(key)
        target = index + delta
        if not 0 <= target < len(widgets):
            return
        widgets.insert(target, widgets.pop(index))
        data["widgets"] = widgets
        self.save(group, data)

    def set_widget_order(self, group: str | None, order: list[str]) -> None:
        """Replace the whole widget order (drag & drop / bulk edits)."""
        data = self.load(group)
        data["widgets"] = list(order)
        self.save(group, data)

    #  widget options 

    def get_widget_options(self, group: str | None, widget_key: str) -> dict:
        """Return the stored options of one widget on a page.

        Missing keys, a broken container or a non-dict value all yield an
        empty dict, so callers can read an option with a plain ``.get(key,
        default)`` and never have to guard against a half-written file.
        """
        options = self.load(group).get("widget_options")
        if not isinstance(options, dict):
            return {}
        value = options.get(widget_key)
        return dict(value) if isinstance(value, dict) else {}

    def set_widget_option(
        self, group: str | None, widget_key: str, key: str, value
    ) -> None:
        """Write a single option of one widget, leaving the others untouched."""
        data = self.load(group)
        options = data.get("widget_options")
        if not isinstance(options, dict):
            options = {}
        widget_options = options.get(widget_key)
        if not isinstance(widget_options, dict):
            widget_options = {}
        widget_options[key] = value
        options[widget_key] = widget_options
        data["widget_options"] = options
        self.save(group, data)

    #  quick links 

    def set_quick_links(self, group: str | None, links: list[dict]) -> None:
        """Replace the whole quick-link list (used by the edit dialog)."""
        data = self.load(group)
        data["quick_links"] = list(links)
        self.save(group, data)

    def add_quick_link(self, group: str | None, label: str, url: str, icon: str = DEFAULT_LINK_ICON) -> dict:
        """Append a quick link and return it."""
        data = self.load(group)
        link = {"id": str(uuid.uuid4()), "label": label, "url": url, "icon": icon}
        data["quick_links"].append(link)
        self.save(group, data)
        return link

    def update_quick_link(self, group: str | None, link_id: str, **fields) -> None:
        """Patch a single quick link (label / url / icon)."""
        data = self.load(group)
        for link in data["quick_links"]:
            if link.get("id") == link_id:
                link.update(fields)
                break
        self.save(group, data)

    def remove_quick_link(self, group: str | None, link_id: str) -> None:
        data = self.load(group)
        data["quick_links"] = [l for l in data["quick_links"] if l.get("id") != link_id]
        self.save(group, data)

    #  todos 

    def add_todo(self, group: str | None, text: str) -> dict:
        data = self.load(group)
        todo = {"id": str(uuid.uuid4()), "text": text, "done": False}
        data["todos"].append(todo)
        self.save(group, data)
        return todo

    def toggle_todo(self, group: str | None, todo_id: str) -> None:
        data = self.load(group)
        for todo in data["todos"]:
            if todo.get("id") == todo_id:
                todo["done"] = not todo.get("done")
                break
        self.save(group, data)

    def remove_todo(self, group: str | None, todo_id: str) -> None:
        data = self.load(group)
        data["todos"] = [t for t in data["todos"] if t.get("id") != todo_id]
        self.save(group, data)

    #  recent modules 

    def recent_modules(self, group: str | None) -> list[str]:
        """Module titles most recently opened in *group*, newest first."""
        return [t for t in self.load(group)["recent_modules"] if isinstance(t, str)]

    def record_module_open(self, group: str | None, title: str) -> None:
        """Push *title* to the front of the recent list (dedupe, capped)."""
        data = self.load(group)
        recent = [t for t in data["recent_modules"] if t != title]
        recent.insert(0, title)
        data["recent_modules"] = recent[:RECENT_LIMIT]
        self.save(group, data)

    #  schedule 

    def set_schedule_entries(self, group: str | None, entries: list[dict]) -> None:
        """Replace the whole timetable (used by the edit dialog)."""
        data = self.load(group)
        data["schedule"] = list(entries)
        self.save(group, data)

    def add_schedule_entry(
        self,
        group: str | None,
        day: int,
        start: str,
        end: str,
        title: str,
        room: str = "",
        color: str = "",
    ) -> dict:
        """Append one timetable entry and return it.

        ``day`` is the weekday like ``datetime.weekday()`` (0 = Monday).
        """
        data = self.load(group)
        entry = {
            "id": str(uuid.uuid4()),
            "day": int(day),
            "start": start,
            "end": end,
            "title": title,
            "room": room,
            "color": color,
        }
        data["schedule"].append(entry)
        self.save(group, data)
        return entry

    def update_schedule_entry(self, group: str | None, entry_id: str, **fields) -> None:
        """Patch a single timetable entry (day / start / end / title / …)."""
        data = self.load(group)
        for entry in data["schedule"]:
            if entry.get("id") == entry_id:
                entry.update(fields)
                break
        self.save(group, data)

    def remove_schedule_entry(self, group: str | None, entry_id: str) -> None:
        data = self.load(group)
        data["schedule"] = [
            e for e in data["schedule"] if e.get("id") != entry_id
        ]
        self.save(group, data)

    #  calendar 

    def set_calendar_ics_url(self, group: str | None, url: str) -> None:
        """Store the group's read-only iCal/ICS feed URL ("" = not connected)."""
        data = self.load(group)
        data["calendar_ics_url"] = url or ""
        self.save(group, data)

    #  private 

    def _path(self, group: str | None) -> Path:
        base = self.root if not group else self.root / _safe_name(group)
        return base / HOME_FILENAME
