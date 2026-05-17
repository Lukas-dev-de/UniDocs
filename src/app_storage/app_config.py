"""
storage/app_config.py
---------------------
Reads and writes a config.json file next to main.py.

config.json example
-------------------
{
  "unidocs_location": "/home/user/Documents/UniDocs"
}

Usage
-----
    from storage.app_config import AppConfig

    cfg = AppConfig()
    cfg.unidocs_location          # → Path
    cfg.unidocs_location = Path("/new/path")   # saves immediately
"""

from __future__ import annotations

import json
from pathlib import Path

# Always sits next to main.py, regardless of where the script is run from
_CONFIG_PATH = Path(__file__).parent.parent / "config.json"
_DEFAULT_UNIDOCS = Path(__file__).parent.parent / "UniDocs"


class AppConfig:
    def __init__(self, config_path: Path = _CONFIG_PATH):
        self._path = config_path
        self._data: dict = {}
        self._load()

    # ── public properties ──────────────────────────────────────────────────

    @property
    def unidocs_location(self) -> Path:
        raw = self._data.get("unidocs_location")
        if raw:
            return Path(raw)
        return _DEFAULT_UNIDOCS

    @unidocs_location.setter
    def unidocs_location(self, value: Path):
        self._data["unidocs_location"] = str(value)
        self._save()

    # ── persistence ────────────────────────────────────────────────────────

    def _load(self):
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            self._data = {}

    def _save(self):
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
