"""
models/document.py
------------------
One file inside a module folder.

A document carries no data of its own beyond what the filesystem says: the
title is the file stem, the path is absolute, and the tags are resolved from
the module's ``.doc_tags`` file when the module is loaded.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from models.tag import Tag


@dataclass
class Document:
    title: str
    description: str = ""
    filepath: str = ""
    tags: list[Tag] = field(default_factory=list)