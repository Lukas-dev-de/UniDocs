"""
tools/module_order_smoke.py
---------------------------
Headless check of the sidebar's "Move up" / "Move down" menu entries.

Covers both halves: the .order file that remembers the arrangement, and the
sidebar handler that performs one move and writes it back.

    .venv/bin/python tools/module_order_smoke.py
"""

import json
import sys
import tempfile
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from app_storage.module_store import ModuleStore, ORDER_FILENAME  # noqa: E402
from models.module import Module  # noqa: E402
from ui.module_sidebar import ModuleSidebar  # noqa: E402


class _Event:
    """Just enough of a TapEvent for the context menu handler."""

    class _Pos:
        x = 10.0
        y = 20.0

    global_position = _Pos()


class _MenuRecorder:
    """Stands in for ContextMenu, capturing the entries it was shown."""

    def __init__(self):
        self.items = None

    def show(self, x, y, items):
        self.items = [(label, cb) for label, _icon, _color, cb in items]


def headless(sidebar: ModuleSidebar) -> None:
    """Neutralise the calls that need a real page."""
    sidebar.update = lambda *a, **k: None  # type: ignore[method-assign]
    sidebar.modules_list.update = lambda *a, **k: None  # type: ignore[method-assign]
    for selector in (sidebar.icon_selector, sidebar.color_selector):
        selector.reset = lambda *a, **k: None  # type: ignore[method-assign]


def fresh_store() -> ModuleStore:
    store = ModuleStore(root=Path(tempfile.mkdtemp()) / "UniDocs")
    store.root.mkdir(parents=True, exist_ok=True)
    for title in ("Math", "Physics", "Chemistry"):
        store.save_module(Module(title=title))
    return store


def make_sidebar(store: ModuleStore) -> ModuleSidebar:
    sidebar = ModuleSidebar(store=store)
    headless(sidebar)
    sidebar._ctx_menu = _MenuRecorder()
    return sidebar


def titles(sidebar: ModuleSidebar) -> list[str]:
    return [sidebar._tile_module(c).title for c in sidebar.modules_list.controls]


def displayed(store: ModuleStore) -> list[str]:
    return [m.title for m in store.load_all()]


def test_order_roundtrip() -> None:
    store = fresh_store()
    assert store.load_order() == [], "a new install has no saved order"
    assert not (store.root / ORDER_FILENAME).exists(), "nothing written until moved"

    store.save_order(["Chemistry", "Math", "Physics"])
    assert json.loads((store.root / ORDER_FILENAME).read_text())[0] == "Chemistry"
    assert displayed(store) == ["Chemistry", "Math", "Physics"], displayed(store)

    # A name that no longer exists must not hide the modules that do.
    store.save_order(["Ghost", "Physics"])
    assert displayed(store) == ["Physics", "Chemistry", "Math"], displayed(store)
    print("  order round-trip: ok")


def test_corrupt_order() -> None:
    store = fresh_store()
    (store.root / ORDER_FILENAME).write_text("{ not json")
    assert store.load_order() == []
    assert displayed(store) == ["Chemistry", "Math", "Physics"], "falls back to A-Z"

    (store.root / ORDER_FILENAME).write_text('{"a": 1}')
    assert store.load_order() == [], "a non-list is ignored too"
    print("  corrupt order: ok")


def test_rename_follows_order() -> None:
    store = fresh_store()
    store.save_order(["Chemistry", "Math", "Physics"])

    chemistry = next(m for m in store.load_all() if m.title == "Chemistry")
    store.rename_module(chemistry, "Chem 2")
    assert store.load_order() == ["Chem 2", "Math", "Physics"], store.load_order()
    assert displayed(store) == ["Chem 2", "Math", "Physics"], displayed(store)
    print("  rename keeps its slot: ok")


def test_move_down_and_up() -> None:
    store = fresh_store()
    sidebar = make_sidebar(store)
    assert titles(sidebar) == ["Chemistry", "Math", "Physics"], titles(sidebar)

    sidebar._move_module(sidebar._tile_module(sidebar.modules_list.controls[0]), +1)
    assert titles(sidebar) == ["Math", "Chemistry", "Physics"], titles(sidebar)
    assert store.load_order() == ["Math", "Chemistry", "Physics"], store.load_order()
    assert displayed(store) == ["Math", "Chemistry", "Physics"], displayed(store)

    sidebar._move_module(sidebar._tile_module(sidebar.modules_list.controls[2]), -1)
    assert titles(sidebar) == ["Math", "Physics", "Chemistry"], titles(sidebar)
    assert store.load_order() == ["Math", "Physics", "Chemistry"], store.load_order()

    # A reload keeps the arrangement instead of reverting to alphabetical.
    sidebar._reload_and_update()
    assert titles(sidebar) == ["Math", "Physics", "Chemistry"], titles(sidebar)
    print("  move up / down: ok")


def test_move_edges() -> None:
    store = fresh_store()
    sidebar = make_sidebar(store)

    top = sidebar._tile_module(sidebar.modules_list.controls[0])
    bottom = sidebar._tile_module(sidebar.modules_list.controls[-1])
    sidebar._move_module(top, -1)
    sidebar._move_module(bottom, +1)
    assert titles(sidebar) == ["Chemistry", "Math", "Physics"], titles(sidebar)
    assert not (store.root / ORDER_FILENAME).exists(), "a no-op must not persist"

    # A module that is no longer listed (deleted elsewhere) is a no-op.
    sidebar._move_module(Module(title="Gone"), -1)
    assert titles(sidebar) == ["Chemistry", "Math", "Physics"], titles(sidebar)
    print("  edges and stale modules: ok")


def test_menu_entries() -> None:
    store = fresh_store()
    sidebar = make_sidebar(store)
    controls = sidebar.modules_list.controls

    def entries(index: int) -> dict:
        sidebar._show_module_menu(_Event(), sidebar._tile_module(controls[index]))
        return {label: cb is not None for label, cb in sidebar._ctx_menu.items}

    top, middle, bottom = entries(0), entries(1), entries(2)
    assert list(top) == ["Edit", "Move up", "Move down", "Delete"], list(top)
    assert top == {"Edit": True, "Move up": False, "Move down": True, "Delete": True}, top
    assert middle == {"Edit": True, "Move up": True, "Move down": True, "Delete": True}, middle
    assert bottom == {"Edit": True, "Move up": True, "Move down": False, "Delete": True}, bottom

    # Clicking the enabled "Move down" moves that specific module.
    sidebar._show_module_menu(_Event(), sidebar._tile_module(controls[1]))
    entries_shown = dict(sidebar._ctx_menu.items)
    entries_shown["Move down"]()
    assert titles(sidebar) == ["Chemistry", "Physics", "Math"], titles(sidebar)
    print("  menu entries: ok")


def test_add_module_goes_last() -> None:
    store = fresh_store()
    sidebar = make_sidebar(store)

    sidebar._move_module(sidebar._tile_module(sidebar.modules_list.controls[0]), +2)
    assert titles(sidebar) == ["Math", "Physics", "Chemistry"], titles(sidebar)

    sidebar.title_field.value = "Biology"
    sidebar.description_field.value = ""
    sidebar.add_module(None)
    assert titles(sidebar) == ["Math", "Physics", "Chemistry", "Biology"], titles(sidebar)
    assert store.load_order() == ["Math", "Physics", "Chemistry", "Biology"]
    assert displayed(store) == ["Math", "Physics", "Chemistry", "Biology"], displayed(store)
    print("  new modules land at the end: ok")


def test_order_survives_sanitised_titles() -> None:
    """Titles that _safe_name rewrites must still match their folder."""
    store = fresh_store()
    sidebar = make_sidebar(store)

    sidebar.title_field.value = "Physics: Intro"
    sidebar.description_field.value = ""
    sidebar.add_module(None)
    assert store.load_order() == [
        "Chemistry",
        "Math",
        "Physics",
        "Physics Intro",
    ], store.load_order()

    # The tile is relabelled from the folder name on reload, and the module
    # keeps its slot rather than dropping to the tail.
    sidebar._reload_and_update()
    assert titles(sidebar) == ["Chemistry", "Math", "Physics", "Physics Intro"], titles(sidebar)

    sidebar._move_module(sidebar._tile_module(sidebar.modules_list.controls[3]), -1)
    assert titles(sidebar) == ["Chemistry", "Math", "Physics Intro", "Physics"], titles(sidebar)
    assert displayed(store) == ["Chemistry", "Math", "Physics Intro", "Physics"], displayed(store)
    print("  sanitised titles keep their slot: ok")


def main() -> None:
    test_order_roundtrip()
    test_corrupt_order()
    test_rename_follows_order()
    test_move_down_and_up()
    test_move_edges()
    test_menu_entries()
    test_add_module_goes_last()
    test_order_survives_sanitised_titles()
    print("MODULE ORDER OK")


if __name__ == "__main__":
    main()
