"""
tools/import_dialog_smoke.py
----------------------------
Headless check of the import dialog's name guards.

Two things must be refused before a single byte is copied:

* a file that would end up with a name already present in the target module
* two staged files that would collide on the same final name

    .venv/bin/python tools/import_dialog_smoke.py
"""

import sys
import tempfile
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import flet as ft  # noqa: E402

from app_storage.module_store import ModuleStore  # noqa: E402
from models.module import Module  # noqa: E402
from ui.import_dialog import ImportDialog  # noqa: E402

failures: list[str] = []


def check(label: str, got, expected) -> None:
    ok = got == expected
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got!r}")
    if not ok:
        failures.append(label)
        print(f"       expected: {expected!r}")


class _PickedFile:
    """Just enough of a FilePickerResultFile (name + path)."""

    def __init__(self, path: Path):
        self.path = str(path)
        self.name = path.name


def headless(dialog: ImportDialog) -> ImportDialog:
    """Stub the repaint hook -- there is no page in this test."""
    dialog.update = lambda *a, **k: None
    return dialog


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    root = tmp / "UniDocs"
    store = ModuleStore(root=root)
    store.save_module(Module(title="Math"))

    module_dir = root / "Math"
    (module_dir / "notes.pdf").write_text("existing", encoding="utf-8")

    src = tmp / "src"
    src.mkdir()
    existing_like = src / "notes.pdf"
    existing_like.write_text("new", encoding="utf-8")
    fresh_a = src / "a.txt"
    fresh_a.write_text("a", encoding="utf-8")
    fresh_b = src / "b.txt"
    fresh_b.write_text("b", encoding="utf-8")
    clean = src / "fresh.pdf"
    clean.write_text("fresh", encoding="utf-8")

    def open_dialog():
        dialog = headless(ImportDialog(store=store))
        dialog.open = True
        dialog._selected_module = next(
            m for m in store.load_all() if m.title == "Math"
        )
        return dialog

    print("importing a name that is already in the module is blocked:")
    dialog = open_dialog()
    dialog._picked_files = [_PickedFile(existing_like)]
    dialog._import(None)
    check("error shown", "Already in this module" in dialog._status.value, True)
    check("dialog stays open", dialog.open, True)
    check("existing file untouched",
          (module_dir / "notes.pdf").read_text(encoding="utf-8"), "existing")
    check("no suffixed copy was made", (module_dir / "notes (2).pdf").exists(), False)

    print("two staged files that collapse onto the same name are blocked:")
    dialog = open_dialog()
    dialog._picked_files = [_PickedFile(fresh_a), _PickedFile(fresh_b)]
    dialog._display_names = {"a.txt": "same", "b.txt": "same"}
    dialog._import(None)
    check("error shown", "used more than once" in dialog._status.value, True)
    check("dialog stays open", dialog.open, True)
    check("nothing copied", (module_dir / "same.txt").exists(), False)

    print("a clean import still goes through:")
    dialog = open_dialog()
    dialog._picked_files = [_PickedFile(clean)]
    dialog._import(None)
    check("dialog closed", dialog.open, False)
    check("file landed in the module",
          (module_dir / "fresh.pdf").read_text(encoding="utf-8"), "fresh")

    print("a rename inside the dialog is respected by the guard:")
    renamed = src / "report.pdf"
    renamed.write_text("report", encoding="utf-8")
    dialog = open_dialog()
    dialog._picked_files = [_PickedFile(renamed)]
    dialog._display_names = {"report.pdf": "notes.pdf"}  # -> clashes with notes.pdf
    dialog._import(None)
    check("error shown", "Already in this module" in dialog._status.value, True)
    check("still open", dialog.open, True)
    check("nothing copied",
          (module_dir / "notes.pdf").read_text(encoding="utf-8"), "existing")

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("IMPORT DIALOG OK")
