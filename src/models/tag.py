"""
models/tag.py
-------------
A Tag has a stable UUID (id), a display name, and a color hex.
Storing the id in .doc_tags means rename/recolor never orphans assignments.
"""
from __future__ import annotations
import re
import uuid

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


class Tag:
    def __init__(self, id: str, name: str, color: str = DEFAULT_TAG_COLOR):
        self.id = id
        self.name = name
        self.color = color

    # convenience constructor used when creating a brand-new tag
    @classmethod
    def new(cls, name: str, color: str = DEFAULT_TAG_COLOR) -> "Tag":
        return cls(id=str(uuid.uuid4()), name=name, color=color)

    def __repr__(self):
        return f"Tag(id={self.id!r}, name={self.name!r}, color={self.color!r})"