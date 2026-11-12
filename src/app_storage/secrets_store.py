"""Credential storage for cloud sync.

Passwords and OAuth tokens go to the operating system keyring when one is
available. On headless Linux boxes (no D-Bus / Secret Service) the module falls
back to a private JSON file in the per-user config folder. That file is not
encrypted, but it is only readable by the current user (mode 0600).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from platformdirs import user_config_dir

logger = logging.getLogger(__name__)

SERVICE = "UniDocs"


class SecretsStore:
    """Small key/value store backed by keyring or a 0600 JSON file."""

    def __init__(
        self,
        fallback_path: Path | None = None,
        keyring_module=None,
    ):
        self._fallback_path = (
            Path(fallback_path)
            if fallback_path is not None
            else Path(user_config_dir("UniDocs", appauthor=False)) / "secrets.json"
        )
        self._keyring = keyring_module
        self._file_data: dict[str, str] | None = None
        self._keyring_broken = False
        self._lock = threading.RLock()

    # -- public API -----------------------------------------------------------

    def get_secret(self, name: str) -> str | None:
        with self._lock:
            value = self._keyring_get(name)
            if value is not None:
                return value
            return self._load_file().get(name)

    def set_secret(self, name: str, value: str) -> None:
        with self._lock:
            if self._keyring_set(name, value):
                # Never leave a stale copy in the weaker store.
                self._file_delete(name)
                return
            data = self._load_file(force=True)
            data[name] = value
            self._save_file(data)

    def delete_secret(self, name: str) -> None:
        with self._lock:
            self._keyring_delete(name)
            self._file_delete(name)

    def backend_name(self) -> str:
        """``"keyring"`` or ``"file"`` — for the settings status line."""
        return "keyring" if self._keyring_available() and not self._keyring_broken else "file"

    # -- keyring --------------------------------------------------------------

    def _keyring_available(self) -> bool:
        if self._keyring is None:
            try:
                import keyring

                self._keyring = keyring
            except ImportError:
                return False
        try:
            backend = self._keyring.get_keyring()
        except Exception:
            return False
        # keyring's fail backend accepts nothing; treat it as "not available".
        module = type(backend).__module__.lower()
        return "fail" not in module

    def _keyring_get(self, name: str) -> str | None:
        if self._keyring_broken or not self._keyring_available():
            return None
        try:
            return self._keyring.get_password(SERVICE, name)
        except Exception as exc:
            logger.warning("keyring read failed, using file fallback: %s", exc)
            self._keyring_broken = True
            return None

    def _keyring_set(self, name: str, value: str) -> bool:
        if self._keyring_broken or not self._keyring_available():
            return False
        try:
            self._keyring.set_password(SERVICE, name, value)
            return True
        except Exception as exc:
            logger.warning("keyring write failed, using file fallback: %s", exc)
            self._keyring_broken = True
            return False

    def _keyring_delete(self, name: str) -> None:
        if self._keyring_broken or not self._keyring_available():
            return
        try:
            self._keyring.delete_password(SERVICE, name)
        except Exception:
            pass

    # -- file fallback --------------------------------------------------------

    def _load_file(self, force: bool = False) -> dict[str, str]:
        if self._file_data is not None and not force:
            return self._file_data
        try:
            raw = json.loads(self._fallback_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        self._file_data = raw if isinstance(raw, dict) else {}
        return self._file_data

    def _save_file(self, data: dict[str, str]) -> None:
        self._fallback_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._fallback_path.with_name(self._fallback_path.name + ".tmp")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._fallback_path)
            try:
                os.chmod(self._fallback_path, 0o600)
            except OSError:
                pass  # Windows: ACLs inherit from the user profile
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
        self._file_data = data

    def _file_delete(self, name: str) -> None:
        data = self._load_file()
        if name in data:
            del data[name]
            self._save_file(data)
