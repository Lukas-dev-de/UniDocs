"""Tests for ``_safe_name``: every title must map to a safe folder name."""

import pytest

from app_storage.module_store import MAX_NAME_LENGTH, ModuleStore, _safe_name
from models.module import Module


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Math", "Math"),
        ("Physics 101", "Physics 101"),
        ("Übung 1", "Übung 1"),
        ("2. Semester", "2. Semester"),
        ("Uni:versity", "University"),
        ("Physics/", "Physics"),
        ("a\\b", "ab"),
        ('a/b\\c:d*e?f"g<h>i|j', "abcdefghij"),
        ("a\x00b\x1fc\x7fd", "abcd"),
        ("a\tb\nc", "abc"),
        ("Physics.", "Physics"),
        ("Physics   ", "Physics"),
        ("   Physics", "Physics"),
        ("Physics. .", "Physics"),
    ],
)
def test_strips_forbidden_characters(title, expected):
    assert _safe_name(title) == expected


@pytest.mark.parametrize("title", [".", "..", "...", "", "   ", "///"])
def test_refuses_parent_and_empty_names(title):
    assert _safe_name(title) == "Untitled"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("CON", "CON_"),
        ("con", "con_"),
        ("CON.txt", "CON.txt_"),
        ("NUL", "NUL_"),
        ("AUX", "AUX_"),
        ("PRN", "PRN_"),
        ("COM1", "COM1_"),
        ("LPT9", "LPT9_"),
        ("COM10", "COM10"),
        ("CONSOLE", "CONSOLE"),
    ],
)
def test_suffixes_windows_device_names(title, expected):
    assert _safe_name(title) == expected


def test_cuts_very_long_names():
    assert len(_safe_name("x" * (MAX_NAME_LENGTH + 200))) == MAX_NAME_LENGTH


def test_cut_name_keeps_no_trailing_dot():
    cut = _safe_name("y" * (MAX_NAME_LENGTH - 1) + "." * 5)

    assert not cut.endswith((".", " "))


def test_dotdot_module_stays_inside_the_root(tmp_path):
    root = tmp_path / "UniDocs"
    root.mkdir()
    store = ModuleStore(root=root)

    store.save_module(Module(title="..", description="evil"))

    assert (root / "Untitled" / ".meta").exists()
    assert not (tmp_path / ".meta").exists()
    store.delete_module(Module(title=".."))
    assert root.exists()
    assert tmp_path.exists()


def test_dotdot_group_stays_inside_the_root(tmp_path):
    root = tmp_path / "UniDocs"
    root.mkdir()
    store = ModuleStore(root=root)

    name = store.create_group("..")

    assert name == "Untitled"
    assert (root / "Untitled" / ".group").exists()
    assert not (tmp_path / ".group").exists()
