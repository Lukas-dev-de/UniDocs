"""Flet-facing sync service: provider factory, threads, progress, purge."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from pathlib import Path

from app_storage.app_config import AppConfig
from app_storage.secrets_store import SecretsStore
from app_storage.trash_store import TrashStore
from sync.base import BaseSyncProvider, SyncAuthError, SyncProviderError
from sync.engine import SyncEngine
from sync.gdrive import GDriveProvider, load_credentials, resolve_client_secret
from sync.state import SyncState
from sync.types import SyncReport
from sync.unidocs import UniDocsProvider
from sync.webdav import WebDAVProvider

logger = logging.getLogger(__name__)


def webdav_password_key(url: str, username: str) -> str:
    raw = f"{url.strip()}\n{username.strip()}".encode("utf-8")
    return "webdav_password:" + hashlib.sha256(raw).hexdigest()[:16]


def unidocs_token_key(url: str) -> str:
    raw = f"unidocs\n{url.strip()}".encode("utf-8")
    return "unidocs_token:" + hashlib.sha256(raw).hexdigest()[:16]


def provider_identity(cfg: AppConfig, gdrive_folder_id: str = "") -> str:
    if cfg.sync_provider == "webdav":
        return f"webdav:{cfg.webdav_url}|{cfg.webdav_username}|{cfg.webdav_root}"
    if cfg.sync_provider == "gdrive":
        return f"gdrive:{gdrive_folder_id or cfg.gdrive_folder_id or 'auto'}"
    if cfg.sync_provider == "unidocs":
        return f"unidocs:{cfg.unidocs_url}"
    return "off"


def provider_label(cfg: AppConfig) -> str:
    if cfg.sync_provider == "webdav":
        return f"WebDAV {cfg.webdav_url} ({cfg.webdav_username})"
    if cfg.sync_provider == "gdrive":
        return "Google Drive"
    if cfg.sync_provider == "unidocs":
        return f"UniDocs server {cfg.unidocs_url}"
    return "Sync aus"


class SyncService:
    def __init__(
        self,
        page,
        cfg: AppConfig | None = None,
        store=None,
        secrets: SecretsStore | None = None,
        provider_factory=None,
        state_path: Path | None = None,
    ):
        self.page = page
        self.cfg = cfg or AppConfig()
        self.store = store
        self.secrets = secrets or SecretsStore()
        self._provider_factory = provider_factory
        self._state_path = state_path
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._provider: BaseSyncProvider | None = None
        self._last_progress = 0.0
        self.on_progress = None
        self.on_done = None
        self.on_error = None

    # -- public API -------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._lock.locked()

    def start(self, interactive: bool = False) -> bool:
        """Kick off a sync in a worker thread. Returns False if one is running."""
        if self.page is None:
            return False
        if not self._lock.acquire(blocking=False):
            return False
        self.cfg.reload()
        if self.cfg.sync_provider == "off":
            self._lock.release()
            return False
        self._cancel = threading.Event()
        try:
            self.page.run_thread(lambda: self._worker(interactive))
        except Exception as exc:
            self._lock.release()
            logger.warning("could not start sync thread: %s", exc)
            return False
        return True

    def cancel(self) -> None:
        self._cancel.set()

    def shutdown(self) -> None:
        self.cancel()

    # -- worker -----------------------------------------------------------

    def _worker(self, interactive: bool) -> None:
        report = SyncReport()
        provider = None
        try:
            report = self._run_sync(interactive)
        except SyncAuthError as exc:
            report.aborted = True
            report.message = str(exc)
        except SyncProviderError as exc:
            report.aborted = True
            report.message = str(exc)
        except Exception as exc:
            logger.exception("unexpected sync failure")
            report.aborted = True
            report.message = f"Sync failed: {exc}"
        finally:
            provider = self._provider
            if provider is not None:
                try:
                    provider.close()
                except Exception:
                    pass
            self._provider = None
            self._lock.release()
            self._post_done(report)

    def _run_sync(self, interactive: bool) -> SyncReport:
        provider, identity = self._build_provider(interactive)
        self._provider = provider
        self.cfg.reload()
        root = Path(self.cfg.unidocs_location)
        state = SyncState(
            identity,
            root,
            provider_label=provider_label(self.cfg),
            path=self._state_path,
        ).load()
        engine = SyncEngine(
            provider,
            root,
            state,
            device_name=self.cfg.device_name,
            progress=self._progress,
            cancel_event=self._cancel,
        )
        suspended = False
        if self.store is not None:
            self.store.suspend_watching()
            suspended = True
        try:
            report = engine.run()
        finally:
            if suspended:
                self.store.resume_watching()
        if (
            isinstance(provider, GDriveProvider)
            and provider.folder_id
            and provider.folder_id != self.cfg.gdrive_folder_id
        ):
            self.cfg.gdrive_folder_id = provider.folder_id
        if not report.aborted and not report.cancelled:
            self._purge_trash(state)
        return report

    def _build_provider(self, interactive: bool):
        if self._provider_factory is not None:
            result = self._provider_factory(self.cfg, self.secrets, interactive)
            if isinstance(result, tuple):
                return result
            return result, provider_identity(self.cfg)

        provider_name = self.cfg.sync_provider
        if provider_name == "webdav":
            url = self.cfg.webdav_url
            username = self.cfg.webdav_username
            if not url:
                raise SyncAuthError("WebDAV URL is missing")
            password = self.secrets.get_secret(webdav_password_key(url, username))
            if not password:
                raise SyncAuthError("WebDAV password is missing")
            provider = WebDAVProvider(
                url,
                username,
                password,
                remote_root=self.cfg.webdav_root,
            )
            return provider, provider_identity(self.cfg)

        if provider_name == "unidocs":
            url = self.cfg.unidocs_url
            if not url:
                raise SyncAuthError("UniDocs server URL is missing")
            token = self.secrets.get_secret(unidocs_token_key(url))
            if not token:
                raise SyncAuthError("UniDocs server token is missing")
            provider = UniDocsProvider(url, token)
            return provider, provider_identity(self.cfg)

        if provider_name == "gdrive":
            client_secret = resolve_client_secret(self.cfg.gdrive_client_secret_path)
            creds = load_credentials(
                client_secret,
                self.secrets,
                interactive=interactive,
            )
            provider = GDriveProvider(
                credentials=creds,
                folder_id=self.cfg.gdrive_folder_id,
                token_store=self.secrets,
                interactive=interactive,
                client_secret_path=client_secret,
            )
            # The folder id identifies the state file. Create/find the root now
            # so the id is stable before the first state file is written.
            if not self.cfg.gdrive_folder_id:
                provider.ensure_root()
                if provider.folder_id:
                    self.cfg.gdrive_folder_id = provider.folder_id
            return provider, provider_identity(self.cfg, provider.folder_id)

        raise SyncAuthError("No sync provider selected")

    # -- trash retention --------------------------------------------------

    def _purge_trash(self, state: SyncState) -> int:
        if not self.cfg.trash_auto_empty_enabled:
            return 0
        eligible: set[str] = set()
        for rel in state.files:
            if rel.startswith(".trash/"):
                parts = rel.split("/")
                if len(parts) >= 2:
                    eligible.add(parts[1])
        if not eligible:
            return 0
        trash = TrashStore(
            Path(self.cfg.unidocs_location),
            device_id=self.cfg.device_id,
            device_name=self.cfg.device_name,
        )
        try:
            removed = trash.purge_older_than(
                self.cfg.trash_retention_days, eligible_ids=eligible
            )
            if removed:
                logger.info("trash auto-purge removed %s entries", removed)
            return removed
        except Exception as exc:
            logger.warning("trash auto-purge failed: %s", exc)
            return 0

    # -- Flet callbacks ---------------------------------------------------

    def _progress(self, phase: str, done: int, total: int, rel: str) -> None:
        now = time.monotonic()
        if now - self._last_progress < 0.1 and done < total:
            return
        self._last_progress = now
        if self.page is None:
            return
        try:
            self.page.run_task(self._emit_progress, phase, done, total, rel)
        except Exception:
            pass

    async def _emit_progress(self, phase, done, total, rel):
        callback = self.on_progress
        if callback is None:
            return
        try:
            result = callback(phase, done, total, rel)
            if hasattr(result, "__await__"):
                await result
        except Exception:
            logger.debug("progress callback failed", exc_info=True)

    def _post_done(self, report: SyncReport) -> None:
        if self.page is None:
            return
        try:
            self.page.run_task(self._emit_done, report)
        except Exception:
            pass

    async def _emit_done(self, report: SyncReport):
        callback = self.on_done
        if callback is None:
            return
        try:
            result = callback(report)
            if hasattr(result, "__await__"):
                await result
        except Exception:
            logger.debug("done callback failed", exc_info=True)
