"""Shared naming and path-safety helpers for trash and sync.

Kept in ``app_storage`` so both ``TrashStore`` and the sync engine can use it
without a dependency from storage to sync.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

TRASH_DIRNAME = ".trash"
SYNC_TMP_DIRNAME = ".unidocs-tmp"
RESERVED_ROOT_DIRS = {TRASH_DIRNAME, SYNC_TMP_DIRNAME}
MAX_COMPONENT_LENGTH = 100
_DEVICE_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


class UnsafePathError(ValueError):
    """A path escaped the UniDocs root or points into internal folders."""


def normalize_rel(rel: str) -> str:
    """Return a clean POSIX relative path or raise ``UnsafePathError``."""
    if not isinstance(rel, str) or not rel.strip():
        raise UnsafePathError("empty path")
    if "\x00" in rel:
        raise UnsafePathError("NUL byte in path")
    candidate = PurePosixPath(rel.replace("\\", "/"))
    if candidate.is_absolute():
        raise UnsafePathError(f"absolute path: {rel!r}")
    parts = candidate.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise UnsafePathError(f"unsafe path: {rel!r}")
    return candidate.as_posix()


def resolve_inside(root: Path, rel: str) -> Path:
    """Resolve *rel* under *root*, refusing traversal and internal folders."""
    clean = normalize_rel(rel)
    if clean.split("/", 1)[0] in RESERVED_ROOT_DIRS:
        raise UnsafePathError(f"path points into an internal folder: {rel!r}")
    root_resolved = Path(root).resolve()
    target = (root_resolved / clean).resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise UnsafePathError(f"path escapes the root: {rel!r}") from exc
    return target


def sanitize_device_name(name: str, limit: int = 24) -> str:
    cleaned = _DEVICE_SAFE.sub("-", (name or "").strip()).strip("-_")
    return (cleaned[:limit] or "device")


def _split_name(name: str) -> tuple[str, str]:
    if name.startswith(".") and name.count(".") == 1:
        return name, ""
    path = PurePosixPath(name)
    return path.stem, path.suffix


def conflict_name(
    name: str,
    device_name: str,
    when: datetime | None = None,
    counter: int = 0,
) -> str:
    """``lecture.pdf`` -> ``lecture (Konflikt Laptop-20261027-143012).pdf``."""
    device = sanitize_device_name(device_name)
    stamp = (when or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    suffix = f"-{counter}" if counter else ""
    marker = f" (Konflikt {device}-{stamp}{suffix})"
    stem, ext = _split_name(name)
    room = MAX_COMPONENT_LENGTH - len(marker) - len(ext)
    if room < 1:
        room = 1
    return f"{stem[:room]}{marker}{ext}"


def unique_conflict_path(
    path: Path,
    device_name: str,
    when: datetime | None = None,
) -> Path:
    """First free ``<conflict name>`` next to *path*."""
    for counter in range(0, 1000):
        candidate = path.with_name(conflict_name(path.name, device_name, when, counter))
        if not candidate.exists():
            return candidate
    raise OSError(f"could not find a free conflict name for {path}")
