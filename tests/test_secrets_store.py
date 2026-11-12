"""Tests for the keyring / 0600-file credential store."""

import os
import stat

import pytest

from app_storage.secrets_store import SecretsStore


class FakeKeyring:
    def __init__(self, fail: bool = False):
        self.data: dict[tuple[str, str], str] = {}
        self.fail = fail

    def get_keyring(self):
        class Backend:
            pass

        return Backend()

    def get_password(self, service, name):
        if self.fail:
            raise RuntimeError("no dbus")
        return self.data.get((service, name))

    def set_password(self, service, name, value):
        if self.fail:
            raise RuntimeError("no dbus")
        self.data[(service, name)] = value

    def delete_password(self, service, name):
        if self.fail:
            raise RuntimeError("no dbus")
        self.data.pop((service, name), None)


@pytest.fixture
def store(tmp_path):
    return SecretsStore(fallback_path=tmp_path / "secrets.json", keyring_module=FakeKeyring())


def test_roundtrip_via_keyring(store, tmp_path):
    store.set_secret("webdav_password", "secret")

    assert store.get_secret("webdav_password") == "secret"
    assert store.backend_name() == "keyring"
    assert not (tmp_path / "secrets.json").exists()


def test_falls_back_to_private_file_when_keyring_fails(tmp_path):
    store = SecretsStore(
        fallback_path=tmp_path / "secrets.json",
        keyring_module=FakeKeyring(fail=True),
    )

    store.set_secret("gdrive_token", '{"refresh_token": "x"}')

    assert store.backend_name() == "file"
    assert store.get_secret("gdrive_token") == '{"refresh_token": "x"}'
    path = tmp_path / "secrets.json"
    assert path.exists()
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600


def test_delete_removes_both_backends(store, tmp_path):
    store.set_secret("k", "v")
    store.set_secret("k2", "v2")
    store.delete_secret("k")

    assert store.get_secret("k") is None
    assert store.get_secret("k2") == "v2"


def test_missing_key_returns_none(store):
    assert store.get_secret("nope") is None


def test_corrupt_fallback_file_starts_empty(tmp_path):
    path = tmp_path / "secrets.json"
    path.write_text("not json", encoding="utf-8")
    store = SecretsStore(fallback_path=path, keyring_module=FakeKeyring(fail=True))

    assert store.get_secret("k") is None

    store.set_secret("k", "v")
    assert store.get_secret("k") == "v"
