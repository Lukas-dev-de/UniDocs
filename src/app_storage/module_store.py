"""
storage/module_store.py
-----------------------
Filesystem-backed persistence for Module objects.

Layout
------
UniDocs/
├── Physics 101/
│   ├── .meta           ← JSON: {"description": "...", "icon": "SCIENCE"}
│   └── lecture.pdf     ← documents (any file)
└── Math/
    ├── .meta
    └── ...

The icon is stored as the bare icon-name string (e.g. "SCIENCE"),
resolved to ft.Icons.<name> on load.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import flet as ft

from models.module import Module
from models.document import Document

UNIDOCS_DIR = Path(__file__).parent.parent / "UniDocs"
META_FILENAME = ".meta"
_DEFAULT_ICON_NAME = "FOLDER"

# helperfunctions
def _icon_to_name(icon_value) -> str:
    """
    Convert an ft.Icons enum member to its string name for storage.
    ft.Icons.ADD  →  "ADD"
    Falls back to the default if the value is None or unrecognised.
    """
    if icon_value is None:
        return _DEFAULT_ICON_NAME
    name = getattr(icon_value, "name", None)
    if name:
        return name
    for attr in dir(ft.Icons):
        try:
            if getattr(ft.Icons, attr) == icon_value:
                return attr
        except Exception:
            pass
    return _DEFAULT_ICON_NAME


def _name_to_icon(name: str):
    """Return the ft.Icons value for a stored name, falling back to FOLDER."""
    return getattr(ft.Icons, name.upper(), ft.Icons.FOLDER)



class ModuleStore:
    """
    Reads and writes modules from/to the UniDocs directory.

    Parameters
    ----------
    root : Path, optional
        Root folder. Defaults to UniDocs/ next to main.py.
    on_change : callable, optional
        Called (with no arguments) from a background thread whenever
        the filesystem changes externally.  Use page.run_thread_safe /
        page.invoke_method to update UI safely.
    """

    def __init__(self, root: Path = UNIDOCS_DIR, on_change=None):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._on_change = on_change
        self._observer = None
        self._watch_lock = threading.Lock()


    # crud-functions
    def load_all(self) -> list[Module]:
        """Return a Module for every sub-folder that contains a .meta file."""
        modules: list[Module] = []
        for folder in sorted(self.root.iterdir()):
            if folder.is_dir():
                module = self._load_module(folder)
                if module:
                    modules.append(module)
        return modules

    def save_module(self, module: Module) -> Path:
        """
        Persist a module.  Creates the folder if it does not exist.
        Returns the module's folder path.
        """
        folder = self._folder_for(module)
        folder.mkdir(parents=True, exist_ok=True)
        self._write_meta(folder, module)
        return folder

    def delete_module(self, module: Module):
        """Remove the module folder and all its contents."""
        import shutil
        folder = self._folder_for(module)
        if folder.exists():
            shutil.rmtree(folder)

    def rename_module(self, module: Module, new_title: str):
        """Rename the module folder and update module.title."""
        old_folder = self._folder_for(module)
        new_folder = self.root / _safe_name(new_title)
        if old_folder.exists() and old_folder != new_folder:
            old_folder.rename(new_folder)
        module.title = new_title

    def rename_document(self, doc, new_stem: str) -> str:
        """
        Rename a document file on disk (stem only, extension preserved).
        Updates doc.title and doc.filepath in place.
        Returns the new filepath string.
        """
        old_path = Path(doc.filepath)
        new_path = old_path.with_name(new_stem + old_path.suffix)
        # avoid clobbering
        counter = 2
        base = new_path
        while new_path.exists() and new_path != old_path:
            new_path = base.with_name(f"{new_stem} ({counter}){old_path.suffix}")
            counter += 1
        old_path.rename(new_path)
        doc.title = new_path.stem
        doc.filepath = str(new_path)
        return str(new_path)

    def delete_document(self, module: Module, doc) -> None:
        """Delete a document file from disk and remove it from module.documents."""
        path = Path(doc.filepath)
        if path.exists():
            path.unlink()
        module.documents = [d for d in module.documents if d.filepath != doc.filepath]

    def add_document(self, module: Module, src_path: Path) -> Document:
        """
        Copy *src_path* into the module's folder and return a Document.
        """
        import shutil
        folder = self._folder_for(module)
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / src_path.name
        # avoid clobbering: append (2), (3), … if name already exists
        stem, suffix = dest.stem, dest.suffix
        counter = 2
        while dest.exists():
            dest = folder / f"{stem} ({counter}){suffix}"
            counter += 1
        shutil.copy2(src_path, dest)
        doc = Document(title=dest.stem, description="", filepath=str(dest))
        module.add_document(doc)
        return doc

    # filesystem watcher -> does not work yet
    def start_watching(self):
        """
        Start a watchdog observer that calls self._on_change whenever
        UniDocs changes on disk (external edits, other processes, etc.).

        Safe to call multiple times – only one observer runs at a time.
        """
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            # watchdog not installed – silently skip live-sync
            return

        with self._watch_lock:
            if self._observer and self._observer.is_alive():
                return

            store = self

            class _Handler(FileSystemEventHandler):
                def on_any_event(self, event):
                    # ignore .meta writes triggered own save_module
                    if event.src_path.endswith(META_FILENAME):
                        return
                    if store._on_change:
                        store._on_change()

            observer = Observer()
            observer.schedule(_Handler(), str(self.root), recursive=True)
            observer.daemon = True
            observer.start()
            self._observer = observer

    def stop_watching(self):
        with self._watch_lock:
            if self._observer:
                self._observer.stop()
                self._observer.join(timeout=2)
                self._observer = None

    # helpers
    def _folder_for(self, module: Module) -> Path:
        return self.root / _safe_name(module.title)

    def _load_module(self, folder: Path) -> Module | None:
        meta_path = folder / META_FILENAME
        if not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        icon_name = meta.get("icon", _DEFAULT_ICON_NAME)
        module = Module(
            title=folder.name,
            description=meta.get("description", ""),
            icon=_name_to_icon(icon_name),
        )
        # load documents (every non-meta file)
        for f in sorted(folder.iterdir()):
            if f.is_file() and f.name != META_FILENAME:
                module.add_document(
                    Document(title=f.stem, description="", filepath=str(f))
                )
        return module

    def _write_meta(self, folder: Path, module: Module):
        meta = {
            "description": module.description,
            "icon": _icon_to_name(module.icon or _DEFAULT_ICON_NAME),
        }
        (folder / META_FILENAME).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _safe_name(title: str) -> str:
    """Strip characters that are illegal in folder names on common OSes."""
    illegal = r'\/:*?"<>|'
    return "".join(c for c in title if c not in illegal).strip() or "Untitled"