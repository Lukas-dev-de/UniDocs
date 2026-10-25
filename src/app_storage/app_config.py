"""
storage/app_config.py
---------------------
Reads and writes the user's ``config.json``.

Location
--------
The file lives in the per-user config folder (``platformdirs``):
``%LOCALAPPDATA%/UniDocs`` on Windows, ``~/Library/Application Support/UniDocs``
on macOS, ``~/.config/UniDocs`` on Linux. A bundled install (Program Files,
``/Applications``, an AppImage) cannot write next to the code, so the old
location was not usable there. A ``config.json`` found next to the code is
copied over once on first start (see ``AppConfig._migrate_legacy``).

config.json example
-------------------
{
  "unidocs_location": "/home/user/Documents/UniDocs",
  "theme_palette": "default",
  "theme_mode": "dark",
  "auto_install_patches": true,
  "seen_update": "2.4.0"
}

Usage
-----
    from app_storage.app_config import AppConfig

    cfg = AppConfig()
    cfg.unidocs_location          # → Path
    cfg.unidocs_location = Path("/new/path")   # saves immediately
    cfg.theme_palette             # → "default"  (see ui.theme.PALETTES)
    cfg.theme_mode                # → "system"  (system | light | dark)
    cfg.auto_install_patches      # → True       (patch updates, see ui.update_prompt)
    cfg.seen_update               # → ""         (update popup already shown for this version)
"""

from __future__ import annotations

import json
from pathlib import Path
from platformdirs import user_config_dir, user_documents_dir

from app_storage.io_utils import write_json

# Per-user config folder; the file has to be writable after a normal install.
# ``appauthor=False`` keeps Windows from nesting a second "UniDocs" folder.
_CONFIG_PATH = Path(user_config_dir("UniDocs", appauthor=False)) / "config.json"

# Where versions up to 2.5.0 kept the file: next to the code. Read once and
# copied to the new location, never written to again.
_LEGACY_CONFIG_PATH = Path(__file__).parent.parent / "config.json"

_DEFAULT_UNIDOCS = Path(user_documents_dir()) / "UniDocs"

class AppConfig:
    def __init__(self, config_path: Path | None = None):
        """Load the config, migrating the old location when in default use.

        Passing *config_path* (tests, tools) skips the migration and touches
        no file outside that path.
        """
        self._path = Path(config_path) if config_path is not None else _CONFIG_PATH
        self._data: dict = {}
        if config_path is None:
            self._migrate_legacy()
        self._load()

    #  public properties 

    @property
    def unidocs_location(self) -> Path:
        raw = self._data.get("unidocs_location")
        if raw:
            return Path(raw)
        return _DEFAULT_UNIDOCS

    @unidocs_location.setter
    def unidocs_location(self, value: Path):
        self._set("unidocs_location", str(value))

    @property
    def theme_palette(self) -> str:
        """Id of the active colour palette (see ``ui.theme.PALETTES``)."""
        return self._data.get("theme_palette") or "default"

    @theme_palette.setter
    def theme_palette(self, value: str):
        self._set("theme_palette", value)

    @property
    def theme_mode(self) -> str:
        """Appearance mode: ``"system" | "light" | "dark"``."""
        return self._data.get("theme_mode") or "system"

    @theme_mode.setter
    def theme_mode(self, value: str):
        self._set("theme_mode", value)

    @property
    def auto_install_patches(self) -> bool:
        """Install patch releases (2.3.0 -> 2.3.1) on startup without asking.

        Only ever acted on where UniDocs can install itself: the Windows
        setup, the Linux install.sh build and the AppImage; see
        ``updater.can_self_update``.
        """
        return bool(self._data.get("auto_install_patches", True))

    @auto_install_patches.setter
    def auto_install_patches(self, value: bool):
        self._set("auto_install_patches", bool(value))

    @property
    def restore_group(self) -> bool:
        """Reopen the app in the group that was on screen when it was closed."""
        return bool(self._data.get("restore_group", False))

    @restore_group.setter
    def restore_group(self, value: bool):
        self._set("restore_group", bool(value))

    @property
    def restore_module(self) -> bool:
        """Also reopen the last module on startup (needs ``restore_group``)."""
        return bool(self._data.get("restore_module", False))

    @restore_module.setter
    def restore_module(self, value: bool):
        self._set("restore_module", bool(value))

    @property
    def last_group(self) -> str:
        """Folder name of the group last shown ("" = Home)."""
        return self._data.get("last_group") or ""

    @last_group.setter
    def last_group(self, value: str):
        self._set("last_group", value or "")

    @property
    def last_module(self) -> str:
        """Title of the last opened module ("" = none)."""
        return self._data.get("last_module") or ""

    @last_module.setter
    def last_module(self, value: str):
        self._set("last_module", value or "")

    @property
    def seen_update(self) -> str:
        """Newest release version the user was already told about.

        The startup check shows at most one popup per version, so a dismissed
        update never pops up again on every launch.
        """
        return self._data.get("seen_update") or ""

    @seen_update.setter
    def seen_update(self, value: str):
        self._set("seen_update", value or "")

    #  persistence 

    def _load(self):
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._data = {}
        if not isinstance(self._data, dict):
            self._data = {}

    def _migrate_legacy(self) -> None:
        """Copy a ``config.json`` next to the code to the per-user folder.

        Runs once: if the new file exists already nothing happens. The old
        file is left untouched (it may sit in a read-only install folder
        anyway) and only ever read.
        """
        if self._path.exists() or not _LEGACY_CONFIG_PATH.exists():
            return
        try:
            data = json.loads(_LEGACY_CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        try:
            write_json(self._path, data)
        except OSError:
            pass  # config folder not writable -> start with defaults

    def _set(self, key: str, value):
        """Write one key and save.

        The file is re-read first because more than one AppConfig instance
        points at it (main.py, the settings dialog). Without the reload, an
        instance that has been around for a while would write its stale copy
        back and drop whatever the other one stored in the meantime.
        """
        self._load()
        self._data[key] = value
        self._save()

    def _save(self):
        write_json(self._path, self._data)
