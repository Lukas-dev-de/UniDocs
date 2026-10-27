"""Walk the local UniDocs root and hash files.

The scan is deliberately strict: symlinks and special files are skipped,
internal temp folders are ignored, and path names are validated before they
ever reach a provider.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from app_storage.naming import SYNC_TMP_DIRNAME, normalize_rel
from sync.types import FileState, LocalEntry

IGNORED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
IGNORED_SUFFIXES = (".tmp",)
CHUNK_SIZE = 1024 * 1024


class LocalScanError(Exception):
    pass


def is_ignored_name(name: str) -> bool:
    return (
        name in IGNORED_NAMES
        or name.startswith("~$")
        or name.endswith(IGNORED_SUFFIXES)
    )


def scan_local(
    root: Path,
    previous: dict[str, FileState] | None = None,
    want_md5: bool = False,
) -> dict[str, LocalEntry]:
    """Return every file and directory below *root*, keyed by POSIX rel path.

    Hash values from *previous* are reused when size and mtime are unchanged.
    """
    root = Path(root)
    if not root.is_dir():
        raise LocalScanError(f"UniDocs root is missing: {root}")
    previous = previous or {}
    entries: dict[str, LocalEntry] = {}
    case_seen: dict[str, str] = {}

    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        rel_dir = current_path.relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir

        # In-place filtering stops os.walk from descending into them.
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name != SYNC_TMP_DIRNAME and not is_ignored_name(name)
            and not (current_path / name).is_symlink()
        )
        filenames[:] = sorted(
            name
            for name in filenames
            if not is_ignored_name(name) and not (current_path / name).is_symlink()
        )

        if rel_dir:
            _check_path_safety(rel_dir, case_seen)
            entries[rel_dir] = LocalEntry(rel_path=rel_dir, is_dir=True)

        for name in filenames:
            path = current_path / name
            if not path.is_file():
                continue
            rel = f"{rel_dir}/{name}" if rel_dir else name
            _check_path_safety(rel, case_seen)
            stat = path.stat()
            old = previous.get(rel)
            sha256 = old.local_sha256 if old else None
            md5 = old.local_md5 if old else None
            reuse = (
                old is not None
                and old.local_size == stat.st_size
                and old.local_mtime_ns == stat.st_mtime_ns
                and sha256
                and (md5 or not want_md5)
            )
            if not reuse:
                sha256, md5 = hash_file(path, want_md5)
            entries[rel] = LocalEntry(
                rel_path=rel,
                is_dir=False,
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                sha256=sha256,
                md5=md5 if want_md5 else None,
            )

    return entries


def hash_file(path: Path, want_md5: bool) -> tuple[str, str | None]:
    sha = hashlib.sha256()
    md5 = hashlib.md5() if want_md5 else None
    try:
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(CHUNK_SIZE)
                if not chunk:
                    break
                sha.update(chunk)
                if md5 is not None:
                    md5.update(chunk)
    except OSError as exc:
        raise LocalScanError(f"cannot read {path}: {exc}") from exc
    return sha.hexdigest(), md5.hexdigest() if md5 is not None else None


def _check_path_safety(rel: str, case_seen: dict[str, str]) -> None:
    try:
        clean = normalize_rel(rel)
    except ValueError as exc:
        raise LocalScanError(str(exc)) from exc
    if sys.platform in ("win32", "darwin"):
        folded = clean.casefold()
        other = case_seen.get(folded)
        if other is not None and other != clean:
            raise LocalScanError(
                f"paths differ only by case, unsupported here: {other!r} / {clean!r}"
            )
        case_seen[folded] = clean
