"""
app_storage/module_store.py
-----------------------
Filesystem-backed persistence for Module objects.

Layout
------
UniDocs/
├ tags.json              ← global tag registry: [{"id": "<uuid>", "name": "...", "color": "..."}, ...]
├ .order                 ← Home sidebar order: ["Physics 101", ...]  (folder names)
├ Physics 101/           ← a module living directly in the root ("Home")
│   ├ .meta              ← JSON: {"description": "...", "icon": "SCIENCE", "color": "#1A5FB4"}
│   ├ .doc_tags          ← {"lecture.pdf": ["<uuid1>", "<uuid2>"], ...}  (tag IDs, not names)
│   └ lecture.pdf
└ School/                ← a group: a folder holding modules instead of documents
    ├ .group             ← empty marker file that marks this folder as a group
    ├ .order             ← sidebar order for the modules inside this group
    ├ Math/
    │   ├ .meta
    │   └ ...
    └ Physics/
        └ ...

A folder is a *group* when it holds a .group marker; a folder is a *module*
when it holds a .meta file. Groups carry no .meta, so they are never read as
modules.

Tags are stored by their stable UUID in .doc_tags, so renaming or recoloring
a tag never breaks existing assignments.
"""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from pathlib import Path

import flet as ft

from app_storage.io_utils import write_json
from app_logging import get_logger
from models.module import Module
from models.document import Document
from models.tag import Tag, DEFAULT_TAG_COLOR

log = get_logger(__name__)

UNIDOCS_DIR = Path(__file__).parent.parent / "UniDocs"
META_FILENAME = ".meta"
DOC_TAGS_FILENAME = ".doc_tags"
GLOBAL_TAGS_FILENAME = "tags.json"
ORDER_FILENAME = ".order"
# Version of the `.order` payload. 1 (implicit, a bare list) stored folder
# names, 2 stores module ids - see ModuleStore._migrate_order.
ORDER_VERSION = 2
GROUP_MARKER_FILENAME = ".group"
# Home page config per group (see app_storage.home_store.HomeStore). The store
# only ever needs to know the name so the watcher can ignore it.
HOME_FILENAME = ".home.json"
_DEFAULT_ICON_NAME = "FOLDER"

# ``ft.Icons`` value -> attribute name, filled on first use (see _icon_names).
_ICON_NAME_CACHE: dict | None = None
_ICON_CACHE_LOCK = threading.Lock()

# -- folder names ------------------------------------------------------------

# Characters Windows forbids in a file name. macOS and Linux allow most of
# them, but a folder name has to work on every OS the app runs on.
ILLEGAL_CHARS = '\\/:*?"<>|'

# Device names Windows refuses as a file/folder name, with or without an
# extension ("CON.txt" is just as invalid as "CON").
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Longest folder name the stores generate. Far below the 255-byte filesystem
# limit, but leaves room for a suffix on the path as a whole.
MAX_NAME_LENGTH = 100


# -- icon helpers ------------------------------------------------------------

def _icon_names() -> dict:
    """Map every ``ft.Icons`` value to its attribute name, built once.

    Scanning ``dir(ft.Icons)`` on every module load was measurable in the
    sidebar, so the mapping is built on first use and kept.
    """
    global _ICON_NAME_CACHE
    with _ICON_CACHE_LOCK:
        if _ICON_NAME_CACHE is None:
            cache: dict = {}
            for attr in dir(ft.Icons):
                try:
                    cache.setdefault(getattr(ft.Icons, attr), attr)
                except Exception as ex:
                    log.debug("Skipping unreadable icon attribute %r: %s", attr, ex)
                    continue
            _ICON_NAME_CACHE = cache
        return _ICON_NAME_CACHE


def _icon_to_name(icon_value) -> str:
    if icon_value is None:
        return _DEFAULT_ICON_NAME
    name = getattr(icon_value, "name", None)
    if name:
        return name
    try:
        return _icon_names().get(icon_value, _DEFAULT_ICON_NAME)
    except TypeError as ex:  # unhashable value, cannot be an icon
        log.debug("Unhashable icon value %r, using default: %s", icon_value, ex)
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
        self._tags_cache = None
        self._cache_lock = threading.RLock()

    # -- module CRUD ----------------------------------------------------------

    def load_modules(self, group: str | None = None) -> list[Module]:
        """Return the modules that live in *group* (``None`` = Home/root).

        The list follows the order the user moved the modules into (see
        :meth:`save_order`). Modules missing from that order are appended
        alphabetically, which is also the order used before anything has been
        rearranged.
        """
        base = self._group_dir(group)
        if not base.exists():
            return []

        found: list[tuple[str, Module]] = []
        for folder in sorted(base.iterdir()):
            if folder.is_dir():
                module = self._load_module(folder, group=group)
                if module:
                    found.append((folder.name, module))

        # Rewrite a pre-2.5.1 order file before reading it: the mapping needs
        # the loaded modules (and their ids) anyway.
        self._migrate_order(group, [module for _, module in found])

        order = self.load_order(group)
        if order:
            rank = {module_id: i for i, module_id in enumerate(order)}
            found.sort(key=lambda item: rank.get(item[1].id, len(rank)))
        return [module for _, module in found]

    def load_all(self) -> list[Module]:
        """Every module, Home first, then group by group (flattened)."""
        modules = self.load_modules(None)
        for group in self.list_group_names():
            modules.extend(self.load_modules(group))
        return modules

    def list_group_names(self) -> list[str]:
        """Folder names of the groups (root sub-folders carrying a .group)."""
        try:
            folders = sorted(self.root.iterdir())
        except FileNotFoundError:
            return []
        return [
            folder.name
            for folder in folders
            if folder.is_dir() and (folder / GROUP_MARKER_FILENAME).exists()
        ]

    def save_module(self, module: Module) -> Path:
        folder = self._folder_for(module)
        folder.mkdir(parents=True, exist_ok=True)
        self._write_meta(folder, module)
        return folder

    def delete_module(self, module: Module):
        folder = self._folder_for(module)
        if folder.exists():
            shutil.rmtree(folder)

    def rename_module(self, module: Module, new_title: str):
        old_folder = self._folder_for(module)
        new_folder = self._group_dir(module.group) / _safe_name(new_title)
        if old_folder.exists() and old_folder != new_folder:
            old_folder.rename(new_folder)
        module.title = new_title
        # No order fix-up needed: `.order` is keyed by the module id, which a
        # rename keeps (see load_order).

    def rename_conflict(self, module: Module, new_title: str) -> bool:
        """True if renaming *module* to *new_title* would hit another module.

        Renaming to a title that maps onto the module's own folder (say, one
        that only differs by a character ``_safe_name`` strips) is not a
        conflict. Callers should check this before ``rename_module``, which
        would otherwise silently clobber the other folder.
        """
        target = self._group_dir(module.group) / _safe_name(new_title)
        if target != self._folder_for(module) and target.exists():
            return True
        # At Home level a module may not take over an existing group's folder.
        if module.group is None:
            clash = self.root / _safe_name(new_title)
            if clash != self._folder_for(module) and (clash / GROUP_MARKER_FILENAME).exists():
                return True
        return False

    # -- sidebar order --------------------------------------------------------

    def load_order(self, group: str | None = None) -> list[str]:
        """Module ids in the order the user arranged them in.

        *group* selects which list: the Home order (root ``.order``) or the
        order of the modules inside that group (``<group>/.order``). Returns an
        empty list when the order was never changed, which tells
        :meth:`load_modules` to fall back to alphabetical sorting.

        The file stores ids, not titles, so a module keeps its slot when its
        folder is renamed from the outside. An order written before 2.5.1 (a
        bare list of folder names) is mapped on the fly; ``load_modules`` then
        rewrites it as ids.
        """
        raw = self._read_order(group)
        if isinstance(raw, dict):
            ids = raw.get("ids")
            if not isinstance(ids, list):
                return []
            return [str(module_id) for module_id in ids]
        if isinstance(raw, list):
            mapped = (self._id_for_folder_name(str(name), group) for name in raw)
            return [module_id for module_id in mapped if module_id]
        return []

    def save_order(self, module_ids: list[str], group: str | None = None) -> None:
        """Persist the module order shown in the sidebar.

        *group* selects which list: the Home order (root ``.order``) or the
        order of the modules inside that group (``<group>/.order``).

        Takes module *ids*. Ids that no longer exist are harmless: they simply
        never match a module and are dropped the next time the order is
        written.
        """
        base = self._group_dir(group)
        write_json(
            base / ORDER_FILENAME,
            {
                "version": ORDER_VERSION,
                "ids": [str(module_id) for module_id in module_ids],
            },
        )

    def _read_order(self, group: str | None):
        """Raw ``.order`` payload: a list (pre-2.5.1), a dict, or ``None``."""
        path = self._group_dir(group) / ORDER_FILENAME
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    def _id_for_folder_name(self, name: str, group: str | None) -> str | None:
        """Module id of the module folder *name*, or ``None`` if there is none."""
        meta_path = self._group_dir(group) / name / META_FILENAME
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        module_id = meta.get("id")
        return str(module_id) if module_id else None

    def _migrate_order(self, group: str | None, modules: list[Module]) -> None:
        """Rewrite a pre-2.5.1 order file (folder names) as module ids.

        Runs from :meth:`load_modules`, because mapping a folder name to an id
        needs the modules - and by then every legacy module has its id written
        back into ``.meta``. A dict payload is already version 2 and left alone.
        """
        raw = self._read_order(group)
        if not isinstance(raw, list) or not raw:
            return
        by_folder = {_safe_name(module.title): module.id for module in modules}
        self.save_order(
            [by_folder[name] for name in raw if name in by_folder], group
        )

    # -- groups ---------------------------------------------------------------

    def create_group(self, name: str) -> str:
        """Create a group folder and return its (sanitised) folder name.

        Returns the existing name when the group is already there. Raises
        ``ValueError`` when the name is taken by a module instead.
        """
        folder_name = _safe_name(name)
        folder = self.root / folder_name
        if folder.exists():
            if (folder / GROUP_MARKER_FILENAME).exists():
                return folder_name
            raise ValueError(f'"{folder_name}" already exists')
        folder.mkdir(parents=True, exist_ok=True)
        (folder / GROUP_MARKER_FILENAME).touch()
        return folder_name

    def rename_group(self, old_name: str, new_name: str) -> str:
        """Rename a group folder and return the new (sanitised) folder name.

        The group's name *is* its folder name, so a rename simply moves the
        folder - the modules and their ``.order`` inside travel with it.
        """
        old_dir = self.root / _safe_name(old_name)
        new_dir = self.root / _safe_name(new_name)
        if new_dir != old_dir and new_dir.exists():
            raise ValueError(f'"{new_dir.name}" already exists')
        if old_dir.exists() and old_dir != new_dir:
            old_dir.rename(new_dir)
        return new_dir.name

    def group_rename_conflict(self, old_name: str, new_name: str) -> bool:
        """True if renaming *old_name* to *new_name* would hit an existing folder."""
        old_dir = self.root / _safe_name(old_name)
        new_dir = self.root / _safe_name(new_name)
        return new_dir != old_dir and new_dir.exists()

    def move_module_to_group(self, module: Module, group: str | None) -> None:
        """Move *module* into *group* (``None`` = Home) and follow the order."""
        target_group = _safe_name(group) if group else None
        src = self._folder_for(module)
        dst = self._group_dir(target_group) / src.name
        if src == dst:
            module.group = target_group
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            raise ValueError(f'"{module.title}" already exists in this group')
        src.rename(dst)

        # Carry the module's slot over: drop it from the old order, append it
        # to the new one (the target order is only rewritten when it exists).
        module_id = module.id
        old_order = self.load_order(module.group)
        if old_order:
            self.save_order(
                [i for i in old_order if i != module_id], module.group
            )
        new_order = self.load_order(target_group)
        if new_order and module_id not in new_order:
            new_order.append(module_id)
            self.save_order(new_order, target_group)
        module.group = target_group

    # -- document CRUD --------------------------------------------------------

    def add_document(self, module: Module, src_path: Path) -> Document:
        """Copy *src_path* into the module's folder and return a Document."""
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
        with self._cache_lock:
            if self._tags_cache is None:
                self._tags_cache = self._read_tags_from_disk()
            return self._tags_cache

    def _read_tags_from_disk(self) -> list[dict]:
        path = self.root / GLOBAL_TAGS_FILENAME
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        if not raw:
            return []
        # migrate old list-of-strings format
        if isinstance(raw[0], str):
            raw = [
                {"id": str(uuid.uuid4()), "name": n, "color": DEFAULT_TAG_COLOR}
                for n in raw
            ]
            self._write_global_tags(raw)
        # migrate old {name, color} format (no id)
        elif "id" not in raw[0]:
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
        with self._cache_lock:
            tags = self.load_all_tags()
            # prevent duplicate names
            for t in tags:
                if t["name"] == name:
                    return t
            new_tag = {"id": str(uuid.uuid4()), "name": name, "color": color or DEFAULT_TAG_COLOR}
            tags.append(new_tag)
            self._write_global_tags(tags)
            return new_tag

    def set_tag_color(self, tag_id: str, color: str) -> None:
        """Update the color for a tag (identified by ID)."""
        with self._cache_lock:
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
        with self._cache_lock:
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
        with self._cache_lock:
            tags = [t for t in self.load_all_tags() if t["id"] != tag_id]
            self._write_global_tags(tags)

        # strip from every module's .doc_tags (Home modules and grouped ones)
        for folder in self._iter_module_dirs():
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
            from watchdog.events import (
                EVENT_TYPE_CLOSED,
                EVENT_TYPE_CLOSED_NO_WRITE,
                EVENT_TYPE_OPENED,
                FileSystemEventHandler,
            )
        except ImportError:
            return

        with self._watch_lock:
            if self._observer and self._observer.is_alive():
                return

            store = self

            # Merely *reading* a file or listing a folder already makes
            # inotify report "opened" / "closed" events. Reacting to those
            # would feed the watcher with its own reload: the reload reads
            # every module folder, which fires more open/close events, which
            # reload again - a loop that pegs a CPU core and starves the UI.
            # Only real changes (create / modify / delete / move) reload.
            _read_noise = {
                EVENT_TYPE_OPENED,
                EVENT_TYPE_CLOSED,
                EVENT_TYPE_CLOSED_NO_WRITE,
            }

            class _Handler(FileSystemEventHandler):
                def on_any_event(self, event):
                    if event.event_type in _read_noise:
                        return
                    # Our own bookkeeping files: .meta and .order are written
                    # by code that repaints itself, and .home.json is the home
                    # page's own config, so reacting here would only trigger a
                    # pointless reload.
                    if Path(event.src_path).name in (
                        META_FILENAME,
                        ORDER_FILENAME,
                        HOME_FILENAME,
                    ):
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
        return self._group_dir(module.group) / _safe_name(module.title)

    def _group_dir(self, group: str | None) -> Path:
        """Folder a group's modules live in; the UniDocs root for Home."""
        return self.root / _safe_name(group) if group else self.root

    def _iter_module_dirs(self):
        """Yield every module folder, in the root and inside every group."""
        bases = [self.root] + [self.root / name for name in self.list_group_names()]
        for base in bases:
            if not base.exists():
                continue
            for folder in base.iterdir():
                if folder.is_dir() and (folder / META_FILENAME).exists():
                    yield folder

    def _load_module(self, folder: Path, group: str | None = None) -> Module | None:
        meta_path = folder / META_FILENAME
        if not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        icon_name = meta.get("icon", _DEFAULT_ICON_NAME)
        module = Module.from_meta(
            title=folder.name,
            meta=meta,
            icon=_name_to_icon(icon_name),
            group=group,
        )
        if not meta.get("id"):
            # Module from before 2.5.1: keep the id we just generated, so it
            # is the same on every later load.
            self._write_meta(folder, module)

        # build id→Tag lookup from the live global registry
        tag_map: dict[str, Tag] = {
            t["id"]: Tag.from_dict(t) for t in self.load_all_tags()
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
        write_json(
            folder / META_FILENAME,
            module.to_meta(_icon_to_name(module.icon or _DEFAULT_ICON_NAME)),
        )

    def _read_doc_tags(self, folder: Path) -> dict:
        path = folder / DOC_TAGS_FILENAME
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write_doc_tags(self, folder: Path, data: dict) -> None:
        write_json(folder / DOC_TAGS_FILENAME, data)

    def _write_global_tags(self, tags: list[dict]) -> None:
        with self._cache_lock:
            write_json(self.root / GLOBAL_TAGS_FILENAME, tags)
            self._tags_cache = tags


def _safe_name(title: str) -> str:
    """Turn a module/group title into a folder name that is safe everywhere.

    Dropped: the characters Windows forbids (``\\ / : * ? " < > |``), control
    characters, and trailing dots/spaces (Windows silently strips those, so
    two names would otherwise end up in one folder).

    ``.`` and ``..`` are refused explicitly: they would make the module
    folder the parent of the UniDocs root, and ``delete_module`` would remove
    the lot. Empty results fall back to ``"Untitled"``, names Windows
    reserves (``CON``, ``NUL``, ``COM1``, …) get a trailing underscore.
    """
    cleaned = "".join(
        c for c in title if c not in ILLEGAL_CHARS and c >= " " and c != "\x7f"
    )
    cleaned = cleaned.strip().rstrip(". ")
    if len(cleaned) > MAX_NAME_LENGTH:
        cleaned = cleaned[:MAX_NAME_LENGTH].rstrip(". ")
    if not cleaned or cleaned in {".", ".."}:
        return "Untitled"
    if cleaned.split(".")[0].strip().upper() in _WINDOWS_RESERVED:
        cleaned = f"{cleaned}_"
    return cleaned