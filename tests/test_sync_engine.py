"""End-to-end engine tests with two local devices and one fake remote."""

import threading

from app_storage.trash_store import TrashStore
from sync.engine import SyncEngine
from sync.state import SyncState
from fake_provider import FakeProvider


def make_engine(root, provider, state_path, device, cancel=None):
    state = SyncState("fake", root, path=state_path).load()
    return SyncEngine(
        provider,
        root,
        state,
        device_name=device,
        cancel_event=cancel,
    )


def sync(root, provider, state_path, device="Device", cancel=None):
    return make_engine(root, provider, state_path, device, cancel).run()


def write(root, rel, data=b"x"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_two_devices_converge(tmp_path):
    provider = FakeProvider()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    write(a, "Math/.meta", b"{}")
    write(a, "Math/lecture.pdf", b"pdf")

    first = sync(a, provider, tmp_path / "state-a", "Laptop")
    second = sync(b, provider, tmp_path / "state-b", "PC")

    assert not first.errors and not second.errors
    assert (b / "Math/lecture.pdf").read_bytes() == b"pdf"
    assert (b / "Math/.meta").read_bytes() == b"{}"


def test_second_sync_is_noop(tmp_path):
    provider = FakeProvider()
    a = tmp_path / "a"
    a.mkdir()
    write(a, "a.pdf", b"x")
    sync(a, provider, tmp_path / "s")

    provider.uploads = provider.downloads = provider.moves = 0
    report = sync(a, provider, tmp_path / "s")

    assert report.changed == 0
    assert provider.uploads == provider.downloads == provider.moves == 0


def test_conflict_keeps_both_versions_on_both_devices(tmp_path):
    provider = FakeProvider()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    write(a, "doc.pdf", b"base")
    sync(a, provider, tmp_path / "sa", "Laptop")
    sync(b, provider, tmp_path / "sb", "PC")

    write(a, "doc.pdf", b"from-laptop")
    write(b, "doc.pdf", b"from-pc")
    sync(a, provider, tmp_path / "sa", "Laptop")
    report = sync(b, provider, tmp_path / "sb", "PC")
    sync(a, provider, tmp_path / "sa", "Laptop")

    assert report.conflicts == 1
    a_files = sorted(p.name for p in a.iterdir())
    b_files = sorted(p.name for p in b.iterdir())
    assert "doc.pdf" in a_files and "doc.pdf" in b_files
    assert any("Konflikt" in name for name in a_files)
    assert any("Konflikt" in name for name in b_files)
    assert (a / "doc.pdf").read_bytes() == b"from-pc"
    assert (b / "doc.pdf").read_bytes() == b"from-pc"


def test_delete_propagates_through_trash_without_duplicate_entry(tmp_path):
    provider = FakeProvider()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    write(a, "Math/doc.pdf", b"data")
    (a / "Math/.meta").write_text("{}", encoding="utf-8")
    sync(a, provider, tmp_path / "sa", "Laptop")
    sync(b, provider, tmp_path / "sb", "PC")

    TrashStore(a, device_name="Laptop").move_to_trash(a / "Math/doc.pdf", "document")
    report_a = sync(a, provider, tmp_path / "sa", "Laptop")
    report_b = sync(b, provider, tmp_path / "sb", "PC")

    assert not report_a.errors and not report_b.errors
    assert not (b / "Math/doc.pdf").exists()
    trash_b = TrashStore(b, device_name="PC").list_entries()
    assert len(trash_b) == 1
    assert trash_b[0].payload.read_bytes() == b"data"
    assert report_b.trashed == 1


def test_restore_propagates_and_removes_trash_entry_everywhere(tmp_path):
    provider = FakeProvider()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    write(a, "Math/doc.pdf", b"data")
    (a / "Math/.meta").write_text("{}", encoding="utf-8")
    sync(a, provider, tmp_path / "sa", "Laptop")
    sync(b, provider, tmp_path / "sb", "PC")
    TrashStore(a, device_name="Laptop").move_to_trash(a / "Math/doc.pdf", "document")
    sync(a, provider, tmp_path / "sa", "Laptop")
    sync(b, provider, tmp_path / "sb", "PC")

    trash_b = TrashStore(b, device_name="PC")
    trash_b.restore(trash_b.list_entries()[0].id)
    sync(b, provider, tmp_path / "sb", "PC")
    sync(a, provider, tmp_path / "sa", "Laptop")
    sync(b, provider, tmp_path / "sb", "PC")

    assert (a / "Math/doc.pdf").read_bytes() == b"data"
    assert (b / "Math/doc.pdf").read_bytes() == b"data"
    assert TrashStore(a).list_entries() == []
    assert TrashStore(b).list_entries() == []


def test_module_delete_and_restore_propagates_as_one_trash_entry(tmp_path):
    provider = FakeProvider()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    write(a, "Math/.meta", b"{}")
    write(a, "Math/doc.pdf", b"data")
    sync(a, provider, tmp_path / "sa", "Laptop")
    sync(b, provider, tmp_path / "sb", "PC")

    TrashStore(a, device_name="Laptop").move_to_trash(a / "Math", "module")
    report_a = sync(a, provider, tmp_path / "sa", "Laptop")
    report_b = sync(b, provider, tmp_path / "sb", "PC")

    assert not report_a.errors and not report_b.errors
    assert not (b / "Math").exists()
    entries = TrashStore(b, device_name="PC").list_entries()
    assert len(entries) == 1
    assert entries[0].kind == "module"
    assert (entries[0].payload / "doc.pdf").read_bytes() == b"data"

    TrashStore(b, device_name="PC").restore(entries[0].id)
    sync(b, provider, tmp_path / "sb", "PC")
    sync(a, provider, tmp_path / "sa", "Laptop")
    sync(b, provider, tmp_path / "sb", "PC")

    assert (a / "Math/doc.pdf").read_bytes() == b"data"
    assert (b / "Math/doc.pdf").read_bytes() == b"data"
    assert TrashStore(a).list_entries() == []
    assert TrashStore(b).list_entries() == []


def test_external_remote_delete_moves_local_copy_to_trash(tmp_path):
    provider = FakeProvider()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    write(a, "a.pdf", b"data")
    write(a, "keep.pdf", b"keep")
    sync(a, provider, tmp_path / "sa", "Laptop")
    sync(b, provider, tmp_path / "sb", "PC")

    provider.files.pop("a.pdf")
    report_a = sync(a, provider, tmp_path / "sa", "Laptop")
    assert not report_a.errors
    assert not (a / "a.pdf").exists()
    assert len(TrashStore(a).list_entries()) == 1

    sync(a, provider, tmp_path / "sa", "Laptop")  # publish the new trash entry
    report_b = sync(b, provider, tmp_path / "sb", "PC")
    assert not report_b.errors
    assert not (b / "a.pdf").exists()
    entries = TrashStore(b).list_entries()
    assert len(entries) == 1
    assert entries[0].payload.read_bytes() == b"data"


def test_upload_after_remote_delete_does_not_send_stale_etag(tmp_path):
    provider = FakeProvider()
    a = tmp_path / "a"
    a.mkdir()
    write(a, "a.pdf", b"one")
    write(a, "keep.pdf", b"keep")
    sync(a, provider, tmp_path / "sa", "Laptop")
    provider.files.pop("a.pdf")
    write(a, "a.pdf", b"two")

    report = sync(a, provider, tmp_path / "sa", "Laptop")

    assert not report.errors
    assert provider.upload_etags["a.pdf"] is None
    assert provider.files["a.pdf"] == b"two"


def test_two_offline_deletes_collapse_to_one_trash_entry(tmp_path):
    provider = FakeProvider()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    write(a, "doc.pdf", b"data")
    sync(a, provider, tmp_path / "sa", "Laptop")
    sync(b, provider, tmp_path / "sb", "PC")

    TrashStore(a, device_name="Laptop").move_to_trash(a / "doc.pdf", "document")
    TrashStore(b, device_name="PC").move_to_trash(b / "doc.pdf", "document")
    sync(a, provider, tmp_path / "sa", "Laptop")
    sync(b, provider, tmp_path / "sb", "PC")
    sync(a, provider, tmp_path / "sa", "Laptop")
    sync(b, provider, tmp_path / "sb", "PC")

    assert len(TrashStore(a).list_entries()) == 1
    assert len(TrashStore(b).list_entries()) == 1
    assert TrashStore(a).list_entries()[0].payload.read_bytes() == b"data"


def test_edit_during_download_is_not_overwritten(tmp_path):
    provider = FakeProvider()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    write(a, "doc.pdf", b"base")
    sync(a, provider, tmp_path / "sa", "Laptop")
    sync(b, provider, tmp_path / "sb", "PC")
    write(b, "doc.pdf", b"remote-edit")
    sync(b, provider, tmp_path / "sb", "PC")

    provider.download_hook = lambda rel: write(a, "doc.pdf", b"local-edit")
    report = sync(a, provider, tmp_path / "sa", "Laptop")
    provider.download_hook = None

    assert report.errors
    assert (a / "doc.pdf").read_bytes() == b"local-edit"

    report = sync(a, provider, tmp_path / "sa", "Laptop")
    assert report.conflicts == 1
    assert (a / "doc.pdf").read_bytes() == b"local-edit"
    assert any("Konflikt" in path.name for path in a.iterdir())


def test_module_rename_uses_remote_move(tmp_path):
    provider = FakeProvider()
    a = tmp_path / "a"
    a.mkdir()
    write(a, "Math/.meta", b"{}")
    write(a, "Math/doc.pdf", b"data")
    sync(a, provider, tmp_path / "sa", "Laptop")
    provider.uploads = 0
    provider.moves = 0

    (a / "Math").rename(a / "Mathe")
    report = sync(a, provider, tmp_path / "sa", "Laptop")

    assert not report.errors
    assert provider.moves >= 1
    assert provider.uploads == 0
    assert "Mathe/doc.pdf" in provider.files
    assert "Math/doc.pdf" not in provider.files


def test_aborts_when_remote_turns_empty_after_prior_sync(tmp_path):
    provider = FakeProvider()
    a = tmp_path / "a"
    a.mkdir()
    write(a, "doc.pdf", b"data")
    sync(a, provider, tmp_path / "sa")
    provider.files.clear()
    provider.dirs.clear()

    report = sync(a, provider, tmp_path / "sa")

    assert report.aborted
    assert (a / "doc.pdf").exists()


def test_listing_failure_aborts_without_changes(tmp_path):
    provider = FakeProvider()
    a = tmp_path / "a"
    a.mkdir()
    write(a, "doc.pdf", b"data")
    provider.fail_list = True

    report = sync(a, provider, tmp_path / "sa")

    assert report.aborted
    assert provider.files == {}
    assert (a / "doc.pdf").exists()


def test_cancellation_stops_before_actions(tmp_path):
    provider = FakeProvider()
    a = tmp_path / "a"
    a.mkdir()
    write(a, "doc.pdf", b"data")
    cancel = threading.Event()
    cancel.set()

    report = sync(a, provider, tmp_path / "sa", cancel=cancel)

    assert report.cancelled
    assert provider.files == {}


def test_upload_errors_are_collected_and_other_actions_continue(tmp_path):
    provider = FakeProvider()
    provider.fail_uploads = True
    a = tmp_path / "a"
    a.mkdir()
    write(a, "one.pdf", b"1")
    write(a, "two.pdf", b"2")

    report = sync(a, provider, tmp_path / "sa")

    assert not report.aborted
    assert len(report.errors) == 2
    assert (a / "one.pdf").exists() and (a / "two.pdf").exists()
