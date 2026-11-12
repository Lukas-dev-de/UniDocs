"""Tests for the config location and the one-time migration."""

import json

import pytest

from app_storage import app_config
from app_storage.app_config import AppConfig


@pytest.fixture
def paths(tmp_path, monkeypatch):
    """Point both the new and the old config path at the test tmp folder."""
    new = tmp_path / "config" / "config.json"
    legacy = tmp_path / "code" / "config.json"
    legacy.parent.mkdir()
    monkeypatch.setattr(app_config, "_CONFIG_PATH", new)
    monkeypatch.setattr(app_config, "_LEGACY_CONFIG_PATH", legacy)
    return new, legacy


def test_defaults_without_any_file(paths):
    cfg = AppConfig()

    assert cfg.theme_mode == "system"
    assert cfg.seen_update == ""
    assert cfg.sync_provider == "off"
    assert cfg.webdav_root == "UniDocs"
    assert cfg.trash_retention_days == 30
    assert cfg.trash_auto_empty_enabled is False


def test_sync_settings_persist_and_clamp(paths):
    cfg = AppConfig()
    cfg.sync_provider = "webdav"
    cfg.webdav_url = " https://cloud.example.com/dav "
    cfg.webdav_username = " user "
    cfg.webdav_root = "/UniDocs/"
    cfg.trash_retention_days = 0
    device_a = cfg.device_id

    reloaded = AppConfig()

    assert reloaded.sync_provider == "webdav"
    assert reloaded.webdav_url == "https://cloud.example.com/dav"
    assert reloaded.webdav_username == "user"
    assert reloaded.webdav_root == "UniDocs"
    assert reloaded.trash_retention_days == 1
    assert reloaded.device_id == device_a


def test_unidocs_settings_persist(paths):
    cfg = AppConfig()
    cfg.sync_provider = "unidocs"
    cfg.unidocs_url = " https://unidocs.example.com/ "

    reloaded = AppConfig()

    assert reloaded.sync_provider == "unidocs"
    assert reloaded.unidocs_url == "https://unidocs.example.com"


def test_unidocs_data_dir_env_overrides_location(paths, monkeypatch, tmp_path):
    cfg = AppConfig()
    monkeypatch.setenv("UNIDOCS_DATA_DIR", str(tmp_path / "data"))

    assert cfg.unidocs_location == (tmp_path / "data").resolve()


def test_reload_picks_up_external_change(paths):
    first = AppConfig()
    second = AppConfig()
    second.sync_on_start = True

    first.reload()

    assert first.sync_on_start is True


def test_migrates_legacy_file_once(paths):
    new, legacy = paths
    legacy.write_text(
        json.dumps({"theme_mode": "dark", "seen_update": "2.5.0"}), encoding="utf-8"
    )

    cfg = AppConfig()

    assert cfg.theme_mode == "dark"
    assert cfg.seen_update == "2.5.0"
    assert json.loads(new.read_text(encoding="utf-8"))["theme_mode"] == "dark"
    assert legacy.exists(), "the old file is left alone"


def test_does_not_overwrite_an_existing_config(paths):
    new, legacy = paths
    new.parent.mkdir()
    new.write_text(json.dumps({"theme_mode": "light"}), encoding="utf-8")
    legacy.write_text(json.dumps({"theme_mode": "dark"}), encoding="utf-8")

    cfg = AppConfig()

    assert cfg.theme_mode == "light"


def test_ignores_a_broken_legacy_file(paths):
    new, legacy = paths
    legacy.write_text("{ not json", encoding="utf-8")

    cfg = AppConfig()

    assert cfg.theme_mode == "system"
    assert not new.exists()


def test_ignores_a_non_dict_legacy_file(paths):
    new, legacy = paths
    legacy.write_text('["nope"]', encoding="utf-8")

    cfg = AppConfig()

    assert cfg.theme_mode == "system"
    assert not new.exists()


def test_ignores_a_non_dict_config(paths):
    new, _legacy = paths
    new.parent.mkdir()
    new.write_text('["nope"]', encoding="utf-8")

    cfg = AppConfig()

    assert cfg.theme_mode == "system"


def test_explicit_path_skips_migration(paths, tmp_path):
    _new, legacy = paths
    legacy.write_text(json.dumps({"theme_mode": "dark"}), encoding="utf-8")
    own = tmp_path / "own" / "config.json"

    cfg = AppConfig(config_path=own)
    cfg.theme_mode = "light"

    assert json.loads(own.read_text(encoding="utf-8")) == {"theme_mode": "light"}
    assert not (tmp_path / "config" / "config.json").exists()


def test_setters_persist_to_disk(paths):
    new, _legacy = paths
    cfg = AppConfig()

    cfg.theme_mode = "dark"

    assert json.loads(new.read_text(encoding="utf-8")) == {"theme_mode": "dark"}
