"""Tests for the stable module id in ``.meta``."""

import json

from app_storage.module_store import META_FILENAME, ModuleStore
from models.module import Module


def make_store(tmp_path) -> ModuleStore:
    root = tmp_path / "UniDocs"
    root.mkdir()
    return ModuleStore(root=root)


def read_meta(store: ModuleStore, folder: str, group: str | None = None) -> dict:
    base = store.root if not group else store.root / group
    return json.loads((base / folder / META_FILENAME).read_text(encoding="utf-8"))


def test_saved_module_carries_its_id(tmp_path):
    store = make_store(tmp_path)
    module = Module(title="Math")

    store.save_module(module)

    assert read_meta(store, "Math")["id"] == module.id


def test_load_keeps_the_id(tmp_path):
    store = make_store(tmp_path)
    module = Module(title="Math")
    store.save_module(module)

    loaded = store.load_modules(None)[0]

    assert loaded.id == module.id


def test_legacy_module_gets_a_persisted_id(tmp_path):
    store = make_store(tmp_path)
    folder = store.root / "Old"
    folder.mkdir()
    (folder / META_FILENAME).write_text(
        json.dumps({"description": "no id yet", "icon": "FOLDER"}), encoding="utf-8"
    )

    first = store.load_modules(None)[0]

    assert first.id
    assert read_meta(store, "Old")["id"] == first.id, "id is written back"
    assert store.load_modules(None)[0].id == first.id, "and stays the same"


def test_rename_keeps_the_id(tmp_path):
    store = make_store(tmp_path)
    module = Module(title="Math")
    store.save_module(module)
    before = module.id

    store.rename_module(module, "Mathematics")

    assert module.id == before
    assert read_meta(store, "Mathematics")["id"] == before
    assert store.load_modules(None)[0].id == before


def test_move_to_group_keeps_the_id(tmp_path):
    store = make_store(tmp_path)
    module = Module(title="Math")
    store.save_module(module)
    group = store.create_group("School")

    store.move_module_to_group(module, group)

    assert read_meta(store, "Math", group=group)["id"] == module.id
    assert store.load_modules(group)[0].id == module.id
