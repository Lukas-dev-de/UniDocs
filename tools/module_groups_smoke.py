"""
tools/module_groups_smoke.py
----------------------------
Headless check of the sidebar's group support.

Two halves: the store that keeps modules in group folders, and the sidebar
that filters the module list by the active group and offers "New group…".

    .venv/bin/python tools/module_groups_smoke.py
"""

import sys
import tempfile
from pathlib import Path

import flet as ft

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from app_storage.module_store import ModuleStore  # noqa: E402
from models.module import Module  # noqa: E402
from ui.module_sidebar import ModuleSidebar  # noqa: E402


def fresh_store() -> ModuleStore:
    store = ModuleStore(root=Path(tempfile.mkdtemp()) / "UniDocs")
    store.root.mkdir(parents=True, exist_ok=True)
    store.save_module(Module(title="Math"))
    group = store.create_group("School")
    store.save_module(Module(title="Physics", group=group))
    return store


def make_sidebar(store: ModuleStore) -> ModuleSidebar:
    sidebar = ModuleSidebar(store=store)
    sidebar.update = lambda *a, **k: None  # type: ignore[method-assign]
    sidebar.modules_list.update = lambda *a, **k: None  # type: ignore[method-assign]
    # The "New group…" prompt is normally built in did_mount (needs a page).
    sidebar._new_group_field = ft.TextField()
    sidebar._new_group_status = ft.Text()
    sidebar._new_group_dialog = ft.AlertDialog()
    sidebar._new_group_dialog.update = lambda *a, **k: None
    return sidebar


def titles(sidebar: ModuleSidebar) -> list[str]:
    return [sidebar._tile_module(c).title for c in sidebar.modules_list.controls]


def test_group_filter() -> None:
    store = fresh_store()
    sidebar = make_sidebar(store)

    assert titles(sidebar) == ["Math"], "Home shows only Home modules"
    sidebar._select_group("School")
    assert sidebar._active_group == "School"
    assert titles(sidebar) == ["Physics"], titles(sidebar)
    sidebar._select_group(None)
    assert titles(sidebar) == ["Math"], titles(sidebar)
    print("  group filter: ok")


def test_create_in_active_group() -> None:
    store = fresh_store()
    sidebar = make_sidebar(store)

    # Home active -> new module lands at Home.
    sidebar._on_create_module("Bio", "", ft.Icons.FOLDER, None, None)
    assert titles(sidebar) == ["Math", "Bio"], titles(sidebar)
    assert sorted(m.title for m in store.load_modules(None)) == ["Bio", "Math"]

    # "School" active -> new module lands in the group, not on screen.
    sidebar._select_group("School")
    sidebar._on_create_module("Chem", "", ft.Icons.FOLDER, None, "School")
    assert titles(sidebar) == ["Physics", "Chem"], titles(sidebar)
    assert sorted(m.title for m in store.load_modules("School")) == ["Chem", "Physics"]

    # A module created for another group than the one on screen is not listed.
    sidebar._select_group(None)
    sidebar._on_create_module("Art", "", ft.Icons.FOLDER, None, "School")
    assert titles(sidebar) == ["Math", "Bio"], titles(sidebar)
    assert "Art" in [m.title for m in store.load_modules("School")]
    print("  create in active group: ok")


def test_new_group_prompt() -> None:
    store = fresh_store()
    sidebar = make_sidebar(store)

    sidebar._open_new_group_dialog()
    assert sidebar._new_group_dialog.open is True

    sidebar._new_group_field.value = "Work"
    sidebar._commit_new_group()
    assert store.list_group_names() == ["School", "Work"], store.list_group_names()
    assert sidebar._active_group == "Work"
    assert titles(sidebar) == [], titles(sidebar)
    print("  new group prompt: ok")


def main() -> None:
    test_group_filter()
    test_create_in_active_group()
    test_new_group_prompt()
    print("MODULE GROUPS OK")


if __name__ == "__main__":
    main()
