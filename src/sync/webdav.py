"""WebDAV provider (Nextcloud, ownCloud, Synology, generic WebDAV)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from app_storage.naming import normalize_rel
from sync.base import (
    BaseSyncProvider,
    SyncAuthError,
    SyncConflictError,
    SyncNetworkError,
    SyncNotFoundError,
    SyncProviderError,
)
from sync.types import RemoteEntry

logger = logging.getLogger(__name__)


class WebDAVProvider(BaseSyncProvider):
    hash_kind = None  # WebDAV has no reliable content hash
    supports_move = True
    supports_dirs = True

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        remote_root: str = "UniDocs",
        client=None,
    ):
        if client is None:
            import webdav4.client as wd

            client = wd.Client(base_url=base_url, auth=(username, password), retry=True)
        self._client = client
        self.remote_root = remote_root.strip("/") or "UniDocs"
        self._root_ensured = False

    # -- provider API -----------------------------------------------------

    def test_connection(self) -> None:
        try:
            self._client.info("")
        except Exception as exc:
            raise self._map_error(exc, "base URL") from exc

    def root_exists(self) -> bool:
        try:
            return bool(self._client.exists(self.remote_root))
        except Exception as exc:
            raise self._map_error(exc, self.remote_root) from exc

    def ensure_root(self) -> None:
        self._ensure_root()

    def list_remote(self) -> dict[str, RemoteEntry]:
        result: dict[str, RemoteEntry] = {}
        if not self.root_exists():
            return result
        queue = [self.remote_root]
        seen: set[str] = set()
        while queue:
            current = queue.pop()
            if current in seen:
                continue
            seen.add(current)
            try:
                items = self._client.ls(current, detail=True)
            except Exception as exc:
                raise self._map_error(exc, current) from exc
            for item in items:
                if not isinstance(item, dict):
                    continue
                rel = self._relative_name(item.get("name") or "")
                if rel is None or rel == "":
                    continue
                is_dir = item.get("type") == "directory"
                entry = RemoteEntry(
                    rel,
                    is_dir,
                    size=int(item.get("content_length") or 0),
                    mtime=_to_timestamp(item.get("modified")),
                    hash=None,
                    hash_kind=None,
                    etag=item.get("etag"),
                )
                result[rel] = entry
                if is_dir:
                    queue.append(f"{self.remote_root}/{rel}")
        return result

    def read_text(self, rel: str, max_bytes: int = 65536) -> str:
        rel = normalize_rel(rel)
        try:
            with self._client.open(self._full(rel), "rb") as fh:
                data = fh.read(max_bytes)
        except Exception as exc:
            raise self._map_error(exc, rel) from exc
        return data.decode("utf-8", errors="replace")

    def download_file(self, rel: str, local_path: Path) -> None:
        rel = normalize_rel(rel)
        try:
            self._client.download_file(self._full(rel), str(local_path))
        except Exception as exc:
            raise self._map_error(exc, rel) from exc

    def upload_file(
        self,
        local_path: Path,
        rel: str,
        expected_etag: str | None = None,
    ) -> RemoteEntry:
        rel = normalize_rel(rel)
        self._ensure_dir(_parent(rel))
        headers = {"If-Match": expected_etag} if expected_etag else None
        try:
            self._client.upload_file(
                str(local_path),
                self._full(rel),
                overwrite=True,
                headers=headers,
            )
            info = self._client.info(self._full(rel))
        except Exception as exc:
            raise self._map_error(exc, rel) from exc
        is_dir = False
        return RemoteEntry(
            rel,
            is_dir,
            size=int(info.get("content_length") or Path(local_path).stat().st_size),
            mtime=_to_timestamp(info.get("modified")),
            etag=info.get("etag"),
        )

    def create_dir(self, rel: str) -> RemoteEntry:
        rel = normalize_rel(rel)
        self._ensure_dir(rel)
        return RemoteEntry(rel, True, mtime=0.0)

    def move(self, src_rel: str, dst_rel: str, is_dir: bool) -> None:
        src_rel = normalize_rel(src_rel)
        dst_rel = normalize_rel(dst_rel)
        self._ensure_dir(_parent(dst_rel))
        try:
            self._client.move(self._full(src_rel), self._full(dst_rel), overwrite=False)
        except Exception as exc:
            raise self._map_error(exc, f"{src_rel} -> {dst_rel}") from exc

    def delete(self, rel: str, is_dir: bool, recursive: bool = False) -> None:
        rel = normalize_rel(rel)
        try:
            self._client.remove(self._full(rel))
        except Exception as exc:
            raise self._map_error(exc, rel) from exc

    def close(self) -> None:
        try:
            self._client.http.close()
        except Exception:
            pass

    # -- helpers ----------------------------------------------------------

    def _full(self, rel: str) -> str:
        rel = rel.strip("/")
        return f"{self.remote_root}/{rel}" if rel else self.remote_root

    def _relative_name(self, name: str) -> str | None:
        """`name` from webdav4 is relative to the base URL."""
        clean = name.strip("/")
        if clean == self.remote_root:
            return ""
        prefix = self.remote_root + "/"
        if not clean.startswith(prefix):
            return None
        return normalize_rel(clean[len(prefix) :])

    def _ensure_root(self) -> None:
        if self._root_ensured:
            return
        try:
            self._client.mkdir(self.remote_root)
        except Exception as exc:
            if not self._is_already_exists(exc):
                raise self._map_error(exc, self.remote_root) from exc
        self._root_ensured = True

    def _ensure_dir(self, rel: str) -> None:
        self._ensure_root()
        if not rel or rel == ".":
            return
        components = PurePosixPath(normalize_rel(rel)).parts
        current = ""
        for part in components:
            current = f"{current}/{part}" if current else part
            try:
                self._client.mkdir(self._full(current))
            except Exception as exc:
                if not self._is_already_exists(exc):
                    raise self._map_error(exc, current) from exc

    @staticmethod
    def _is_already_exists(exc: Exception) -> bool:
        return type(exc).__name__ == "ResourceAlreadyExists"

    def _map_error(self, exc: Exception, rel: str) -> SyncProviderError:
        name = type(exc).__name__
        if name == "ResourceNotFound":
            return SyncNotFoundError(f"{rel}: not found")
        if name == "ResourceAlreadyExists" or name == "ResourceConflict":
            return SyncConflictError(f"{rel}: {exc}")
        if name in ("ForbiddenOperation", "ResourceLocked"):
            return SyncAuthError(f"{rel}: {exc}")
        if name in ("InsufficientStorage", "BadGatewayError"):
            return SyncNetworkError(f"{rel}: {exc}")
        if name in ("HTTPError", "HTTPStatusError"):
            status = getattr(getattr(exc, "response", None), "status_code", 0)
            if status in (401, 403):
                return SyncAuthError(f"{rel}: {exc}")
            if status == 412:
                return SyncConflictError(f"{rel}: precondition failed")
            if status == 404:
                return SyncNotFoundError(f"{rel}: not found")
            if status in (429, 500, 502, 503, 504) or status >= 500:
                return SyncNetworkError(f"{rel}: {exc}")
        return SyncProviderError(f"{rel}: {exc}")


def _parent(rel: str) -> str:
    parts = PurePosixPath(rel).parts
    return "/".join(parts[:-1])


def _to_timestamp(value) -> float:
    if not value:
        return 0.0
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()
