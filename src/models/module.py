"""
models/module.py
----------------
A module: one folder in a group (or in the UniDocs root) plus its documents.

The ``.meta`` payload belongs here too (``to_meta`` / ``from_meta``), so the
store only has to read and write files. The icon is stored by name, because a
``ft.Icons`` value cannot be serialised.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import flet as ft

from models.document import Document


@dataclass
class Module:
    title: str = "New Module"
    description: str = ""
    icon: Any = ft.Icons.SQUARE
    # Accent colour as a "#RRGGBB" string. ``None`` means "follow the theme",
    # which is how every module created before v2.3.0 behaves.
    color: str | None = None
    # Name of the group folder this module lives in; ``None`` means the
    # UniDocs root (shown as "Home" in the sidebar).
    group: str | None = None
    documents: list[Document] = field(default_factory=list)
    # Stable identity, kept in `.meta`. Survives renames and moving between
    # groups, so the UI can recognise "the same module" without comparing
    # titles. Modules created before v2.5.1 get one on first load.
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def add_document(self, document: Document) -> None:
        self.documents.append(document)

    #  serialisation

    def to_meta(self, icon_name: str) -> dict:
        """Payload for the module's ``.meta`` file.

        *icon_name* is the ``ft.Icons`` attribute name (see
        ``module_store._icon_to_name``); the icon itself is not serialisable.
        """
        return {
            "id": self.id,
            "description": self.description,
            "icon": icon_name,
            "color": self.color,
        }

    @classmethod
    def from_meta(
        cls,
        title: str,
        meta: dict,
        icon,
        group: str | None = None,
    ) -> "Module":
        """Build a module from its folder name, ``.meta`` payload and icon.

        Missing or null keys fall back to the defaults, so a ``.meta`` written
        by an older version keeps working.
        """
        return cls(
            title=title,
            description=meta.get("description") or "",
            icon=icon,
            color=meta.get("color") or None,
            group=group,
            id=meta.get("id") or str(uuid.uuid4()),
        )