"""Soft-delete store for documents and modules.

Deleted files are moved - never unlinked - into ``<root>/.trash/<entry>/``.
An entry carries a ``meta.json`` with the original path and enough info to
restore it later. Because ``.trash`` lives inside the synced root, the entry
travels to other devices through the normal sync engine.

Layout::

    UniDocs/.trash/20261027T143012Z_laptop_a1b2c3d4/
        meta.json
        files/School/Math/lecture.pdf
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app_storage.io_utils import write_json
from app_storage.naming import (
    RESERVED_ROOT_DIRS,
    TRASH_DIRNAME,
    normalize_rel,
    sanitize_device_name,
    unique_conflict_path,
)

TRASH_META_FILENAME = "meta.json"
TRASH_FILES_DIRNAME = "files"
DOC_TAGS_FILENAME = ".doc_tags"
GROUP_MARKER_FILENAME = ".group"
META_FILENAME = ".meta"


class TrashError(Exception):
    """Base error for trash operations."""


class TrashRestoreError(TrashError):
    """The entry cannot be restored to its original place."""


@dataclass
class TrashEntry:
    id: str
    entry_dir: Path
    original_path: str
    kind: str
    deleted_at: str
    device_id: str = ""
    device_name: str = ""
    module_id: str | None = None
    doc_tags: list[str] = field(default_factory=list)
    payload_sha256: str | None = None
    state: str = "ready"

    @property
    def payload(self) -> Path:
        # original_path is validated in _entry_from_meta before an entry is
        # handed out, so this cannot escape the entry directory.
        return self.entry_dir / TRASH_FILES_DIRNAME / Path(self.original_path)

    @property
    def deleted_dt(self) -> datetime | None:
        try:
            return datetime.fromisoformat(self.deleted_at.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None


class TrashStore:
    def __init__(self, root: Path, device_id: str = "", device_name: str = ""):
        self.root = Path(root)
        self.device_id = device_id
        self.device_name = device_name

    @property
    def trash_dir(self) -> Path:
        return self.root / TRASH_DIRNAME

    # -- deleting -------------------------------------------------------------

    def move_to_trash(
        self,
        path: Path,
        kind: str,
        module_id: str | None = None,
        doc_tags: list[str] | None = None,
    ) -> TrashEntry:
        """Move a file or module folder into a fresh trash entry."""
        path = Path(path)
        if not path.exists():
            raise TrashError(f"path does not exist: {path}")
        rel = self._relative_path(path)
        if rel.split("/", 1)[0] in RESERVED_ROOT_DIRS:
            raise TrashError(f"cannot trash an internal path: {rel}")

        entry_id = self._new_entry_id()
        entry_dir = self.trash_dir / entry_id
        meta = {
            "id": entry_id,
            "original_path": rel,
            "kind": kind,
            "deleted_at": _utc_now_iso(),
            "device_id": self.device_id,
            "device_name": self.device_name,
            "module_id": module_id,
            "doc_tags": list(doc_tags or []),
            "payload_sha256": None,
            "state": "pending",
        }
        entry_dir.mkdir(parents=True, exist_ok=False)
        self._write_meta(entry_dir, meta)

        payload = entry_dir / TRASH_FILES_DIRNAME / Path(rel)
        payload.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(payload))

        meta["state"] = "ready"
        self._write_meta(entry_dir, meta)
        return self._entry_from_meta(entry_dir, meta)

    def move_into_entry(self, entry_id: str, path: Path) -> tuple[TrashEntry, Path]:
        """Adopt a local file/folder into an existing (synced) entry.

        Used on the second device: the remote entry already names the original
        path, so the local live copy is moved into that same entry instead of
        creating a duplicate trash item. Returns the entry and the payload
        destination (a module entry may swallow many files).
        """
        entry = self.get_entry(entry_id)
        path = Path(path)
        rel = self._relative_path(path)
        if rel.split("/", 1)[0] in RESERVED_ROOT_DIRS:
            raise TrashError(f"cannot trash an internal path: {rel}")
        if rel == entry.original_path:
            payload = entry.payload
        elif entry.kind == "module" and rel.startswith(entry.original_path + "/"):
            suffix = rel[len(entry.original_path) + 1 :]
            payload = entry.payload / Path(suffix)
        else:
            raise TrashError(
                f"{rel} does not belong to trash entry {entry.original_path}"
            )
        if payload.exists():
            # The other device's payload is already here. Keep both if the
            # local copy differs instead of silently dropping one.
            payload = unique_conflict_path(payload, self.device_name)
        payload.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(payload))
        return entry, payload

    # -- reading --------------------------------------------------------------

    def list_entries(self, include_pending: bool = False) -> list[TrashEntry]:
        if not self.trash_dir.exists():
            return []
        entries: list[TrashEntry] = []
        for entry_dir in self.trash_dir.iterdir():
            if not entry_dir.is_dir():
                continue
            meta_path = entry_dir / TRASH_META_FILENAME
            if not meta_path.exists():
                continue
            meta = self._read_meta(meta_path)
            if not meta:
                continue
            if meta.get("state", "ready") != "ready" and not include_pending:
                continue
            entry = self._entry_from_meta(entry_dir, meta)
            if not entry.original_path:
                continue
            entries.append(entry)
        entries.sort(key=lambda entry: entry.deleted_at, reverse=True)
        return entries

    def get_entry(self, entry_id: str) -> TrashEntry:
        if not entry_id or "/" in entry_id or "\\" in entry_id or entry_id in (".", ".."):
            raise TrashError(f"invalid trash entry id: {entry_id!r}")
        entry_dir = self.trash_dir / entry_id
        meta_path = entry_dir / TRASH_META_FILENAME
        meta = self._read_meta(meta_path)
        if not meta:
            raise TrashError(f"trash entry not found: {entry_id}")
        entry = self._entry_from_meta(entry_dir, meta)
        if not entry.original_path:
            raise TrashError(f"trash entry has an unsafe original path: {entry_id}")
        return entry

    def entries_for_path(self, original_path: str) -> list[TrashEntry]:
        clean = normalize_rel(original_path)
        return [entry for entry in self.list_entries() if entry.original_path == clean]

    def set_payload_hash(self, entry_id: str, sha256: str) -> None:
        entry = self.get_entry(entry_id)
        meta = self._read_meta(entry.entry_dir / TRASH_META_FILENAME)
        meta["payload_sha256"] = sha256
        self._write_meta(entry.entry_dir, meta)

    # -- restoring / purging --------------------------------------------------

    def restore(self, entry_id: str) -> Path:
        entry = self.get_entry(entry_id)
        rel = normalize_rel(entry.original_path)
        if rel.split("/", 1)[0] in RESERVED_ROOT_DIRS:
            raise TrashRestoreError("refusing to restore into an internal folder")
        payload = self._payload_for(entry)
        if not payload.exists():
            raise TrashRestoreError("payload is missing or still syncing")

        target = self.root / Path(rel)
        try:
            target.resolve().relative_to(self.root.resolve())
        except ValueError as exc:
            raise TrashRestoreError("original path escapes the root") from exc

        if entry.kind == "document":
            self._ensure_document_parent(target)
        elif entry.kind == "module":
            self._ensure_module_parent(target, rel)
        else:
            raise TrashRestoreError(f"unknown trash kind: {entry.kind}")

        if target.exists():
            target = unique_conflict_path(target, self.device_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(payload), str(target))

        if entry.kind == "document" and entry.doc_tags:
            self._restore_doc_tags(target, entry.doc_tags)

        shutil.rmtree(entry.entry_dir, ignore_errors=True)
        return target

    def delete_forever(self, entry_id: str) -> None:
        entry = self.get_entry(entry_id)
        self._guard_entry_dir(entry.entry_dir)
        shutil.rmtree(entry.entry_dir, ignore_errors=True)

    def empty(self) -> int:
        return self.purge_older_than(0, now=None, all_entries=True)

    def purge_older_than(
        self,
        days: int,
        now: datetime | None = None,
        eligible_ids: set[str] | None = None,
        all_entries: bool = False,
    ) -> int:
        """Delete ready entries older than *days* (0 = everything)."""
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
        removed = 0
        for entry in self.list_entries():
            if eligible_ids is not None and entry.id not in eligible_ids:
                continue
            deleted = entry.deleted_dt
            if not all_entries and (deleted is None or deleted > cutoff):
                continue
            try:
                self.delete_forever(entry.id)
                removed += 1
            except TrashError:
                continue
        return removed

    def recover(self) -> None:
        """Finish entries interrupted between payload move and meta update."""
        if not self.trash_dir.exists():
            return
        for entry_dir in self.trash_dir.iterdir():
            if not entry_dir.is_dir():
                continue
            meta_path = entry_dir / TRASH_META_FILENAME
            meta = self._read_meta(meta_path)
            if not meta or meta.get("state", "ready") == "ready":
                continue
            try:
                rel = normalize_rel(str(meta.get("original_path") or ""))
                if rel.split("/", 1)[0] in RESERVED_ROOT_DIRS:
                    raise ValueError("reserved path")
                payload = entry_dir / TRASH_FILES_DIRNAME / Path(rel)
                original = self.root / Path(rel)
                if not payload.exists() and original.exists():
                    payload.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(original), str(payload))
                if payload.exists():
                    meta["state"] = "ready"
                    self._write_meta(entry_dir, meta)
                else:
                    shutil.rmtree(entry_dir, ignore_errors=True)
            except (OSError, ValueError):
                continue

    # -- helpers --------------------------------------------------------------

    def _new_entry_id(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        device = sanitize_device_name(self.device_name or self.device_id, limit=8).lower()
        return f"{stamp}_{device}_{uuid.uuid4().hex[:8]}"

    def _relative_path(self, path: Path) -> str:
        try:
            rel = Path(path).resolve().relative_to(self.root.resolve())
        except ValueError as exc:
            raise TrashError(f"path is outside the UniDocs root: {path}") from exc
        return normalize_rel(rel.as_posix())

    def _payload_for(self, entry: TrashEntry) -> Path:
        payload = entry.payload
        if payload.exists():
            return payload
        # Older or hand-edited entries might keep a single file directly under
        # ``files/``; accept that too.
        files_dir = entry.entry_dir / TRASH_FILES_DIRNAME
        if files_dir.exists():
            candidates = [p for p in files_dir.iterdir() if p.name != TRASH_META_FILENAME]
            if len(candidates) == 1:
                return candidates[0]
        return payload

    def _ensure_document_parent(self, target: Path) -> None:
        if not target.parent.is_dir():
            raise TrashRestoreError(
                "the module folder no longer exists; restore the module first"
            )

    def _ensure_module_parent(self, target: Path, rel: str) -> None:
        parent = target.parent
        if parent.exists():
            if not parent.is_dir():
                raise TrashRestoreError("the target path is occupied by a file")
            if (parent / META_FILENAME).exists():
                raise TrashRestoreError("the target group folder is a module")
        elif len(Path(rel).parts) > 1:
            parent.mkdir(parents=True, exist_ok=True)
        # Module inside a group: make sure the folder is still a group.
        if len(Path(rel).parts) > 1:
            marker = parent / GROUP_MARKER_FILENAME
            if not marker.exists():
                marker.touch()

    def _restore_doc_tags(self, target: Path, tag_ids: list[str]) -> None:
        path = target.parent / DOC_TAGS_FILENAME
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data[target.name] = list(tag_ids)
        write_json(path, data)

    def _guard_entry_dir(self, entry_dir: Path) -> None:
        try:
            entry_dir.resolve().relative_to(self.trash_dir.resolve())
        except ValueError as exc:
            raise TrashError("refusing to delete outside the trash folder") from exc

    def _entry_from_meta(self, entry_dir: Path, meta: dict) -> TrashEntry:
        raw_path = str(meta.get("original_path") or "")
        try:
            original_path = normalize_rel(raw_path)
        except ValueError:
            original_path = ""
        if original_path.split("/", 1)[0] in RESERVED_ROOT_DIRS:
            original_path = ""
        return TrashEntry(
            id=str(meta.get("id") or entry_dir.name),
            entry_dir=entry_dir,
            original_path=original_path,
            kind=str(meta.get("kind") or "document"),
            deleted_at=str(meta.get("deleted_at") or ""),
            device_id=str(meta.get("device_id") or ""),
            device_name=str(meta.get("device_name") or ""),
            module_id=meta.get("module_id"),
            doc_tags=list(meta.get("doc_tags") or []),
            payload_sha256=meta.get("payload_sha256"),
            state=str(meta.get("state") or "ready"),
        )

    def _read_meta(self, meta_path: Path) -> dict:
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_meta(self, entry_dir: Path, meta: dict) -> None:
        entry_dir.mkdir(parents=True, exist_ok=True)
        write_json(entry_dir / TRASH_META_FILENAME, meta)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
