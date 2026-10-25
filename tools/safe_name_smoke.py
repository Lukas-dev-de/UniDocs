"""

Folder-name safety smoke test.

Covers ``_safe_name`` in ``src/app_storage/module_store.py``: titles must map
to a folder name that no OS rejects and that can never point outside the
UniDocs root.

Run:  python tools/safe_name_smoke.py
"""

import sys
import tempfile
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import flet as ft  # noqa: E402
from app_storage.module_store import (  # noqa: E402
    MAX_NAME_LENGTH,
    ModuleStore,
    _safe_name,
)
from models.module import Module  # noqa: E402

failures: list[str] = []


def check(label: str, actual, expected) -> None:
    if actual == expected:
        print(f"  ok   {label}")
    else:
        failures.append(label)
        print(f"  FAIL {label}: got {actual!r}, expected {expected!r}")


# -- plain titles ------------------------------------------------------------

print("plain titles are kept:")
check("simple", _safe_name("Math"), "Math")
check("spaces inside", _safe_name("Physics 101"), "Physics 101")
check("unicode", _safe_name("Übung 1"), "Übung 1")
check("dot inside", _safe_name("2. Semester"), "2. Semester")

# -- stripped characters -----------------------------------------------------

print("forbidden characters are stripped:")
check("colon", _safe_name("Uni:versity"), "University")
check("slash", _safe_name("Physics/"), "Physics")
check("backslash", _safe_name("a\\b"), "ab")
check("all of them", _safe_name('a/b\\c:d*e?f"g<h>i|j'), "abcdefghij")
check("control chars", _safe_name("a\x00b\x1fc\x7fd"), "abcd")
check("tab and newline", _safe_name("a\tb\nc"), "abc")

# -- edges around dots and spaces -------------------------------------------

print("dots and spaces at the edges are trimmed:")
check("trailing dot", _safe_name("Physics."), "Physics")
check("trailing space", _safe_name("Physics   "), "Physics")
check("leading space", _safe_name("   Physics"), "Physics")
check("dot and space", _safe_name("Physics. ."), "Physics")

print("dot-only names are refused:")
check("dot", _safe_name("."), "Untitled")
check("dot dot", _safe_name(".."), "Untitled")
check("three dots", _safe_name("..."), "Untitled")

print("empty results fall back:")
check("empty", _safe_name(""), "Untitled")
check("spaces only", _safe_name("   "), "Untitled")
check("illegal only", _safe_name("///"), "Untitled")

# -- Windows device names ----------------------------------------------------

print("reserved device names get a suffix:")
check("CON", _safe_name("CON"), "CON_")
check("lowercase", _safe_name("con"), "con_")
check("with extension", _safe_name("CON.txt"), "CON.txt_")
check("NUL", _safe_name("NUL"), "NUL_")
check("AUX", _safe_name("AUX"), "AUX_")
check("PRN", _safe_name("PRN"), "PRN_")
check("COM1", _safe_name("COM1"), "COM1_")
check("LPT9", _safe_name("LPT9"), "LPT9_")
check("COM10 is fine", _safe_name("COM10"), "COM10")
check("CONSOLE is fine", _safe_name("CONSOLE"), "CONSOLE")

# -- length ------------------------------------------------------------------

print("long names are cut:")
long_name = "x" * (MAX_NAME_LENGTH + 200)
check("length", len(_safe_name(long_name)), MAX_NAME_LENGTH)
check(
    "cut keeps no trailing dot",
    _safe_name("y" * (MAX_NAME_LENGTH - 1) + "." * 5)[-1] != ".",
    True,
)

# -- the store stays inside its root ----------------------------------------

print("store never leaves the root:")


def fresh_store() -> ModuleStore:
    root = Path(tempfile.mkdtemp()) / "UniDocs"
    root.mkdir()
    return ModuleStore(root=root)


def test_dotdot_module() -> None:
    """A module titled ".." must not write into the root's parent."""
    store = fresh_store()
    parent = store.root.parent
    store.save_module(Module(title="..", description="evil"))
    assert (store.root / "Untitled" / ".meta").exists(), "lands in root/Untitled"
    assert not (parent / ".meta").exists(), "nothing written outside the root"
    store.delete_module(Module(title=".."))
    assert parent.exists(), "parent folder survives the delete"
    assert store.root.exists(), "root folder survives the delete"
    print("  ok   '..' module stays inside the root")


def test_dotdot_group() -> None:
    """A group named ".." must not take over the root's parent either."""
    store = fresh_store()
    parent = store.root.parent
    name = store.create_group("..")
    assert name == "Untitled", name
    assert (store.root / "Untitled" / ".group").exists(), "group inside the root"
    assert not (parent / ".group").exists(), "nothing written outside the root"
    print("  ok   '..' group stays inside the root")


def test_reserved_module() -> None:
    store = fresh_store()
    store.save_module(Module(title="CON", description="x", icon=ft.Icons.FOLDER))
    assert (store.root / "CON_" / ".meta").exists(), "reserved name got a suffix"
    print("  ok   reserved module name got a suffix")


test_dotdot_module()
test_dotdot_group()
test_reserved_module()

print()
if failures:
    print(f"FAILED: {len(failures)} check(s): {failures}")
    raise SystemExit(1)
print("SAFE NAME OK")
