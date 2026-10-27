"""Google Drive provider (My Drive, scope ``drive.file``).

Only files created by UniDocs are visible with this scope. A pre-existing
"UniDocs" folder made in the Drive web UI is therefore invisible; the app
creates and remembers its own folder id.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime
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

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_KEY = "gdrive_token"
FOLDER_MIME = "application/vnd.google-apps.folder"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"
FIELDS = "id,name,mimeType,size,modifiedTime,md5Checksum,parents,trashed"
ROOT_NAME = "UniDocs"
BUNDLED_CLIENT_SECRET = Path(__file__).parent.parent / "gdrive_client_secret.json"


def resolve_client_secret(configured: str = "") -> str:
    """Find the desktop OAuth client JSON.

    Order: user-selected file, build-time env, bundled file. A release can ship
    one client so the user only clicks "Connect & sync"; the installed-app
    secret is not confidential, but bundling it means Google can revoke it if
    it gets abused.
    """
    if configured and Path(configured).is_file():
        return configured
    env = os.environ.get("UNIDOCS_GDRIVE_CLIENT_SECRET", "").strip()
    if env and Path(env).is_file():
        return env
    if BUNDLED_CLIENT_SECRET.is_file():
        return str(BUNDLED_CLIENT_SECRET)
    return configured


def load_credentials(
    client_secret_path: str,
    token_store,
    interactive: bool = False,
):
    """Load a saved token, refresh it, or run the loopback OAuth flow."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    raw = token_store.get_secret(TOKEN_KEY) if token_store else None
    creds = None
    if raw:
        try:
            creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
        except (ValueError, json.JSONDecodeError):
            creds = None

    if creds is not None and creds.valid:
        return creds
    if creds is not None and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            if token_store:
                token_store.set_secret(TOKEN_KEY, creds.to_json())
            return creds
        except Exception as exc:
            logger.warning("Google token refresh failed: %s", exc)
            creds = None

    if not interactive:
        raise SyncAuthError("Google Drive is not connected")
    if not client_secret_path or not Path(client_secret_path).is_file():
        raise SyncAuthError("Google client_secret.json is missing")
    flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not getattr(creds, "refresh_token", None):
        raise SyncAuthError("Google hat keinen Refresh-Token geliefert")
    if token_store:
        token_store.set_secret(TOKEN_KEY, creds.to_json())
    return creds


def build_service(credentials):
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=credentials, cache_discovery=False)


class GDriveProvider(BaseSyncProvider):
    hash_kind = "md5"
    supports_move = True
    supports_dirs = True

    def __init__(
        self,
        service=None,
        credentials=None,
        folder_id: str = "",
        token_store=None,
        interactive: bool = False,
        client_secret_path: str = "",
    ):
        self._credentials = credentials
        self._token_store = token_store
        self._interactive = interactive
        self._client_secret_path = client_secret_path
        if service is None:
            if credentials is None:
                credentials = load_credentials(
                    client_secret_path, token_store, interactive=interactive
                )
                self._credentials = credentials
            service = build_service(credentials)
        self._service = service
        self.folder_id = folder_id
        self._rel_to_id: dict[str, str] = {}
        self._id_to_rel: dict[str, str] = {}
        self._root_ready = bool(folder_id)

    # -- provider API -----------------------------------------------------

    def test_connection(self) -> None:
        self._refresh_if_needed()
        try:
            self._retry(lambda: self._service.about().get(fields="user").execute())
        except Exception as exc:
            raise self._map_error(exc) from exc

    def root_exists(self) -> bool:
        self._refresh_if_needed()
        self._root_ready = False
        try:
            if self.folder_id:
                data = self._retry(
                    lambda: self._service.files()
                    .get(fileId=self.folder_id, fields=FIELDS)
                    .execute()
                )
                if data.get("trashed"):
                    return False
                self._root_ready = True
                return True
            found = self._find_child("root", ROOT_NAME, is_dir=True)
            if found:
                self.folder_id = found["id"]
                self._root_ready = True
                return True
            return False
        except Exception as exc:
            mapped = self._map_error(exc)
            if isinstance(mapped, SyncNotFoundError):
                return False
            raise mapped from exc

    def ensure_root(self) -> None:
        if self._root_ready and self.folder_id:
            return
        self._refresh_if_needed()
        if self.root_exists():
            return
        body = {"name": ROOT_NAME, "mimeType": FOLDER_MIME, "parents": ["root"]}
        try:
            data = self._retry(
                lambda: self._service.files().create(body=body, fields=FIELDS).execute()
            )
        except Exception as exc:
            raise self._map_error(exc) from exc
        self.folder_id = data["id"]
        self._root_ready = True

    def list_remote(self) -> dict[str, RemoteEntry]:
        self._refresh_if_needed()
        if not self.root_exists():
            return {}
        result: dict[str, RemoteEntry] = {}
        self._rel_to_id = {}
        self._id_to_rel = {self.folder_id: ""}
        queue: list[tuple[str, str]] = [(self.folder_id, "")]
        seen: set[str] = set()
        while queue:
            folder_id, prefix = queue.pop()
            if folder_id in seen:
                continue
            seen.add(folder_id)
            try:
                children = self._list_children(folder_id)
            except Exception as exc:
                raise self._map_error(exc) from exc
            for item in children:
                name = item.get("name") or ""
                if not name:
                    continue
                rel = f"{prefix}/{name}" if prefix else name
                try:
                    rel = normalize_rel(rel)
                except ValueError:
                    logger.warning("skipping unsafe Drive name: %r", rel)
                    continue
                mime = item.get("mimeType") or ""
                if mime == SHORTCUT_MIME or (
                    mime.startswith("application/vnd.google-apps.")
                    and mime != FOLDER_MIME
                ):
                    logger.warning("skipping native Google file: %s", rel)
                    continue
                is_dir = mime == FOLDER_MIME
                entry = _entry_from_file(item, rel)
                result[rel] = entry
                self._rel_to_id[rel] = item["id"]
                self._id_to_rel[item["id"]] = rel
                if is_dir:
                    queue.append((item["id"], rel))
        return result

    def read_text(self, rel: str, max_bytes: int = 65536) -> str:
        rel = normalize_rel(rel)
        file_id = self._resolve(rel)
        try:
            data = self._retry(
                lambda: self._service.files().get_media(fileId=file_id).execute()
            )
        except Exception as exc:
            raise self._map_error(exc) from exc
        return bytes(data)[:max_bytes].decode("utf-8", errors="replace")

    def download_file(self, rel: str, local_path: Path) -> None:
        rel = normalize_rel(rel)
        file_id = self._resolve(rel)
        from googleapiclient.http import MediaIoBaseDownload

        try:
            request = self._service.files().get_media(fileId=file_id)
            if not hasattr(request, "uri"):
                # Test doubles and unusual transports return a plain request.
                Path(local_path).write_bytes(request.execute())
                return
            with open(local_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request, chunksize=8 * 1024 * 1024)
                done = False
                while not done:
                    _status, done = downloader.next_chunk()
        except Exception as exc:
            raise self._map_error(exc) from exc

    def upload_file(
        self,
        local_path: Path,
        rel: str,
        expected_etag: str | None = None,
    ) -> RemoteEntry:
        self._refresh_if_needed()
        rel = normalize_rel(rel)
        parent_rel = _parent(rel)
        parent_id = self._ensure_folder_path(parent_rel)
        name = PurePosixPath(rel).name
        cached_id = self._rel_to_id.get(rel)
        existing = {"id": cached_id} if cached_id else self._find_child(
            parent_id, name, is_dir=False
        )
        from googleapiclient.http import MediaFileUpload

        size = Path(local_path).stat().st_size
        media = MediaFileUpload(
            str(local_path),
            mimetype="application/octet-stream",
            resumable=size > 5 * 1024 * 1024,
            chunksize=8 * 1024 * 1024,
        )
        try:
            if existing:
                request = self._service.files().update(
                    fileId=existing["id"],
                    media_body=media,
                    body={"name": name},
                    fields=FIELDS,
                )
            else:
                request = self._service.files().create(
                    body={"name": name, "parents": [parent_id]},
                    media_body=media,
                    fields=FIELDS,
                )
            if expected_etag and hasattr(request, "headers"):
                request.headers["If-Match"] = expected_etag
            data = self._retry(lambda: request.execute())
        except Exception as exc:
            raise self._map_error(exc) from exc
        self._rel_to_id[rel] = data["id"]
        self._id_to_rel[data["id"]] = rel
        return _entry_from_file(data, rel)

    def create_dir(self, rel: str) -> RemoteEntry:
        rel = normalize_rel(rel)
        folder_id = self._ensure_folder_path(rel)
        return RemoteEntry(
            rel,
            True,
            mtime=0.0,
            remote_id=folder_id,
        )

    def move(self, src_rel: str, dst_rel: str, is_dir: bool) -> None:
        self._refresh_if_needed()
        src_rel = normalize_rel(src_rel)
        dst_rel = normalize_rel(dst_rel)
        file_id = self._resolve(src_rel)
        new_parent_id = self._ensure_folder_path(_parent(dst_rel))
        old_parent_id = self._ensure_folder_path(_parent(src_rel))
        try:
            self._retry(
                lambda: self._service.files()
                .update(
                    fileId=file_id,
                    addParents=new_parent_id,
                    removeParents=old_parent_id,
                    body={"name": PurePosixPath(dst_rel).name},
                    fields=FIELDS,
                )
                .execute()
            )
        except Exception as exc:
            raise self._map_error(exc) from exc
        self._rekey_cache(src_rel, dst_rel, file_id)

    def delete(self, rel: str, is_dir: bool, recursive: bool = False) -> None:
        self._refresh_if_needed()
        rel = normalize_rel(rel)
        file_id = self._resolve(rel)
        permanent = recursive or rel.startswith(".trash/")
        try:
            if permanent:
                self._retry(
                    lambda: self._service.files().delete(fileId=file_id).execute()
                )
            else:
                self._retry(
                    lambda: self._service.files()
                    .update(fileId=file_id, body={"trashed": True}, fields=FIELDS)
                    .execute()
                )
        except Exception as exc:
            raise self._map_error(exc) from exc
        self._rel_to_id.pop(rel, None)
        self._id_to_rel.pop(file_id, None)
        for key in list(self._rel_to_id):
            if key.startswith(rel + "/"):
                self._rel_to_id.pop(key, None)

    def close(self) -> None:
        try:
            self._service.close()
        except Exception:
            pass

    # -- Drive helpers ----------------------------------------------------

    def _resolve(self, rel: str) -> str:
        if rel not in self._rel_to_id:
            # Direct provider use (tests, one-off reads) may happen before the
            # engine's list pass; refresh the cache once.
            self.list_remote()
        if rel in self._rel_to_id:
            return self._rel_to_id[rel]
        raise SyncNotFoundError(f"{rel}: not in Drive listing")

    def _ensure_folder_path(self, rel: str) -> str:
        if not rel:
            if self._root_ready and self.folder_id:
                return self.folder_id
            self.ensure_root()
            return self.folder_id
        current_id = self._ensure_folder_path(_parent(rel))
        name = PurePosixPath(rel).name
        cached = self._rel_to_id.get(rel)
        if cached:
            return cached
        found = self._find_child(current_id, name, is_dir=True)
        if found:
            self._rel_to_id[rel] = found["id"]
            self._id_to_rel[found["id"]] = rel
            return found["id"]
        body = {"name": name, "mimeType": FOLDER_MIME, "parents": [current_id]}
        try:
            data = self._retry(
                lambda: self._service.files().create(body=body, fields=FIELDS).execute()
            )
        except Exception as exc:
            raise self._map_error(exc) from exc
        self._rel_to_id[rel] = data["id"]
        self._id_to_rel[data["id"]] = rel
        return data["id"]

    def _find_child(self, parent_id: str, name: str, is_dir: bool):
        escaped = name.replace("\\", "\\\\").replace("'", "\\'")
        mime_clause = (
            f"and mimeType = '{FOLDER_MIME}'" if is_dir else f"and mimeType != '{FOLDER_MIME}'"
        )
        query = (
            f"'{parent_id}' in parents and name = '{escaped}' "
            f"and trashed = false {mime_clause}"
        )
        try:
            items = self._list_query(query)
        except Exception as exc:
            raise self._map_error(exc) from exc
        if not items:
            return None
        if len(items) > 1:
            items.sort(key=lambda item: item.get("id", ""))
            logger.warning("duplicate Drive name %r, using id %s", name, items[0].get("id"))
        return items[0]

    def _list_children(self, folder_id: str) -> list[dict]:
        query = f"'{folder_id}' in parents and trashed = false"
        return self._list_query(query)

    def _list_query(self, query: str) -> list[dict]:
        items: list[dict] = []
        page_token = None
        while True:
            def call(page_token=page_token):
                return (
                    self._service.files()
                    .list(
                        q=query,
                        pageSize=1000,
                        fields=f"nextPageToken, files({FIELDS})",
                        pageToken=page_token,
                    )
                    .execute()
                )

            data = self._retry(call)
            items.extend(data.get("files", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                return items

    def _rekey_cache(self, src: str, dst: str, file_id: str) -> None:
        moved = {}
        for rel, ident in list(self._rel_to_id.items()):
            if rel == src:
                new_rel = dst
            elif rel.startswith(src + "/"):
                new_rel = dst + rel[len(src) :]
            else:
                continue
            moved[new_rel] = ident
            self._rel_to_id.pop(rel, None)
            self._id_to_rel[ident] = new_rel
        self._rel_to_id.update(moved)
        self._rel_to_id[dst] = file_id
        self._id_to_rel[file_id] = dst

    def _refresh_if_needed(self) -> None:
        creds = self._credentials
        if creds is None or not getattr(creds, "expired", False):
            return
        if not getattr(creds, "refresh_token", None):
            raise SyncAuthError("Google Drive: session expired, please reconnect")
        from google.auth.transport.requests import Request

        try:
            creds.refresh(Request())
        except Exception as exc:
            raise SyncAuthError(
                "Google Drive: token refresh failed, please reconnect"
            ) from exc
        if self._token_store:
            self._token_store.set_secret(TOKEN_KEY, creds.to_json())

    def _retry(self, call, attempts: int = 5):
        for attempt in range(attempts):
            try:
                return call()
            except Exception as exc:
                if not self._is_retryable(exc) or attempt == attempts - 1:
                    raise
                delay = min(2**attempt, 32) + random.uniform(0, 0.5)
                time.sleep(delay)
        raise SyncNetworkError("Drive request failed")

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        status = _status_code(exc)
        if status in (429, 500, 502, 503, 504):
            return True
        if status == 403:
            text = str(exc).lower()
            return "ratelimit" in text or "userratelimit" in text
        return False

    def _map_error(self, exc: Exception) -> SyncProviderError:
        status = _status_code(exc)
        if status in (401,):
            return SyncAuthError(f"Google Drive: not authorized ({exc})")
        if status == 403:
            if self._is_retryable(exc):
                return SyncNetworkError(f"Google Drive: rate limit ({exc})")
            return SyncAuthError(f"Google Drive: access denied ({exc})")
        if status == 404:
            return SyncNotFoundError(f"Google Drive: not found ({exc})")
        if status in (409, 412):
            return SyncConflictError(f"Google Drive: conflict ({exc})")
        if status and status >= 500:
            return SyncNetworkError(f"Google Drive: server error ({exc})")
        return SyncProviderError(f"Google Drive: {exc}")


def _entry_from_file(data: dict, rel: str) -> RemoteEntry:
    mime = data.get("mimeType") or ""
    is_dir = mime == FOLDER_MIME
    digest = data.get("md5Checksum")
    return RemoteEntry(
        rel,
        is_dir,
        size=int(data.get("size") or 0),
        mtime=_parse_time(data.get("modifiedTime")),
        hash=digest,
        hash_kind="md5" if digest else None,
        etag=data.get("etag"),
        remote_id=data.get("id"),
    )


def _parse_time(value) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _parent(rel: str) -> str:
    parts = PurePosixPath(rel).parts
    return "/".join(parts[:-1])


def _status_code(exc: Exception) -> int:
    status = getattr(exc, "status_code", None)
    if status:
        return int(status)
    response = getattr(exc, "resp", None)
    status = getattr(response, "status", None)
    if status:
        return int(status)
    return 0
