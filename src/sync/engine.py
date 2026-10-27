"""Execute a sync plan against a provider.

All network and filesystem IO lives here. The planner decides *what* to do;
this module only performs it and records the new state.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Callable

from app_storage.io_utils import write_json
from app_storage.naming import SYNC_TMP_DIRNAME, normalize_rel
from app_storage.trash_store import TrashError, TrashStore
from sync.base import (
    BaseSyncProvider,
    SyncAuthError,
    SyncConflictError,
    SyncProviderError,
)
from sync.local_scan import LocalScanError, hash_file, scan_local
from sync.planner import plan_sync
from sync.state import SyncState
from sync.types import LocalEntry, RemoteEntry, SyncAction, SyncReport

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int, str], None]


class SyncEngine:
    def __init__(
        self,
        provider: BaseSyncProvider,
        root: Path,
        state: SyncState,
        device_name: str = "Device",
        progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ):
        self.provider = provider
        self.root = Path(root)
        self.state = state
        self.device_name = device_name
        self.progress = progress
        self.cancel_event = cancel_event or threading.Event()
        self.want_md5 = provider.hash_kind == "md5"
        self.trash = TrashStore(self.root, device_name=device_name)
        self.temp_dir = self.root / SYNC_TMP_DIRNAME
        self.local: dict[str, LocalEntry] = {}
        self.remote: dict[str, RemoteEntry] = {}
        self._dirty = 0
        self._last_save = time.monotonic()
        self._delete_fresh: dict[str, RemoteEntry] | None = None
        self._delete_refresh_failed = False

    # -- main -----------------------------------------------------------------

    def run(self) -> SyncReport:
        report = SyncReport()
        try:
            self.provider.test_connection()
        except SyncProviderError as exc:
            return self._abort(report, f"Connection failed: {exc}")
        except Exception as exc:
            return self._abort(report, f"Connection failed: {exc}")

        try:
            root_exists = self.provider.root_exists()
        except SyncProviderError as exc:
            return self._abort(report, f"Remote nicht erreichbar: {exc}")

        if not root_exists:
            if self.state.files:
                return self._abort(
                    report,
                    "The remote folder is missing although this device synced before. "
                    "Aborting so no data is deleted.",
                )
            try:
                self.provider.ensure_root()
            except SyncProviderError as exc:
                return self._abort(report, f"Could not create the remote folder: {exc}")

        self.trash.recover()
        try:
            self.local = scan_local(
                self.root,
                previous=self.state.previous_local_hashes(),
                want_md5=self.want_md5,
            )
        except LocalScanError as exc:
            return self._abort(report, f"Local scan failed: {exc}")

        try:
            self.remote = self.provider.list_remote()
        except SyncProviderError as exc:
            return self._abort(report, f"Remote listing failed: {exc}")

        if self.state.files and not self.remote:
            return self._abort(
                report,
                "The remote folder is empty although the sync state knows files. "
                "Aborting so no data is deleted.",
            )

        actions = plan_sync(
            self.local,
            self.remote,
            self.state.files,
            provider_hash_kind=self.provider.hash_kind,
            supports_move=self.provider.supports_move,
            device_name=self.device_name,
        )

        blocked = self._mass_delete_guard(actions)
        if blocked:
            return self._abort(report, blocked)

        total = len(actions)
        try:
            for index, action in enumerate(actions, start=1):
                if self.cancel_event.is_set():
                    report.cancelled = True
                    break
                self._emit("sync", index - 1, total, action.rel_path)
                try:
                    self._execute(action, report)
                except SyncAuthError:
                    raise
                except (
                    SyncProviderError,
                    OSError,
                    ValueError,
                    TrashError,
                    LocalScanError,
                    json.JSONDecodeError,
                ) as exc:
                    logger.warning(
                        "sync action %s %s failed: %s", action.kind, action.rel_path, exc
                    )
                    report.errors.append(f"{action.kind} {action.rel_path}: {exc}")
                self._maybe_save()
        finally:
            self._emit("sync", total, total, "")
            try:
                self.state.save()
            except OSError as exc:
                report.errors.append(f"Saving sync state: {exc}")
            shutil.rmtree(self.temp_dir, ignore_errors=True)

        report.message = report.summary()
        return report

    # -- execute --------------------------------------------------------------

    def _execute(self, action: SyncAction, report: SyncReport) -> None:
        kind = action.kind
        rel = action.rel_path

        if kind == "record":
            local_entry = self.local.get(rel)
            remote_entry = self.remote.get(rel)
            if local_entry and remote_entry:
                self.state.record_local(local_entry, remote_entry, self.provider.hash_kind)
            return

        if kind == "mkdir_local":
            path = self._local_path(rel)
            path.mkdir(parents=True, exist_ok=True)
            entry = self._local_dir_entry(rel, path)
            self.local[rel] = entry
            remote_entry = self.remote.get(rel) or RemoteEntry(rel, True)
            self.state.record_local(entry, remote_entry, self.provider.hash_kind)
            return

        if kind == "mkdir_remote":
            remote_entry = self.provider.create_dir(rel)
            self.remote[rel] = remote_entry
            entry = self.local.get(rel) or LocalEntry(rel, True)
            self.state.record_local(entry, remote_entry, self.provider.hash_kind)
            return

        if kind == "download":
            remote_entry = self.remote[rel]
            entry = self._download(rel, rel, remote_entry)
            self.local[rel] = entry
            self.state.record_local(entry, remote_entry, self.provider.hash_kind)
            report.downloaded += 1
            return

        if kind == "upload":
            self._upload(rel, report)
            return

        if kind == "conflict":
            self._conflict(rel, action.dest_rel, report)
            return

        if kind == "move_remote":
            self._move_remote(rel, action.dest_rel, action.is_dir)
            report.moved += 1
            return

        if kind == "move_local":
            self._move_local(rel, action.dest_rel)
            report.moved += 1
            return

        if kind == "trash_remote_move":
            self._trash_remote_move(rel, action.dest_rel)
            report.trashed += 1
            return

        if kind == "trash_local_adopt":
            self._trash_local_adopt(rel, action.entry_id)
            report.trashed += 1
            return

        if kind == "trash_local_new":
            if self._trash_local_new(rel, action.is_dir):
                report.trashed += 1
            else:
                report.skipped += 1
            return

        if kind == "delete_local":
            if self._delete_local(rel, action.is_dir):
                report.deleted_local += 1
            else:
                report.skipped += 1
            return

        if kind == "delete_remote":
            if self._delete_remote(rel, action.is_dir):
                report.deleted_remote += 1
            else:
                report.skipped += 1
            return

        if kind == "drop_state":
            self.state.drop(rel)
            return

        if kind == "type_conflict":
            report.errors.append(f"{rel}: file/folder conflict, skipped")
            return

        raise ValueError(f"unknown action: {kind}")

    # -- operations -----------------------------------------------------------

    def _upload(self, rel: str, report: SyncReport) -> None:
        path = self._local_path(rel)
        entry = self.local.get(rel)
        if entry is None or entry.is_dir:
            entry = self._local_file_entry(rel, path)
        self._ensure_remote_parent(rel)
        base = self.state.get(rel)
        # A stale If-Match would fail forever when the remote copy is gone.
        expected = base.remote_etag if base and rel in self.remote else None
        remote_entry = self.provider.upload_file(path, rel, expected_etag=expected)
        self.remote[rel] = remote_entry

        # Record the snapshot that was actually uploaded. If the file changed
        # during the upload, the next scan sees a different local hash and
        # uploads the newer version again.
        self.state.record_local(entry, remote_entry, self.provider.hash_kind)
        report.uploaded += 1

    def _download(self, rel: str, dest_rel: str, remote_entry: RemoteEntry) -> LocalEntry:
        target = self._local_path(dest_rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = self._temp_path()
        self.provider.download_file(rel, temp)
        actual_size = temp.stat().st_size
        if remote_entry.size and actual_size != remote_entry.size:
            temp.unlink(missing_ok=True)
            raise SyncProviderError(
                f"size mismatch for {rel}: expected {remote_entry.size}, got {actual_size}"
            )
        sha256, md5 = hash_file(temp, self.want_md5)
        if remote_entry.hash:
            if remote_entry.hash_kind == "sha256" and remote_entry.hash != sha256:
                temp.unlink(missing_ok=True)
                raise SyncProviderError(f"hash mismatch for {rel}")
            if remote_entry.hash_kind == "md5" and md5 and remote_entry.hash != md5:
                temp.unlink(missing_ok=True)
                raise SyncProviderError(f"hash mismatch for {rel}")
        scanned = self.local.get(dest_rel)
        if target.exists():
            current = target.stat()
            if (
                scanned is None
                or current.st_size != scanned.size
                or current.st_mtime_ns != scanned.mtime_ns
            ):
                temp.unlink(missing_ok=True)
                raise SyncConflictError(
                    f"{dest_rel} changed while syncing; retry creates a conflict copy"
                )
        os.replace(temp, target)
        if remote_entry.mtime:
            try:
                os.utime(target, (remote_entry.mtime, remote_entry.mtime))
            except OSError:
                pass
        stat = target.stat()
        return LocalEntry(
            dest_rel,
            False,
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            sha256=sha256,
            md5=md5 if self.want_md5 else None,
        )

    def _conflict(self, rel: str, dest_rel: str, report: SyncReport) -> None:
        remote_entry = self.remote[rel]
        dest_entry = self._download(rel, dest_rel, remote_entry)
        self.local[dest_rel] = dest_entry
        self._ensure_remote_parent(dest_rel)
        dest_remote = self.provider.upload_file(
            self._local_path(dest_rel), dest_rel, expected_etag=None
        )
        self.remote[dest_rel] = dest_remote
        self.state.record_local(dest_entry, dest_remote, self.provider.hash_kind)

        self._upload(rel, report)
        report.conflicts += 1
        report.downloaded += 1

    def _move_remote(self, src: str, dst: str, is_dir: bool) -> None:
        self._ensure_remote_parent(dst)
        self.provider.move(src, dst, is_dir)
        remote_entry = self.remote.get(src)
        self._rekey_state(src, dst)
        self._move_map_key(self.local, src, dst)
        self._move_map_key(self.remote, src, dst)
        if remote_entry is not None:
            self.remote[dst] = RemoteEntry(
                dst,
                is_dir,
                size=remote_entry.size,
                mtime=0.0,
                hash=remote_entry.hash,
                hash_kind=remote_entry.hash_kind,
                etag=None,
                remote_id=remote_entry.remote_id,
            )

    def _move_local(self, src: str, dst: str) -> None:
        src_path = self._local_path(src)
        dst_path = self._local_path(dst)
        if dst_path.exists():
            raise SyncConflictError(f"{dst} appeared while syncing")
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src_path, dst_path)
        self._rekey_state(src, dst)
        self._move_map_key(self.local, src, dst)
        self._move_map_key(self.remote, src, dst)

    def _trash_remote_move(self, src: str, dst: str) -> None:
        self._ensure_remote_parent(dst)
        self.provider.move(src, dst, False)
        old_remote = self.remote.get(src)
        local_payload = self.local.get(dst)
        self._rekey_state(src, dst)
        self._move_map_key(self.local, src, dst)
        self._move_map_key(self.remote, src, dst)
        if local_payload is not None and old_remote is not None:
            moved = RemoteEntry(
                dst,
                False,
                size=old_remote.size or local_payload.size,
                mtime=0.0,
                hash=old_remote.hash or local_payload.sha256,
                hash_kind=old_remote.hash_kind or ("sha256" if local_payload.sha256 else None),
                remote_id=old_remote.remote_id,
            )
            self.state.record_local(local_payload, moved, self.provider.hash_kind)
            self.remote[dst] = moved

    def _trash_local_adopt(self, rel: str, entry_id: str) -> None:
        meta_rel = f".trash/{entry_id}/meta.json"
        meta_path = self._local_path(meta_rel)
        if not meta_path.exists():
            text = self.provider.read_text(meta_rel)
            data = json.loads(text)
            if not isinstance(data, dict):
                raise SyncProviderError(f"invalid trash meta: {meta_rel}")
            write_json(meta_path, data)
        try:
            local_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SyncProviderError(f"unreadable trash meta: {meta_rel}") from exc
        if not _meta_covers(local_meta, rel):
            raise SyncProviderError(f"trash meta path mismatch: {meta_rel}")
        old_local = self.local.get(rel)
        _entry, dest = self.trash.move_into_entry(entry_id, self._local_path(rel))
        self.state.drop(rel)
        payload_rel = dest.resolve().relative_to(self.root.resolve()).as_posix()
        self.state.drop(payload_rel)
        self.local.pop(rel, None)
        payload_remote = self.remote.get(payload_rel)
        if old_local is not None and payload_remote is not None:
            payload_local = LocalEntry(
                payload_rel,
                False,
                size=old_local.size,
                mtime_ns=old_local.mtime_ns,
                sha256=old_local.sha256,
                md5=old_local.md5,
            )
            self.local[payload_rel] = payload_local
            if self._same_content(payload_local, payload_remote):
                self.state.record_local(
                    payload_local, payload_remote, self.provider.hash_kind
                )

    def _trash_local_new(self, rel: str, is_dir: bool) -> bool:
        path = self._local_path(rel)
        if path.exists():
            self.trash.move_to_trash(path, "module" if is_dir else "document")
            moved = True
        else:
            # A parent folder was already moved into the trash in this run.
            moved = False
        for key in list(self.state.files):
            if key == rel or key.startswith(rel + "/"):
                self.state.drop(key)
        self._drop_map_subtree(self.local, rel)
        return moved

    def _drop_map_subtree(self, mapping: dict, prefix: str) -> None:
        for key in list(mapping):
            if key == prefix or key.startswith(prefix + "/"):
                mapping.pop(key, None)

    def _delete_local(self, rel: str, is_dir: bool) -> bool:
        path = self._local_path(rel)
        if is_dir:
            if not path.is_dir():
                self.state.drop(rel)
                return True
            if any(path.iterdir()):
                return False
            path.rmdir()
        else:
            entry = self.local.get(rel)
            if entry is not None and path.exists():
                stat = path.stat()
                if stat.st_size != entry.size or stat.st_mtime_ns != entry.mtime_ns:
                    return False  # edited after the scan, keep it for the next run
            path.unlink(missing_ok=True)
        self.state.drop(rel)
        self.local.pop(rel, None)
        return True

    def _delete_remote(self, rel: str, is_dir: bool) -> bool:
        fresh = self._fresh_remote_for_delete()
        if fresh is None:
            return False
        listed = fresh.get(rel)
        snapshot = self.remote.get(rel)
        if listed is None:
            # Someone deleted it after our listing: nothing left to do.
            self.state.drop(rel)
            self.remote.pop(rel, None)
            return True
        if snapshot is not None and not _remote_entries_equal(snapshot, listed):
            return False
        if is_dir and any(other.startswith(rel + "/") for other in self.remote):
            return False
        self.provider.delete(rel, is_dir, recursive=False)
        self.state.drop(rel)
        self.remote.pop(rel, None)
        return True

    def _fresh_remote_for_delete(self) -> dict[str, RemoteEntry] | None:
        """One refresh right before the delete phase narrows the race window."""
        if self._delete_refresh_failed:
            return None
        if self._delete_fresh is None:
            try:
                self._delete_fresh = self.provider.list_remote()
            except SyncProviderError as exc:
                logger.warning("could not re-list before deletes: %s", exc)
                self._delete_refresh_failed = True
                return None
        return self._delete_fresh

    # -- state helpers --------------------------------------------------------

    def _rekey_state(self, src: str, dst: str) -> None:
        rekeyed: dict[str, object] = {}
        for rel, file_state in list(self.state.files.items()):
            if rel == src:
                new_rel = dst
            elif rel.startswith(src + "/"):
                new_rel = dst + "/" + rel[len(src) + 1 :]
            else:
                continue
            # Keep the last known remote stamp. A server may change it on MOVE;
            # that only causes one extra download, never a blind overwrite.
            rekeyed[new_rel] = file_state
            self.state.drop(rel)
        for new_rel, file_state in rekeyed.items():
            self.state.files[new_rel] = file_state
        self._mark_dirty()

    @staticmethod
    def _move_map_key(mapping: dict, src: str, dst: str) -> None:
        moved = {}
        for rel in list(mapping):
            if rel == src:
                new_rel = dst
            elif rel.startswith(src + "/"):
                new_rel = dst + "/" + rel[len(src) + 1 :]
            else:
                continue
            moved[new_rel] = mapping.pop(rel)
        mapping.update(moved)

    def _mark_dirty(self) -> None:
        self._dirty += 1

    def _maybe_save(self) -> None:
        if self._dirty >= 50 or time.monotonic() - self._last_save > 10.0:
            self.state.save()
            self._dirty = 0
            self._last_save = time.monotonic()

    # -- path helpers ---------------------------------------------------------

    def _local_path(self, rel: str) -> Path:
        clean = normalize_rel(rel)
        root_resolved = self.root.resolve()
        target = (root_resolved / clean).resolve()
        try:
            target.relative_to(root_resolved)
        except ValueError as exc:
            raise ValueError(f"path escapes root: {rel}") from exc
        return target

    def _ensure_remote_parent(self, rel: str) -> None:
        parts = PurePosixPath(rel).parts[:-1]
        current = ""
        for part in parts:
            current = f"{current}/{part}" if current else part
            if current not in self.remote:
                self.remote[current] = self.provider.create_dir(current)

    def _temp_path(self) -> Path:
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        return self.temp_dir / uuid.uuid4().hex

    def _same_content(self, local: LocalEntry, remote: RemoteEntry) -> bool:
        if not remote.hash:
            return local.size == remote.size
        if remote.hash_kind == "sha256":
            return local.sha256 == remote.hash
        if remote.hash_kind == "md5":
            return local.md5 is not None and local.md5 == remote.hash
        return False

    def _local_file_entry(self, rel: str, path: Path) -> LocalEntry:
        stat = path.stat()
        sha256, md5 = hash_file(path, self.want_md5)
        return LocalEntry(
            rel,
            False,
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            sha256=sha256,
            md5=md5 if self.want_md5 else None,
        )

    @staticmethod
    def _local_dir_entry(rel: str, path: Path) -> LocalEntry:
        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0
        return LocalEntry(rel, True, mtime_ns=mtime_ns)

    # -- guard / progress -----------------------------------------------------

    def _mass_delete_guard(self, actions: list[SyncAction]) -> str:
        if len(self.state.files) < 20:
            return ""
        deletes = [
            action
            for action in actions
            if action.kind in ("delete_local", "delete_remote")
            and not action.rel_path.startswith(".trash/")
        ]
        if len(deletes) <= len(self.state.files) / 2:
            return ""
        explained = any(
            action.kind in ("trash_remote_move", "trash_local_adopt")
            for action in actions
        )
        if explained:
            return ""
        return (
            f"{len(deletes)} of {len(self.state.files)} paths would be deleted. "
            "Aborting as a mass-delete guard."
        )

    def _emit(self, phase: str, done: int, total: int, rel: str) -> None:
        if self.progress is None:
            return
        try:
            self.progress(phase, done, total, rel)
        except Exception:
            logger.debug("progress callback failed", exc_info=True)

    def _abort(self, report: SyncReport, message: str) -> SyncReport:
        report.aborted = True
        report.message = message
        logger.warning("sync aborted: %s", message)
        return report


def _remote_entries_equal(first: RemoteEntry, second: RemoteEntry) -> bool:
    if first.is_dir or second.is_dir:
        return first.is_dir and second.is_dir
    if first.hash and second.hash:
        return first.hash == second.hash
    return first.size == second.size and abs(first.mtime - second.mtime) <= 2.0


def _meta_covers(meta: dict, rel: str) -> bool:
    """A document entry covers exactly its path; a module entry its subtree."""
    if not isinstance(meta, dict):
        return False
    original = str(meta.get("original_path") or "")
    if not original:
        return False
    if rel == original:
        return True
    return meta.get("kind") == "module" and rel.startswith(original + "/")
