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
from ui.group_home import GroupHomeDetail  # noqa: E402


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


def test_rename_group_store() -> None:
    store = fresh_store()

    assert store.group_rename_conflict("School", "Math") is True
    assert store.group_rename_conflict("School", "School") is False
    assert store.group_rename_conflict("School", "Uni") is False

    # Illegal characters are stripped, exactly like a new group name.
    new_name = store.rename_group("School", "Uni:versity")
    assert new_name == "University", new_name
    assert store.list_group_names() == ["University"], store.list_group_names()
    # The modules (and their order) travel with the folder.
    assert [m.title for m in store.load_modules("University")] == ["Physics"]

    # A conflicting rename is refused and leaves the folder alone.
    try:
        store.rename_group("University", "Math")
    except ValueError:
        pass
    else:
        raise AssertionError("conflicting rename should raise")
    assert store.list_group_names() == ["University"]
    print("  rename group (store): ok")


def test_sidebar_follows_rename() -> None:
    store = fresh_store()
    sidebar = make_sidebar(store)
    sidebar._select_group("School")

    store.rename_group("School", "Uni")
    sidebar.on_group_renamed("School", "Uni")
    assert sidebar._active_group == "Uni"
    assert titles(sidebar) == ["Physics"], titles(sidebar)
    print("  sidebar follows rename: ok")


def test_home_page_rename() -> None:
    store = fresh_store()
    renamed = []
    home = GroupHomeDetail(
        store=store, on_group_renamed=lambda o, n: renamed.append((o, n))
    )
    home.update = lambda *a, **k: None  # type: ignore[method-assign]
    home.show_error = lambda message: None  # type: ignore[method-assign]

    home.set_group("School")
    assert home.title_text.value == "School"

    home.title_field.value = "Uni:versity"
    home._commit_title(None)
    assert home.title_text.value == "University", home.title_text.value
    assert renamed == [("School", "University")], renamed

    # A conflicting name is refused, the page keeps the old title.
    renamed.clear()
    home.title_field.value = "Math"
    home._commit_title(None)
    assert home.title_text.value == "University"
    assert renamed == []

    # Home is not renameable.
    home.set_group(None)
    assert home.title_text.value == "Home"
    home.title_field.value = "Something"
    home._commit_title(None)
    assert home.title_text.value == "Home"
    assert renamed == []
    print("  home page rename: ok")


def main() -> None:
    test_group_filter()
    test_create_in_active_group()
    test_new_group_prompt()
    test_rename_group_store()
    test_sidebar_follows_rename()
    test_home_page_rename()
    print("MODULE GROUPS OK")


if __name__ == "__main__":
    main()
