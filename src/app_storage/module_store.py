"""
storage/module_store.py
-----------------------
Filesystem-backed persistence for Module objects.

Layout
------
UniDocs/
├ tags.json              ← global tag registry: [{"id": "<uuid>", "name": "...", "color": "..."}, ...]
├ Physics 101/
│   ├ .meta              ← JSON: {"description": "...", "icon": "SCIENCE"}
│   ├ .doc_tags          ← {"lecture.pdf": ["<uuid1>", "<uuid2>"], ...}  (tag IDs, not names)
│   └ lecture.pdf
└ Math/
    ├ .meta
    └ ...

Tags are stored by their stable UUID in .doc_tags, so renaming or recoloring
a tag never breaks existing assignments.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import flet as ft

from models.module import Module
from models.document import Document
from models.tag import Tag, DEFAULT_TAG_COLOR

UNIDOCS_DIR = Path(__file__).parent.parent / "UniDocs"
META_FILENAME = ".meta"
DOC_TAGS_FILENAME = ".doc_tags"
GLOBAL_TAGS_FILENAME = "tags.json"
_DEFAULT_ICON_NAME = "FOLDER"


# -- icon helpers ------------------------------------------------------------

def _icon_to_name(icon_value) -> str:
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
    return getattr(ft.Icons, name.upper(), ft.Icons.FOLDER)


# -- store --------------------------------------------------------------------

class ModuleStore:
    """
    Reads and writes modules from/to the UniDocs directory.

    Parameters
    ----------
    root : Path, optional
        Root folder.
    on_change : callable, optional
        Called (no arguments) from a background thread on filesystem changes.
    """

    def __init__(self, root: Path = UNIDOCS_DIR, on_change=None):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._on_change = on_change
        self._observer = None
        self._watch_lock = threading.Lock()

    # -- module CRUD ----------------------------------------------------------

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
        folder = self._folder_for(module)
        folder.mkdir(parents=True, exist_ok=True)
        self._write_meta(folder, module)
        return folder

    def delete_module(self, module: Module):
        import shutil
        folder = self._folder_for(module)
        if folder.exists():
            shutil.rmtree(folder)

    def rename_module(self, module: Module, new_title: str):
        old_folder = self._folder_for(module)
        new_folder = self.root / _safe_name(new_title)
        if old_folder.exists() and old_folder != new_folder:
            old_folder.rename(new_folder)
        module.title = new_title

    # -- document CRUD --------------------------------------------------------

    def add_document(self, module: Module, src_path: Path) -> Document:
        """Copy *src_path* into the module's folder and return a Document."""
        import shutil
        folder = self._folder_for(module)
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / src_path.name
        stem, suffix = dest.stem, dest.suffix
        counter = 2
        while dest.exists():
            dest = folder / f"{stem} ({counter}){suffix}"
            counter += 1
        shutil.copy2(src_path, dest)
        doc = Document(title=dest.stem, description="", filepath=str(dest))
        module.add_document(doc)
        return doc

    def rename_document(self, doc: Document, new_stem: str) -> str:
        """
        Rename a document file on disk (stem only, extension preserved).
        Updates doc.title and doc.filepath in place.
        Also migrates the .doc_tags entry so tag assignments are preserved.
        Returns the new filepath string.
        """
        old_path = Path(doc.filepath)
        new_path = old_path.with_name(new_stem + old_path.suffix)
        counter = 2
        base_stem = new_stem
        while new_path.exists() and new_path != old_path:
            new_path = old_path.with_name(f"{base_stem} ({counter}){old_path.suffix}")
            counter += 1

        old_path.rename(new_path)

        # -- migrate .doc_tags key --------------------------------------------
        folder = old_path.parent
        doc_tags = self._read_doc_tags(folder)
        old_filename = old_path.name
        new_filename = new_path.name
        if old_filename in doc_tags:
            doc_tags[new_filename] = doc_tags.pop(old_filename)
            self._write_doc_tags(folder, doc_tags)

        doc.title = new_path.stem
        doc.filepath = str(new_path)
        return str(new_path)

    def delete_document(self, module: Module, doc: Document) -> None:
        """Delete a document file from disk and remove it from module.documents."""
        path = Path(doc.filepath)

        # remove from .doc_tags
        folder = path.parent
        doc_tags = self._read_doc_tags(folder)
        if path.name in doc_tags:
            del doc_tags[path.name]
            self._write_doc_tags(folder, doc_tags)

        if path.exists():
            path.unlink()
        module.documents = [d for d in module.documents if d.filepath != doc.filepath]

    # -- tag registry CRUD ----------------------------------------------------
    #
    # tags.json format: [{"id": "<uuid>", "name": "Lecture", "color": "#..."}, ...]
    # Old name-only format (list of strings) is auto-migrated on first read.

    def load_all_tags(self) -> list[dict]:
        """Return the global tag list as [{"id": ..., "name": ..., "color": ...}, ...]."""
        path = self.root / GLOBAL_TAGS_FILENAME
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        if not raw:
            return []
        # migrate old list-of-strings format
        if isinstance(raw[0], str):
            import uuid
            raw = [{"id": str(uuid.uuid4()), "name": n, "color": DEFAULT_TAG_COLOR} for n in raw]
            self._write_global_tags(raw)
        # migrate old {name, color} format (no id)
        elif "id" not in raw[0]:
            import uuid
            for entry in raw:
                entry.setdefault("id", str(uuid.uuid4()))
            self._write_global_tags(raw)
        return raw

    def load_tag_names(self) -> list[str]:
        return [t["name"] for t in self.load_all_tags()]

    def get_tag_by_id(self, tag_id: str) -> dict | None:
        for t in self.load_all_tags():
            if t["id"] == tag_id:
                return t
        return None

    def add_global_tag(self, name: str, color: str | None = None) -> dict:
        """Add a new tag to the global registry. Returns the new tag dict."""
        import uuid
        tags = self.load_all_tags()
        # prevent duplicate names
        if any(t["name"] == name for t in tags):
            # return the existing one
            for t in tags:
                if t["name"] == name:
                    return t
        new_tag = {"id": str(uuid.uuid4()), "name": name, "color": color or DEFAULT_TAG_COLOR}
        tags.append(new_tag)
        self._write_global_tags(tags)
        return new_tag

    def set_tag_color(self, tag_id: str, color: str) -> None:
        """Update the color for a tag (identified by ID)."""
        tags = self.load_all_tags()
        for t in tags:
            if t["id"] == tag_id:
                t["color"] = color
                break
        self._write_global_tags(tags)

    def rename_global_tag(self, tag_id: str, new_name: str) -> None:
        """
        Rename a tag in the global registry.
        Because .doc_tags stores IDs, no per-module migration is needed.
        """
        tags = self.load_all_tags()
        existing_names = [t["name"] for t in tags if t["id"] != tag_id]
        if new_name in existing_names:
            return  # name collision
        for t in tags:
            if t["id"] == tag_id:
                t["name"] = new_name
                break
        self._write_global_tags(tags)

    def remove_global_tag(self, tag_id: str) -> None:
        """
        Remove a tag from the global registry and strip it from all .doc_tags files.
        """
        tags = [t for t in self.load_all_tags() if t["id"] != tag_id]
        self._write_global_tags(tags)

        # strip from every module's .doc_tags
        for folder in self.root.iterdir():
            if not folder.is_dir():
                continue
            doc_tags = self._read_doc_tags(folder)
            changed = False
            for fname in list(doc_tags.keys()):
                if tag_id in doc_tags[fname]:
                    doc_tags[fname] = [tid for tid in doc_tags[fname] if tid != tag_id]
                    changed = True
            if changed:
                self._write_doc_tags(folder, doc_tags)

    def save_doc_tags(self, module: Module, doc: Document, tag_ids: list[str]) -> None:
        """Persist tag-ID assignments for a single document."""
        folder = self._folder_for(module)
        doc_tags = self._read_doc_tags(folder)
        filename = Path(doc.filepath).name
        doc_tags[filename] = tag_ids
        self._write_doc_tags(folder, doc_tags)

    # -- filesystem watcher ---------------------------------------------------

    def start_watching(self):
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            return

        with self._watch_lock:
            if self._observer and self._observer.is_alive():
                return

            store = self

            class _Handler(FileSystemEventHandler):
                def on_any_event(self, event):
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

    # -- private helpers ------------------------------------------------------

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

        # build id→Tag lookup from the live global registry
        tag_map: dict[str, Tag] = {
            t["id"]: Tag(t["id"], t["name"], t["color"])
            for t in self.load_all_tags()
        }

        doc_tags_map = self._read_doc_tags(folder)

        for f in sorted(folder.iterdir()):
            if f.is_file() and f.name not in (META_FILENAME, DOC_TAGS_FILENAME):
                raw_ids = doc_tags_map.get(f.name, [])
                # resolve IDs → Tag objects; silently skip unknown IDs
                resolved_tags = [tag_map[tid] for tid in raw_ids if tid in tag_map]
                module.add_document(
                    Document(
                        title=f.stem,
                        description="",
                        filepath=str(f),
                        tags=resolved_tags,
                    )
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

    def _read_doc_tags(self, folder: Path) -> dict:
        path = folder / DOC_TAGS_FILENAME
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write_doc_tags(self, folder: Path, data: dict) -> None:
        (folder / DOC_TAGS_FILENAME).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _write_global_tags(self, tags: list[dict]) -> None:
        (self.root / GLOBAL_TAGS_FILENAME).write_text(
            json.dumps(tags, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _safe_name(title: str) -> str:
    illegal = r'\/:*?"<>|'
    return "".join(c for c in title if c not in illegal).strip() or "Untitled"