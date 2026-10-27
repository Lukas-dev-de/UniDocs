"""In-memory provider for engine tests (no network)."""

import hashlib
from pathlib import Path, PurePosixPath

from sync.base import (
    BaseSyncProvider,
    SyncNetworkError,
    SyncNotFoundError,
    SyncProviderError,
)
from sync.types import RemoteEntry


class FakeProvider(BaseSyncProvider):
    def __init__(self, hash_kind="sha256", supports_move=True):
        self.hash_kind = hash_kind
        self.supports_move = supports_move
        self.supports_dirs = True
        self.files: dict[str, bytes] = {}
        self.dirs: set[str] = set()
        self.mtimes: dict[str, float] = {}
        self._clock = 1000.0
        self.root_ready = True
        self.fail_list = False
        self.fail_uploads = False
        self.fail_downloads = False
        self.uploads = 0
        self.downloads = 0
        self.moves = 0
        self.deletes = 0
        self.upload_etags: dict[str, str | None] = {}
        self.download_hook = None

    # -- test control -----------------------------------------------------

    def put(self, rel: str, data: bytes):
        self._ensure_parents(rel)
        self.files[rel] = data
        self._clock += 1
        self.mtimes[rel] = self._clock

    def get(self, rel: str) -> bytes:
        return self.files[rel]

    def _hash(self, data: bytes):
        if self.hash_kind == "sha256":
            return hashlib.sha256(data).hexdigest()
        if self.hash_kind == "md5":
            return hashlib.md5(data).hexdigest()
        return None

    def _entry(self, rel: str) -> RemoteEntry:
        data = self.files[rel]
        return RemoteEntry(
            rel,
            False,
            size=len(data),
            mtime=self.mtimes.get(rel, self._clock),
            hash=self._hash(data),
            hash_kind=self.hash_kind if self.hash_kind else None,
            etag=f'"{self._hash(data)}"',
            remote_id=rel,
        )

    def _ensure_parents(self, rel: str):
        parts = PurePosixPath(rel).parts[:-1]
        current = ""
        for part in parts:
            current = f"{current}/{part}" if current else part
            self.dirs.add(current)

    # -- provider API -----------------------------------------------------

    def test_connection(self):
        if self.fail_list:
            raise SyncNetworkError("offline")

    def root_exists(self):
        return self.root_ready

    def ensure_root(self):
        self.root_ready = True

    def list_remote(self):
        if self.fail_list:
            raise SyncNetworkError("listing failed")
        entries = {
            rel: RemoteEntry(rel, True, mtime=self._clock) for rel in self.dirs
        }
        entries.update({rel: self._entry(rel) for rel in self.files})
        return entries

    def read_text(self, rel: str, max_bytes: int = 65536) -> str:
        if rel not in self.files:
            raise SyncNotFoundError(rel)
        return self.files[rel][:max_bytes].decode("utf-8")

    def download_file(self, rel: str, local_path: Path):
        if self.fail_downloads:
            raise SyncNetworkError("download failed")
        if rel not in self.files:
            raise SyncNotFoundError(rel)
        self.downloads += 1
        Path(local_path).write_bytes(self.files[rel])
        if self.download_hook is not None:
            self.download_hook(rel)

    def upload_file(self, local_path: Path, rel: str, expected_etag=None):
        if self.fail_uploads:
            raise SyncNetworkError("upload failed")
        data = Path(local_path).read_bytes()
        self._ensure_parents(rel)
        self.files[rel] = data
        self._clock += 1
        self.mtimes[rel] = self._clock
        self.uploads += 1
        self.upload_etags[rel] = expected_etag
        return self._entry(rel)

    def create_dir(self, rel: str):
        self._ensure_parents(rel)
        self.dirs.add(rel)
        self._clock += 1
        return RemoteEntry(rel, True, mtime=self._clock)

    def move(self, src: str, dst: str, is_dir: bool):
        if src == dst:
            return
        self._ensure_parents(dst)
        if is_dir:
            for rel in list(self.files):
                if rel.startswith(src + "/"):
                    new_rel = dst + "/" + rel[len(src) + 1 :]
                    self.files[new_rel] = self.files.pop(rel)
                    if rel in self.mtimes:
                        self.mtimes[new_rel] = self.mtimes.pop(rel)
            for rel in list(self.dirs):
                if rel == src or rel.startswith(src + "/"):
                    moved = dst + rel[len(src) :] if rel != src else dst
                    self.dirs.add(moved)
                    self.dirs.discard(rel)
            self.dirs.add(dst)
        else:
            if src not in self.files:
                raise SyncNotFoundError(src)
            self.files[dst] = self.files.pop(src)
            if src in self.mtimes:
                self.mtimes[dst] = self.mtimes.pop(src)
        self.moves += 1

    def delete(self, rel: str, is_dir: bool, recursive: bool = False):
        if is_dir:
            if rel not in self.dirs:
                raise SyncNotFoundError(rel)
            children = [p for p in self.dirs if p.startswith(rel + "/")]
            if children and not recursive:
                raise SyncProviderError(f"directory not empty: {rel}")
            for key in list(self.files):
                if key.startswith(rel + "/"):
                    self.files.pop(key)
            for key in list(self.dirs):
                if key == rel or key.startswith(rel + "/"):
                    self.dirs.discard(key)
        else:
            if rel not in self.files:
                raise SyncNotFoundError(rel)
            self.files.pop(rel)
        self.deletes += 1
