"""Persistent per-provider sync state.

The state is the only memory of what the two sides looked like after the last
successful sync. It is keyed by provider identity *and* local root, so pointing
the app at another folder can never look like a mass deletion.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

from platformdirs import user_state_dir

from app_storage.io_utils import write_json
from sync.types import FileState, LocalEntry, RemoteEntry, utc_now_iso

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def state_key(provider_identity: str, local_root: Path) -> str:
    raw = f"{provider_identity}\n{Path(local_root).resolve()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def default_state_path(provider_identity: str, local_root: Path) -> Path:
    base = Path(user_state_dir("UniDocs", appauthor=False)) / "sync"
    return base / f"state-{state_key(provider_identity, local_root)}.json"


class SyncState:
    def __init__(
        self,
        provider_identity: str,
        local_root: Path,
        provider_label: str = "",
        path: Path | None = None,
    ):
        self.provider_identity = provider_identity
        self.local_root = Path(local_root)
        self.provider_label = provider_label
        self.path = Path(path) if path is not None else default_state_path(
            provider_identity, self.local_root
        )
        self.files: dict[str, FileState] = {}
        self.last_sync = ""
        self.had_corruption = False

    # -- reading --------------------------------------------------------------

    def load(self) -> SyncState:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self
        except (OSError, json.JSONDecodeError):
            self._backup_corrupt()
            return self
        if not isinstance(raw, dict) or int(raw.get("version") or 0) != SCHEMA_VERSION:
            # Unknown/old schema: keep a copy, start clean. A first sync makes
            # conflict copies instead of deleting anything.
            self._backup_corrupt(suffix="schema")
            return self
        files = raw.get("files")
        if isinstance(files, dict):
            self.files = {
                str(rel): FileState.from_dict(data) for rel, data in files.items() if rel
            }
        self.last_sync = str(raw.get("last_sync") or "")
        return self

    def get(self, rel_path: str) -> FileState | None:
        return self.files.get(rel_path)

    def previous_local_hashes(self) -> dict[str, FileState]:
        """Snapshot for ``scan_local`` hash reuse (copy, planner mutates)."""
        return dict(self.files)

    # -- writing --------------------------------------------------------------

    def record_local(
        self,
        entry: LocalEntry,
        remote: RemoteEntry,
        remote_hash_kind: str | None = None,
    ) -> None:
        kind = "dir" if entry.is_dir else "file"
        self.files[entry.rel_path] = FileState(
            kind=kind,
            local_sha256=entry.sha256,
            local_md5=entry.md5,
            local_size=entry.size,
            local_mtime_ns=entry.mtime_ns,
            remote_hash=remote.hash,
            remote_hash_kind=remote.hash_kind or remote_hash_kind,
            remote_size=remote.size,
            remote_mtime=remote.mtime,
            remote_etag=remote.etag,
            synced_at=utc_now_iso(),
        )

    def record_remote_only(self, entry: RemoteEntry) -> None:
        """Remote path that exists only remotely (no local counterpart yet)."""
        self.files[entry.rel_path] = FileState(
            kind="dir" if entry.is_dir else "file",
            remote_hash=entry.hash,
            remote_hash_kind=entry.hash_kind,
            remote_size=entry.size,
            remote_mtime=entry.mtime,
            remote_etag=entry.etag,
            synced_at=utc_now_iso(),
        )

    def drop(self, rel_path: str) -> None:
        self.files.pop(rel_path, None)

    def save(self) -> None:
        self.last_sync = utc_now_iso()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_json(
            self.path,
            {
                "version": SCHEMA_VERSION,
                "provider_key": self.provider_identity,
                "provider_label": self.provider_label,
                "local_root": str(self.local_root),
                "last_sync": self.last_sync,
                "files": {rel: fs.to_dict() for rel, fs in self.files.items()},
            },
        )

    # -- corruption -----------------------------------------------------------

    def _backup_corrupt(self, suffix: str = "corrupt") -> None:
        self.had_corruption = True
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = self.path.with_name(f"{self.path.stem}.{suffix}-{stamp}{self.path.suffix}")
        try:
            os.replace(self.path, backup)
            logger.warning("sync state was unreadable, moved to %s", backup)
        except OSError:
            try:
                self.path.unlink()
            except OSError:
                pass
