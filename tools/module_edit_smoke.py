"""
End-to-end checks for the module edit dialog's save path.

Runs ``ModuleEditDialog._save`` against a throwaway UniDocs folder and asserts
that the changes land on disk, that documents follow a rename, and that a
rename onto an existing module is refused instead of clobbering it.

    .venv/bin/python tools/module_edit_smoke.py
"""

import sys
import tempfile
from pathlib import Path

# The app package lives in <repo>/src and uses absolute imports
# (``from ui.theme import ...``), so put that directory on the path.
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import flet as ft  # noqa: E402

from app_storage.module_store import ModuleStore  # noqa: E402
from models.module import Module  # noqa: E402
from ui.components.module_edit_dialog import ModuleEditDialog  # noqa: E402

failures: list[str] = []


def check(label: str, got, expected) -> None:
    ok = got == expected
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got!r}")
    if not ok:
        failures.append(label)
        print(f"       expected: {expected!r}")


def headless(dialog: ModuleEditDialog) -> ModuleEditDialog:
    """Stub the repaint hook -- there is no page in this test."""
    dialog.update = lambda *a, **k: None
    return dialog


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp) / "UniDocs"
    store = ModuleStore(root=root)

    store.save_module(Module(title="Math", description="old", icon=ft.Icons.CALCULATE))
    (root / "Math" / "notes.txt").write_text("x", encoding="utf-8")
    store.save_module(Module(title="Physics", description="", icon=ft.Icons.SCIENCE))

    math = next(m for m in store.load_all() if m.title == "Math")
    saved: list[tuple] = []
    dialog = headless(ModuleEditDialog(store=store, on_saved=lambda m, p: saved.append((m, p))))

    print("edit everything (rename + description + icon + colour):")
    dialog.open_for(math)
    check("form pre-filled with the current title", dialog._title_field.value, "Math")
    dialog._title_field.value = "Mathematics"
    dialog._desc_field.value = "Numbers and such"
    dialog._icon_selector.set_value(ft.Icons.NUMBERS)
    dialog._color_selector.set_value("#2E7D32")
    dialog._save()
    check("dialog closed", dialog.open, False)

    titles = sorted(m.title for m in store.load_all())
    check("module renamed on disk", titles, ["Mathematics", "Physics"])
    check("old folder gone", (root / "Math").exists(), False)
    check("document followed the rename", (root / "Mathematics" / "notes.txt").exists(), True)

    edited = next(m for m in store.load_all() if m.title == "Mathematics")
    check("description persisted", edited.description, "Numbers and such")
    check("icon persisted", edited.icon.name, "NUMBERS")
    check("colour persisted", edited.color, "#2E7D32")
    check("on_saved got the pre-edit title",
          [(m.title, prev) for m, prev in saved], [("Mathematics", "Math")])

    print("rename onto an existing module is refused:")
    physics = next(m for m in store.load_all() if m.title == "Physics")
    dialog.open_for(physics)
    dialog._title_field.value = "Mathematics"
    dialog._save()
    check("dialog stays open", dialog.open, True)
    check("inline error shown", dialog._title_field.error_text,
          "A module with this name already exists")
    check("module not renamed", physics.title, "Physics")
    check("target module intact", (root / "Mathematics" / "notes.txt").exists(), True)

    print("empty title is refused:")
    dialog.open_for(physics)
    dialog._title_field.value = "   "
    dialog._save()
    check("dialog stays open", dialog.open, True)
    check("inline error shown", dialog._title_field.error_text, "Title cannot be empty")
    check("nothing written", sorted(m.title for m in store.load_all()), ["Mathematics", "Physics"])

    print("editing without renaming in place:")
    dialog.open_for(physics)
    dialog._color_selector.set_value(None)
    dialog._save()
    physics_again = next(m for m in store.load_all() if m.title == "Physics")
    check("colour cleared", physics_again.color, None)
    check("description kept", physics_again.description, "")
    check("icon kept", physics_again.icon.name, "SCIENCE")
    check("no duplicate folder", sorted(p.name for p in root.iterdir() if p.is_dir()),
          ["Mathematics", "Physics"])

    print("renaming to a title that maps to the module's own folder:")
    dialog.open_for(physics_again)
    dialog._title_field.value = "Physics/"          # _safe_name strips the slash
    dialog._save()
    check("accepted as an in-place rename", dialog.open, False)
    check("still one module", len(store.load_all()), 2)

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("MODULE EDIT OK")
