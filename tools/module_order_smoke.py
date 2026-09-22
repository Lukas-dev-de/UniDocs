"""
Checks for the sidebar's drag-to-reorder feature.

Two halves are covered: ModuleStore's saved-order handling (including how it
survives renames), and the sidebar's ``_on_reorder`` handler, driven with a
stub list so the test does not need a page to repaint against.

    .venv/bin/python tools/module_order_smoke.py
"""

import sys
import tempfile
from pathlib import Path

# The app package lives in <repo>/src and uses absolute imports
# (``from ui.theme import ...``), so put that directory on the path.
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import flet as ft  # noqa: E402

from app_storage.module_store import ORDER_FILENAME, ModuleStore  # noqa: E402
from models.module import Module  # noqa: E402
from ui.module_sidebar import ModuleSidebar  # noqa: E402

failures: list[str] = []


def check(label: str, got, expected) -> None:
    ok = got == expected
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got!r}")
    if not ok:
        failures.append(label)
        print(f"       expected: {expected!r}")


class _ListStub:
    """Stands in for the ReorderableListView, which needs a page to repaint."""

    def __init__(self, controls):
        self.controls = list(controls)

    def update(self):
        pass


def titles(store: ModuleStore) -> list[str]:
    return [m.title for m in store.load_all()]


def order_of(sidebar) -> list[str]:
    return [sidebar._tile_module(c).title for c in sidebar.modules_list.controls]


def reorder(old_index, new_index):
    return ft.OnReorderEvent(
        name="reorder", control=None, old_index=old_index, new_index=new_index
    )


def headless(sidebar: ModuleSidebar) -> ModuleSidebar:
    """Silence the repaint hooks that need an attached page."""
    sidebar.update = lambda *a, **k: None
    sidebar.icon_selector.reset = lambda *a, **k: None
    sidebar.color_selector.reset = lambda *a, **k: None
    return sidebar


def new_store(tmp: str) -> ModuleStore:
    store = ModuleStore(root=Path(tmp) / "UniDocs")
    for name in ("Math", "Physics", "Chemistry"):
        store.save_module(Module(title=name))
    return store


# -- store: saved order ------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    store = new_store(tmp)
    root = store.root

    print("before anything is rearranged:")
    check("load_all is alphabetical", titles(store), ["Chemistry", "Math", "Physics"])
    check("load_order is empty", store.load_order(), [])
    check("no .order file written", (root / ORDER_FILENAME).exists(), False)

    print("a saved order drives load_all:")
    store.save_order(["Physics", "Chemistry", "Math"])
    check("load_all", titles(store), ["Physics", "Chemistry", "Math"])

    print("stale names in the order are ignored:")
    store.save_order(["Physics", "Ghost", "Chemistry", "Math"])
    check("load_all", titles(store), ["Physics", "Chemistry", "Math"])

    print("modules missing from the order fall in alphabetically at the end:")
    store.save_order(["Physics"])
    check("load_all", titles(store), ["Physics", "Chemistry", "Math"])

    print("an unreadable .order falls back to alphabetical:")
    (root / ORDER_FILENAME).write_text("{not json", encoding="utf-8")
    check("load_order", store.load_order(), [])
    check("load_all", titles(store), ["Chemistry", "Math", "Physics"])

    print("a rename keeps the module's place in the order:")
    store.save_order(["Physics", "Chemistry", "Math"])
    physics = next(m for m in store.load_all() if m.title == "Physics")
    store.rename_module(physics, "Astronomy")
    check("load_order follows the rename", store.load_order(),
          ["Astronomy", "Chemistry", "Math"])
    check("module kept its slot", titles(store), ["Astronomy", "Chemistry", "Math"])

with tempfile.TemporaryDirectory() as tmp:
    print("a rename without a saved order does not create one:")
    store = new_store(tmp)
    store.rename_module(store.load_all()[0], "Renamed")
    check("still no .order file", (store.root / ORDER_FILENAME).exists(), False)
    check("order unchanged", titles(store), ["Math", "Physics", "Renamed"])


# -- sidebar: drag handler ---------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    store = new_store(tmp)
    store.save_order(["Physics", "Chemistry", "Math"])

    sidebar = headless(ModuleSidebar(store=store))
    sidebar._load_from_store()
    check("tiles rendered in the stored order", order_of(sidebar),
          ["Physics", "Chemistry", "Math"])

    sidebar.modules_list = _ListStub(sidebar.modules_list.controls)

    print("dragging the last module to the top:")
    sidebar._on_reorder(reorder(old_index=2, new_index=0))
    check("controls reordered", order_of(sidebar), ["Math", "Physics", "Chemistry"])
    check("order persisted", store.load_order(), ["Math", "Physics", "Chemistry"])
    check("load_all agrees", titles(store), ["Math", "Physics", "Chemistry"])

    print("dragging the top module down one:")
    sidebar._on_reorder(reorder(old_index=0, new_index=1))
    check("controls reordered", order_of(sidebar), ["Physics", "Math", "Chemistry"])
    check("order persisted", store.load_order(), ["Physics", "Math", "Chemistry"])

    print("no-op and out-of-range drags are ignored:")
    sidebar._on_reorder(reorder(old_index=1, new_index=1))
    sidebar._on_reorder(reorder(old_index=0, new_index=99))
    sidebar._on_reorder(reorder(old_index=None, new_index=2))
    check("order untouched", order_of(sidebar), ["Physics", "Math", "Chemistry"])
    check("disk untouched", store.load_order(), ["Physics", "Math", "Chemistry"])

    print("a module added afterwards stays at the end:")
    sidebar.title_field.value = "Biology"
    sidebar.add_module(None)
    check("appended to the tiles", order_of(sidebar),
          ["Physics", "Math", "Chemistry", "Biology"])
    check("appended to the saved order", store.load_order(),
          ["Physics", "Math", "Chemistry", "Biology"])
    check("and survives a reload", titles(store),
          ["Physics", "Math", "Chemistry", "Biology"])

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("MODULE ORDER OK")
