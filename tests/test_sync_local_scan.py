"""Local scan: ignore rules, hashing and hash reuse."""

import hashlib
import os

import pytest

from sync.local_scan import LocalScanError, scan_local
from sync.types import FileState


def test_scan_files_and_dirs(tmp_path):
    (tmp_path / "Math").mkdir()
    (tmp_path / "Math" / "lecture.pdf").write_bytes(b"hello")
    (tmp_path / "Math" / ".meta").write_text("{}", encoding="utf-8")
    (tmp_path / "empty").mkdir()

    entries = scan_local(tmp_path)

    assert entries["Math"].is_dir
    assert entries["empty"].is_dir
    assert entries["Math/.meta"].is_dir is False
    assert entries["Math/lecture.pdf"].size == 5
    assert entries["Math/lecture.pdf"].sha256 == hashlib.sha256(b"hello").hexdigest()


def test_scan_ignores_temp_and_os_junk(tmp_path):
    (tmp_path / "good.pdf").write_bytes(b"x")
    (tmp_path / "partial.tmp").write_bytes(b"x")
    (tmp_path / ".DS_Store").write_bytes(b"x")
    (tmp_path / "~$lock.docx").write_bytes(b"x")
    (tmp_path / ".unidocs-tmp").mkdir()
    (tmp_path / ".unidocs-tmp" / "download").write_bytes(b"x")

    entries = scan_local(tmp_path)

    assert list(entries) == ["good.pdf"]


def test_scan_includes_trash_but_not_internal_temp(tmp_path):
    trash = tmp_path / ".trash" / "entry" / "files"
    trash.mkdir(parents=True)
    (trash / "doc.pdf").write_bytes(b"x")

    entries = scan_local(tmp_path)

    assert ".trash/entry/files/doc.pdf" in entries
    assert ".trash/entry" in entries


def test_hash_reused_when_size_and_mtime_match(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(b"abc")
    first = scan_local(tmp_path)
    previous = {
        "a.pdf": FileState(
            local_sha256=first["a.pdf"].sha256,
            local_size=first["a.pdf"].size,
            local_mtime_ns=first["a.pdf"].mtime_ns,
        )
    }

    # Same size and mtime, corrupt content: reuse proves no re-read.
    path.write_bytes(b"xyz")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, first["a.pdf"].mtime_ns))

    second = scan_local(tmp_path, previous=previous)

    assert second["a.pdf"].sha256 == first["a.pdf"].sha256


def test_rehashes_when_mtime_changes(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(b"abc")
    first = scan_local(tmp_path)
    previous = {
        "a.pdf": FileState(
            local_sha256=first["a.pdf"].sha256,
            local_size=first["a.pdf"].size,
            local_mtime_ns=first["a.pdf"].mtime_ns,
        )
    }

    path.write_bytes(b"abcd")
    second = scan_local(tmp_path, previous=previous)

    assert second["a.pdf"].sha256 != first["a.pdf"].sha256


def test_skips_symlinks(tmp_path):
    (tmp_path / "real").write_bytes(b"x")
    try:
        (tmp_path / "link").symlink_to(tmp_path / "real")
    except OSError:
        pytest.skip("symlinks not supported")

    entries = scan_local(tmp_path)

    assert "link" not in entries
    assert "real" in entries


def test_missing_root_raises(tmp_path):
    with pytest.raises(LocalScanError):
        scan_local(tmp_path / "missing")


def test_md5_only_when_requested(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"abc")

    plain = scan_local(tmp_path)
    hashed = scan_local(tmp_path, want_md5=True)

    assert plain["a.pdf"].md5 is None
    assert hashed["a.pdf"].md5 == hashlib.md5(b"abc").hexdigest()
