"""
models/tag.py
-------------
A Tag has a stable UUID (id), a display name, and a color hex.
Storing the id in .doc_tags means rename/recolor never orphans assignments.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

DEFAULT_TAG_COLOR = "#1565C0"

_DIGITS = re.compile(r"(\d+)")


def natural_sort_key(name: str) -> list:
    """Sort key that orders w2 before w10 (digit runs compared as numbers).

    The pattern always splits into text, number, text, number..., so element
    types line up across keys and lists stay comparable.
    """
    return [
        int(part) if part.isdigit() else part.lower()
        for part in _DIGITS.split(name or "")
    ]


@dataclass
class Tag:
    id: str
    name: str
    color: str = DEFAULT_TAG_COLOR

    # convenience constructor used when creating a brand-new tag
    @classmethod
    def new(cls, name: str, color: str = DEFAULT_TAG_COLOR) -> "Tag":
        return cls(id=str(uuid.uuid4()), name=name, color=color)

    #  serialisation (the shape used in tags.json and in the UI) 

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "color": self.color}

    @classmethod
    def from_dict(cls, data: dict) -> "Tag":
        return cls(
            id=data["id"],
            name=data["name"],
            color=data.get("color") or DEFAULT_TAG_COLOR,
        )