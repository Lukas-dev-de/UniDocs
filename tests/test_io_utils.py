"""Tests for the atomic JSON writer in ``app_storage.io_utils``."""

import json

import pytest

from app_storage import io_utils
from app_storage.io_utils import TMP_SUFFIX, write_json


def test_writes_readable_json(tmp_path):
    path = tmp_path / "data.json"

    write_json(path, {"a": 1, "b": ["x", "ü"]})

    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "b": ["x", "ü"]}


def test_creates_missing_parent_folders(tmp_path):
    path = tmp_path / "deep" / "deeper" / "data.json"

    write_json(path, {"a": 1})

    assert path.exists()


def test_leaves_no_temporary_file(tmp_path):
    path = tmp_path / "data.json"

    write_json(path, {"a": 1})

    assert not path.with_name(path.name + TMP_SUFFIX).exists()
    assert list(tmp_path.iterdir()) == [path]


def test_replaces_existing_content(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("old and broken", encoding="utf-8")

    write_json(path, {"a": 2})

    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 2}


def test_failed_replace_keeps_the_old_file(tmp_path, monkeypatch):
    path = tmp_path / "data.json"
    path.write_text('{"a": 1}', encoding="utf-8")

    def boom(src, dst):
        raise OSError("disk on fire")

    monkeypatch.setattr(io_utils.os, "replace", boom)

    with pytest.raises(OSError):
        write_json(path, {"a": 2})

    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    assert not path.with_name(path.name + TMP_SUFFIX).exists()


def test_unserialisable_payload_keeps_the_old_file(tmp_path):
    path = tmp_path / "data.json"
    path.write_text('{"a": 1}', encoding="utf-8")

    with pytest.raises(TypeError):
        write_json(path, {"a": object()})

    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    assert not path.with_name(path.name + TMP_SUFFIX).exists()
