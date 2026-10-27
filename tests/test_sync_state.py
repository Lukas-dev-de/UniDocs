"""Sync state roundtrip, key isolation and corruption handling."""

import json

from sync.state import SCHEMA_VERSION, SyncState, state_key
from sync.types import FileState, LocalEntry, RemoteEntry


def test_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    state = SyncState("webdav:u|r", tmp_path / "root", "My Cloud", path=path)
    state.files["Math/a.pdf"] = FileState(
        local_sha256="abc",
        local_size=3,
        local_mtime_ns=123,
        remote_hash="def",
        remote_hash_kind="md5",
        remote_size=3,
        remote_mtime=1.5,
        remote_etag='"e"',
    )
    state.save()

    loaded = SyncState("webdav:u|r", tmp_path / "root", path=path).load()

    entry = loaded.files["Math/a.pdf"]
    assert entry.local_sha256 == "abc"
    assert entry.remote_hash == "def"
    assert entry.remote_etag == '"e"'
    assert loaded.last_sync


def test_key_includes_provider_and_root(tmp_path):
    a = state_key("webdav:a", tmp_path / "root-a")
    b = state_key("webdav:b", tmp_path / "root-a")
    c = state_key("webdav:a", tmp_path / "root-b")

    assert len({a, b, c}) == 3


def test_missing_file_starts_empty(tmp_path):
    state = SyncState("p", tmp_path, path=tmp_path / "missing.json").load()
    assert state.files == {}
    assert state.had_corruption is False


def test_corrupt_file_is_backed_up(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("not json", encoding="utf-8")

    state = SyncState("p", tmp_path, path=path).load()

    assert state.had_corruption is True
    assert state.files == {}
    backups = list(tmp_path.glob("state.corrupt-*.json"))
    assert len(backups) == 1


def test_wrong_schema_is_backed_up(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": 99, "files": {"a": {}}}), encoding="utf-8")

    state = SyncState("p", tmp_path, path=path).load()

    assert state.had_corruption is True
    assert state.files == {}
    assert list(tmp_path.glob("state.schema-*.json"))


def test_record_local_and_drop(tmp_path):
    state = SyncState("p", tmp_path, path=tmp_path / "s.json")
    local = LocalEntry("a.pdf", False, size=3, mtime_ns=10, sha256="sha", md5="md5")
    remote = RemoteEntry("a.pdf", False, size=3, mtime=5.0, hash="md5", hash_kind="md5")

    state.record_local(local, remote)
    assert state.files["a.pdf"].local_sha256 == "sha"
    assert state.files["a.pdf"].remote_hash_kind == "md5"

    state.drop("a.pdf")
    assert state.files == {}


def test_version_constant_stable():
    assert SCHEMA_VERSION == 1
