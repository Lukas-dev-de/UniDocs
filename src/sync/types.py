"""Plain data types shared by the sync engine, planner and providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class LocalEntry:
    rel_path: str
    is_dir: bool
    size: int = 0
    mtime_ns: int = 0
    sha256: str | None = None
    md5: str | None = None


@dataclass(frozen=True)
class RemoteEntry:
    rel_path: str
    is_dir: bool
    size: int = 0
    mtime: float = 0.0
    hash: str | None = None
    hash_kind: str | None = None
    etag: str | None = None
    remote_id: str | None = None


@dataclass
class FileState:
    """Last successfully synced snapshot of one relative path."""

    kind: str = "file"
    local_sha256: str | None = None
    local_md5: str | None = None
    local_size: int = 0
    local_mtime_ns: int = 0
    remote_hash: str | None = None
    remote_hash_kind: str | None = None
    remote_size: int = 0
    remote_mtime: float = 0.0
    remote_etag: str | None = None
    synced_at: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> FileState:
        if not isinstance(data, dict):
            return cls()
        local = data.get("local") if isinstance(data.get("local"), dict) else {}
        remote = data.get("remote") if isinstance(data.get("remote"), dict) else {}
        return cls(
            kind=str(data.get("kind") or "file"),
            local_sha256=local.get("sha256"),
            local_md5=local.get("md5"),
            local_size=int(local.get("size") or 0),
            local_mtime_ns=int(local.get("mtime_ns") or 0),
            remote_hash=remote.get("hash"),
            remote_hash_kind=remote.get("hash_kind"),
            remote_size=int(remote.get("size") or 0),
            remote_mtime=float(remote.get("mtime") or 0.0),
            remote_etag=remote.get("etag"),
            synced_at=str(data.get("synced_at") or ""),
        )

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "local": {
                "sha256": self.local_sha256,
                "md5": self.local_md5,
                "size": self.local_size,
                "mtime_ns": self.local_mtime_ns,
            },
            "remote": {
                "hash": self.remote_hash,
                "hash_kind": self.remote_hash_kind,
                "size": self.remote_size,
                "mtime": self.remote_mtime,
                "etag": self.remote_etag,
            },
            "synced_at": self.synced_at,
        }


@dataclass
class SyncAction:
    """One unit of work planned by the planner and executed by the engine."""

    kind: str
    rel_path: str = ""
    dest_rel: str = ""
    is_dir: bool = False
    entry_id: str = ""
    note: str = ""


@dataclass
class SyncReport:
    uploaded: int = 0
    downloaded: int = 0
    deleted_local: int = 0
    deleted_remote: int = 0
    moved: int = 0
    conflicts: int = 0
    trashed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    aborted: bool = False
    cancelled: bool = False
    message: str = ""

    @property
    def changed(self) -> int:
        return (
            self.uploaded
            + self.downloaded
            + self.deleted_local
            + self.deleted_remote
            + self.moved
            + self.conflicts
            + self.trashed
        )

    def summary(self) -> str:
        if self.aborted:
            return self.message or "Sync aborted"
        if self.cancelled:
            return "Sync cancelled"
        parts = []
        if self.uploaded:
            parts.append(f"{self.uploaded} uploaded")
        if self.downloaded:
            parts.append(f"{self.downloaded} downloaded")
        if self.trashed:
            parts.append(f"{self.trashed} moved to trash")
        if self.conflicts:
            parts.append(f"{self.conflicts} conflict(s)")
        if self.deleted_local:
            parts.append(f"{self.deleted_local} removed locally")
        if self.deleted_remote:
            parts.append(f"{self.deleted_remote} removed remotely")
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        if not parts:
            return self.message or "Everything is up to date"
        return ", ".join(parts)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
