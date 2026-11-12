"""Trash lifecycle: delete -> entry -> restore/purge, scanner safety."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app_storage.module_store import ModuleStore
from app_storage.trash_store import TrashError, TrashRestoreError, TrashStore
from models.document import Document
from models.module import Module


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "UniDocs"
    root.mkdir()
    return root


@pytest.fixture
def store(root):
    return TrashStore(root, device_id="dev-1", device_name="Laptop")


def test_move_file_and_restore(root, store):
    module = root / "Math"
    module.mkdir()
    doc = module / "lecture.pdf"
    doc.write_bytes(b"hello")

    entry = store.move_to_trash(doc, "document")

    assert not doc.exists()
    assert entry.state == "ready"
    assert entry.original_path == "Math/lecture.pdf"
    assert entry.payload.read_bytes() == b"hello"
    assert [e.id for e in store.list_entries()] == [entry.id]

    restored = store.restore(entry.id)

    assert restored == doc
    assert doc.read_bytes() == b"hello"
    assert store.list_entries() == []


def test_restore_uses_conflict_name_when_target_exists(root, store):
    module = root / "Math"
    module.mkdir()
    doc = module / "lecture.pdf"
    doc.write_bytes(b"old")
    entry = store.move_to_trash(doc, "document")
    doc.write_bytes(b"new")

    restored = store.restore(entry.id)

    assert restored != doc
    assert "Konflikt" in restored.name
    assert restored.read_bytes() == b"old"
    assert doc.read_bytes() == b"new"


def test_move_module_folder_as_one_entry(root, store):
    module = root / "School" / "Math"
    module.mkdir(parents=True)
    (root / "School" / ".group").touch()
    (module / ".meta").write_text("{}", encoding="utf-8")
    (module / "lecture.pdf").write_bytes(b"x")

    entry = store.move_to_trash(module, "module")

    assert not module.exists()
    assert entry.kind == "module"
    assert (entry.payload / "lecture.pdf").exists()

    store.restore(entry.id)
    assert (module / "lecture.pdf").exists()


def test_restore_recreates_missing_group(root, store):
    module = root / "School" / "Math"
    module.mkdir(parents=True)
    (root / "School" / ".group").touch()
    (module / ".meta").write_text("{}", encoding="utf-8")
    entry = store.move_to_trash(module, "module")
    (root / "School" / ".group").unlink()
    (root / "School").rmdir()

    store.restore(entry.id)

    assert (root / "School" / ".group").exists()
    assert (module / ".meta").exists() or module.is_dir()


def test_restore_document_fails_when_module_is_gone(root, store):
    module = root / "Math"
    module.mkdir()
    doc = module / "lecture.pdf"
    doc.write_bytes(b"x")
    entry = store.move_to_trash(doc, "document")
    module.rmdir()

    with pytest.raises(TrashRestoreError):
        store.restore(entry.id)


def test_restore_document_reapplies_tags(root, store):
    module = root / "Math"
    module.mkdir()
    doc = module / "lecture.pdf"
    doc.write_bytes(b"x")
    entry = store.move_to_trash(doc, "document", doc_tags=["tag-1"])
    (module / ".doc_tags").write_text(json.dumps({}), encoding="utf-8")

    store.restore(entry.id)

    tags = json.loads((module / ".doc_tags").read_text(encoding="utf-8"))
    assert tags["lecture.pdf"] == ["tag-1"]


def test_adopt_file_into_module_entry_keeps_subpath(root, store):
    module = root / "School" / "Math"
    module.mkdir(parents=True)
    (root / "School" / ".group").touch()
    (module / ".meta").write_text("{}", encoding="utf-8")
    (module / "doc.pdf").write_bytes(b"data")
    entry = store.move_to_trash(module, "module")

    (root / "School" / "Math").mkdir(parents=True)
    (root / "School" / "Math" / "notes.pdf").write_bytes(b"notes")
    adopted, dest = store.move_into_entry(
        entry.id, root / "School" / "Math" / "notes.pdf"
    )

    assert adopted.id == entry.id
    assert dest == entry.payload / "notes.pdf"
    assert dest.read_bytes() == b"notes"
    assert not (root / "School" / "Math" / "notes.pdf").exists()


def test_delete_forever_and_empty(root, store):
    (root / "a.txt").write_bytes(b"a")
    (root / "b.txt").write_bytes(b"b")
    first = store.move_to_trash(root / "a.txt", "document")
    second = store.move_to_trash(root / "b.txt", "document")

    store.delete_forever(first.id)
    assert [e.id for e in store.list_entries()] == [second.id]

    assert store.empty() == 1
    assert store.list_entries() == []


def test_purge_older_than(root, store):
    (root / "a.txt").write_bytes(b"a")
    (root / "b.txt").write_bytes(b"b")
    old = store.move_to_trash(root / "a.txt", "document")
    fresh = store.move_to_trash(root / "b.txt", "document")
    meta_path = old.entry_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["deleted_at"] = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    removed = store.purge_older_than(30)

    assert removed == 1
    assert [e.id for e in store.list_entries()] == [fresh.id]


def test_trash_is_invisible_to_module_scanner(root, store):
    module_store = ModuleStore(root=root)
    module = root / "Math"
    module.mkdir()
    module_store.save_module(Module(title="Math", description=""))
    (module / "lecture.pdf").write_bytes(b"x")
    entry = store.move_to_trash(module, "module")

    assert module_store.load_all() == []
    assert entry.entry_dir.exists()


def test_recover_finishes_pending_entry(root, store):
    (root / "a.txt").write_bytes(b"a")
    entry = store.move_to_trash(root / "a.txt", "document")
    meta_path = entry.entry_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["state"] = "pending"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    store.recover()

    assert store.list_entries()[0].state == "ready"


def test_refuses_path_outside_root(root, store, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"x")

    with pytest.raises(TrashError):
        store.move_to_trash(outside, "document")


def test_unsafe_meta_path_is_ignored(root, store):
    (root / "a.txt").write_bytes(b"a")
    entry = store.move_to_trash(root / "a.txt", "document")
    meta_path = entry.entry_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["original_path"] = "../../evil.txt"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    assert store.list_entries() == []
    with pytest.raises(TrashError):
        store.get_entry(entry.id)


def test_refuses_to_restore_into_internal_folder(root, store):
    (root / "a.txt").write_bytes(b"a")
    entry = store.move_to_trash(root / "a.txt", "document")
    meta_path = entry.entry_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["original_path"] = ".trash/evil.txt"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    with pytest.raises(TrashError):
        store.restore(entry.id)


def test_module_store_delete_document_moves_to_trash(root):
    store = ModuleStore(root=root, device_id="d", device_name="Laptop")
    module = Module(title="Math", description="")
    store.save_module(module)
    path = root / "Math" / "lecture.pdf"
    path.write_bytes(b"x")
    (root / "Math" / ".doc_tags").write_text(
        json.dumps({"lecture.pdf": ["t1"]}), encoding="utf-8"
    )
    doc = Document(title="lecture", description="", filepath=str(path))
    module.documents.append(doc)

    store.delete_document(module, doc)

    assert not path.exists()
    entries = store.trash.list_entries()
    assert entries[0].kind == "document"
    assert entries[0].doc_tags == ["t1"]
    assert json.loads((root / "Math" / ".doc_tags").read_text(encoding="utf-8")) == {}
    assert module.documents == []
