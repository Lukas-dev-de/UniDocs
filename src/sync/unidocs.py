"""UniDocs server provider: sync against a self-hosted UniDocs server.

Replaces Nextcloud/WebDAV when both endpoints are UniDocs itself. The server
exposes ``/api/v1/...`` (see ``src/unidocs_server/api.py``); this provider maps
the ``BaseSyncProvider`` contract onto it. SHA-256 hashes travel with the file
metadata, so the planner can skip unchanged files without downloading them.
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

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

API_PREFIX = "/api/v1"


class UniDocsProvider(BaseSyncProvider):
    hash_kind = "sha256"
    supports_move = True
    supports_dirs = True

    def __init__(
        self,
        base_url: str,
        token: str,
        remote_root: str = "",
        client=None,
        timeout: float = 30.0,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token
        self.remote_root = (remote_root or "").strip("/")
        self._timeout = timeout
        if client is None:
            import httpx

            client = httpx.Client(
                base_url=self.base_url,
                timeout=timeout,
                headers={"Authorization": f"Bearer {token}"},
            )
        self._client = client

    # -- provider API -----------------------------------------------------

    def test_connection(self) -> None:
        try:
            resp = self._client.get(f"{API_PREFIX}/status")
            self._raise_for_status(resp)
        except SyncProviderError:
            raise
        except Exception as exc:
            raise self._map_error(exc, "status") from exc

    def root_exists(self) -> bool:
        # The server's UniDocs folder always exists conceptually; an empty
        # folder is still a valid sync target.
        return True

    def ensure_root(self) -> None:
        return None

    def list_remote(self) -> dict[str, RemoteEntry]:
        result: dict[str, RemoteEntry] = {}
        try:
            resp = self._client.get(f"{API_PREFIX}/files")
            self._raise_for_status(resp)
            data = resp.json()
        except SyncProviderError:
            raise
        except Exception as exc:
            raise self._map_error(exc, "files") from exc
        for item in data.get("files", []):
            rel = normalize_rel(str(item.get("path") or ""))
            if not rel:
                continue
            result[rel] = RemoteEntry(
                rel_path=rel,
                is_dir=bool(item.get("is_dir")),
                size=int(item.get("size") or 0),
                mtime=float(item.get("mtime") or 0.0),
                hash=item.get("sha256"),
                hash_kind="sha256" if item.get("sha256") else None,
                etag=item.get("etag"),
            )
        return result

    def read_text(self, rel: str, max_bytes: int = 65536) -> str:
        rel = normalize_rel(rel)
        try:
            with self._client.stream("GET", self._file_url(rel)) as resp:
                self._raise_for_status(resp)
                data = b""
                for chunk in resp.iter_bytes():
                    data += chunk
                    if len(data) >= max_bytes:
                        break
        except SyncProviderError:
            raise
        except Exception as exc:
            raise self._map_error(exc, rel) from exc
        return data.decode("utf-8", errors="replace")

    def download_file(self, rel: str, local_path: Path) -> None:
        rel = normalize_rel(rel)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._client.stream("GET", self._file_url(rel)) as resp:
                self._raise_for_status(resp)
                with local_path.open("wb") as out:
                    for chunk in resp.iter_bytes():
                        out.write(chunk)
        except SyncProviderError:
            raise
        except Exception as exc:
            raise self._map_error(exc, rel) from exc

    def upload_file(
        self,
        local_path: Path,
        rel: str,
        expected_etag: str | None = None,
    ) -> RemoteEntry:
        rel = normalize_rel(rel)
        headers = {"If-Match": expected_etag} if expected_etag else None
        try:
            with local_path.open("rb") as fh:
                resp = self._client.put(
                    self._file_url(rel), content=fh, headers=headers
                )
            self._raise_for_status(resp)
            data = resp.json()
        except SyncProviderError:
            raise
        except Exception as exc:
            raise self._map_error(exc, rel) from exc
        return RemoteEntry(
            rel_path=rel,
            is_dir=False,
            size=int(data.get("size") or local_path.stat().st_size),
            mtime=float(data.get("mtime") or 0.0),
            hash=data.get("sha256"),
            hash_kind="sha256" if data.get("sha256") else None,
            etag=data.get("etag"),
        )

    def create_dir(self, rel: str) -> RemoteEntry:
        rel = normalize_rel(rel)
        try:
            resp = self._client.post(self._dir_url(rel))
            self._raise_for_status(resp)
        except SyncProviderError:
            raise
        except Exception as exc:
            raise self._map_error(exc, rel) from exc
        return RemoteEntry(rel, True, mtime=0.0)

    def move(self, src_rel: str, dst_rel: str, is_dir: bool) -> None:
        src_rel = normalize_rel(src_rel)
        dst_rel = normalize_rel(dst_rel)
        try:
            resp = self._client.post(
                f"{API_PREFIX}/move",
                json={"from": src_rel, "to": dst_rel, "is_dir": is_dir},
            )
            self._raise_for_status(resp)
        except SyncProviderError:
            raise
        except Exception as exc:
            raise self._map_error(exc, f"{src_rel} -> {dst_rel}") from exc

    def delete(self, rel: str, is_dir: bool, recursive: bool = False) -> None:
        rel = normalize_rel(rel)
        try:
            resp = self._client.delete(self._file_url(rel))
            self._raise_for_status(resp)
        except SyncProviderError:
            raise
        except Exception as exc:
            raise self._map_error(exc, rel) from exc

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    # -- helpers ----------------------------------------------------------

    def _file_url(self, rel: str) -> str:
        rel = rel.strip("/")
        return f"{API_PREFIX}/files/{_quote(rel)}"

    def _dir_url(self, rel: str) -> str:
        rel = rel.strip("/")
        return f"{API_PREFIX}/dirs/{_quote(rel)}"

    def _raise_for_status(self, resp) -> None:
        if resp.is_success or 200 <= resp.status_code < 300:
            return
        status = resp.status_code
        detail = ""
        try:
            detail = str(resp.json().get("detail", ""))
        except Exception:
            pass
        message = detail or f"HTTP {status}"
        if status in (401, 403):
            raise SyncAuthError(message)
        if status == 412:
            raise SyncConflictError(message)
        if status == 404:
            raise SyncNotFoundError(message)
        if status in (409,):
            raise SyncConflictError(message)
        if status == 429 or status >= 500:
            raise SyncNetworkError(message)
        raise SyncProviderError(message)

    def _map_error(self, exc: Exception, rel: str) -> SyncProviderError:
        import httpx

        if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
            return SyncNetworkError(f"{rel}: cannot reach server")
        if isinstance(exc, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
            return SyncNetworkError(f"{rel}: timeout")
        return SyncProviderError(f"{rel}: {exc}")


def _quote(rel: str) -> str:
    """Quote one rel path for use in a URL, keeping directory separators."""
    return "/".join(quote(part, safe="") for part in rel.split("/"))
