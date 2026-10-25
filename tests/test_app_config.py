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
