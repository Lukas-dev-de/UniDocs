"""Sync service: factory errors, off switch, auto-purge, worker wiring."""

import asyncio
import inspect
import json
from datetime import datetime, timedelta, timezone

import pytest

from app_storage.app_config import AppConfig
from app_storage.trash_store import TrashStore
from sync.service import SyncService, webdav_password_key
from sync.state import SyncState
from sync.types import FileState
from fake_provider import FakeProvider


class FakePage:
    def __init__(self):
        self.threads = 0
        self.tasks = 0

    def run_thread(self, fn):
        self.threads += 1
        fn()

    def run_task(self, fn, *args):
        self.tasks += 1
        result = fn(*args)
        if inspect.isawaitable(result):
            asyncio.run(result)


class FakeSecrets:
    def __init__(self, data=None):
        self.data = data or {}

    def get_secret(self, name):
        return self.data.get(name)


@pytest.fixture
def cfg(tmp_path):
    return AppConfig(config_path=tmp_path / "config.json")


def test_start_returns_false_when_provider_is_off(cfg):
    service = SyncService(FakePage(), cfg, secrets=FakeSecrets())
    assert service.start() is False


def test_start_runs_worker_with_injected_provider(tmp_path, cfg):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "a.pdf").write_bytes(b"x")
    cfg.unidocs_location = root
    cfg.sync_provider = "webdav"
    provider = FakeProvider()
    service = SyncService(
        FakePage(),
        cfg,
        secrets=FakeSecrets(),
        provider_factory=lambda cfg, secrets, interactive: (provider, "fake"),
        state_path=tmp_path / "state.json",
    )

    assert service.start() is True
    assert "a.pdf" in provider.files


def test_webdav_without_password_aborts(cfg):
    cfg.sync_provider = "webdav"
    cfg.webdav_url = "https://cloud.example.com/dav"
    cfg.webdav_username = "user"
    reports = []
    service = SyncService(FakePage(), cfg, secrets=FakeSecrets())
    service.on_done = reports.append

    service.start()

    assert reports and reports[0].aborted
    assert "password" in reports[0].message.lower()


def test_webdav_password_key_is_stable_and_user_specific():
    a = webdav_password_key("https://x/dav", "alice")
    b = webdav_password_key("https://x/dav", "alice")
    c = webdav_password_key("https://x/dav", "bob")

    assert a == b
    assert a != c
    assert a.startswith("webdav_password:")


def test_auto_purge_only_removes_state_confirmed_entries(tmp_path, cfg):
    root = tmp_path / "docs"
    root.mkdir()
    cfg.unidocs_location = root
    cfg.trash_auto_empty_enabled = True
    cfg.trash_retention_days = 1
    trash = TrashStore(root, device_name="Laptop")
    (root / "old.pdf").write_bytes(b"old")
    (root / "fresh.pdf").write_bytes(b"fresh")
    old = trash.move_to_trash(root / "old.pdf", "document")
    fresh = trash.move_to_trash(root / "fresh.pdf", "document")
    meta_path = old.entry_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["deleted_at"] = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    state = SyncState("fake", root)
    state.files[f".trash/{old.id}/meta.json"] = FileState(kind="file")
    state.files[f".trash/{fresh.id}/meta.json"] = FileState(kind="file")

    service = SyncService(FakePage(), cfg, secrets=FakeSecrets())
    removed = service._purge_trash(state)

    assert removed == 1
    remaining = [entry.id for entry in trash.list_entries()]
    assert remaining == [fresh.id]
