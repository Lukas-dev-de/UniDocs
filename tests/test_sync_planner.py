"""Planner decision table, rename detection and trash reconciliation."""

import hashlib
from datetime import datetime, timezone

from sync.planner import plan_sync
from sync.types import FileState, LocalEntry, RemoteEntry

NOW = datetime(2026, 10, 27, 14, 30, 12, tzinfo=timezone.utc)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def local_file(rel, data=b"x", mtime_ns=1_000_000_000):
    return LocalEntry(
        rel,
        False,
        size=len(data),
        mtime_ns=mtime_ns,
        sha256=sha(data),
        md5=hashlib.md5(data).hexdigest(),
    )


def local_dir(rel):
    return LocalEntry(rel, True)


def remote_file(rel, data=b"x", mtime=100.0, hash_kind="sha256", with_hash=True):
    return RemoteEntry(
        rel,
        False,
        size=len(data),
        mtime=mtime,
        hash=sha(data) if with_hash else None,
        hash_kind=hash_kind if with_hash else None,
    )


def remote_dir(rel):
    return RemoteEntry(rel, True)


def base(rel, data=b"x", remote_mtime=100.0, kind="file"):
    if kind == "dir":
        return FileState(kind="dir")
    return FileState(
        kind="file",
        local_sha256=sha(data),
        local_md5=hashlib.md5(data).hexdigest(),
        local_size=len(data),
        local_mtime_ns=1_000_000_000,
        remote_hash=sha(data),
        remote_hash_kind="sha256",
        remote_size=len(data),
        remote_mtime=remote_mtime,
    )


def kinds(actions):
    return [(a.kind, a.rel_path, a.dest_rel) for a in actions]


def test_first_sync_uploads_downloads_records_and_conflicts():
    local = {"up.pdf": local_file("up.pdf", b"a"), "same.pdf": local_file("same.pdf", b"s")}
    remote = {
        "down.pdf": remote_file("down.pdf", b"d"),
        "same.pdf": remote_file("same.pdf", b"s"),
        "clash.pdf": remote_file("clash.pdf", b"remote"),
    }
    local["clash.pdf"] = local_file("clash.pdf", b"local")

    actions = plan_sync(local, remote, {}, provider_hash_kind="sha256",
                        device_name="Laptop", now=NOW)

    result = kinds(actions)
    assert ("upload", "up.pdf", "") in result
    assert ("download", "down.pdf", "") in result
    assert ("record", "same.pdf", "") in result
    conflict = [a for a in actions if a.kind == "conflict"][0]
    assert conflict.rel_path == "clash.pdf"
    assert "Konflikt Laptop-20261027-143012" in conflict.dest_rel


def test_unchanged_both_sides_is_record_only():
    actions = plan_sync(
        {"a.pdf": local_file("a.pdf")},
        {"a.pdf": remote_file("a.pdf")},
        {"a.pdf": base("a.pdf")},
    )
    assert kinds(actions) == [("record", "a.pdf", "")]


def test_one_side_changed_wins():
    actions = plan_sync(
        {"a.pdf": local_file("a.pdf", b"new")},
        {"a.pdf": remote_file("a.pdf", b"old")},
        {"a.pdf": base("a.pdf", b"old")},
    )
    assert ("upload", "a.pdf", "") in kinds(actions)

    actions = plan_sync(
        {"a.pdf": local_file("a.pdf", b"old")},
        {"a.pdf": remote_file("a.pdf", b"new")},
        {"a.pdf": base("a.pdf", b"old")},
    )
    assert ("download", "a.pdf", "") in kinds(actions)


def test_both_changed_same_content_converges_without_transfer():
    actions = plan_sync(
        {"a.pdf": local_file("a.pdf", b"new")},
        {"a.pdf": remote_file("a.pdf", b"new")},
        {"a.pdf": base("a.pdf", b"old")},
    )
    assert kinds(actions) == [("record", "a.pdf", "")]


def test_both_changed_differently_makes_conflict_copy():
    actions = plan_sync(
        {"a.pdf": local_file("a.pdf", b"local")},
        {"a.pdf": remote_file("a.pdf", b"remote")},
        {"a.pdf": base("a.pdf", b"old")},
        device_name="Laptop",
        now=NOW,
    )
    conflict = [a for a in actions if a.kind == "conflict"]
    assert len(conflict) == 1
    assert conflict[0].dest_rel.startswith("a (Konflikt Laptop-")


def test_local_delete_without_trash_copy_deletes_remote():
    actions = plan_sync(
        {},
        {"a.pdf": remote_file("a.pdf")},
        {"a.pdf": base("a.pdf")},
    )
    assert ("delete_remote", "a.pdf", "") in kinds(actions)


def test_local_delete_with_trash_moves_remote_into_entry():
    local = {
        ".trash/E/files/a.pdf": local_file(".trash/E/files/a.pdf"),
    }
    remote = {"a.pdf": remote_file("a.pdf")}
    state = {"a.pdf": base("a.pdf")}

    actions = plan_sync(local, remote, state, supports_move=True)

    moves = [a for a in actions if a.kind == "trash_remote_move"]
    assert len(moves) == 1
    assert moves[0].rel_path == "a.pdf"
    assert moves[0].dest_rel == ".trash/E/files/a.pdf"
    assert not [a for a in actions if a.kind == "upload" and "files/a.pdf" in a.rel_path]


def test_local_delete_without_move_support_deletes_remote_and_uploads_payload():
    local = {".trash/E/files/a.pdf": local_file(".trash/E/files/a.pdf")}
    remote = {"a.pdf": remote_file("a.pdf")}
    state = {"a.pdf": base("a.pdf")}

    actions = plan_sync(local, remote, state, supports_move=False)

    result = kinds(actions)
    assert ("delete_remote", "a.pdf", "") in result
    assert ("upload", ".trash/E/files/a.pdf", "") in result


def test_remote_delete_with_trash_adopts_local_copy():
    local = {"a.pdf": local_file("a.pdf")}
    remote = {".trash/E/files/a.pdf": remote_file(".trash/E/files/a.pdf")}
    state = {"a.pdf": base("a.pdf")}

    actions = plan_sync(local, remote, state)

    adopt = [a for a in actions if a.kind == "trash_local_adopt"]
    assert len(adopt) == 1
    assert adopt[0].rel_path == "a.pdf"
    assert adopt[0].entry_id == "E"
    assert not [a for a in actions if a.kind == "download" and a.rel_path.endswith("files/a.pdf")]


def test_remote_delete_without_trash_moves_local_copy_to_trash():
    actions = plan_sync(
        {"a.pdf": local_file("a.pdf")},
        {},
        {"a.pdf": base("a.pdf")},
    )
    assert ("trash_local_new", "a.pdf", "") in kinds(actions)


def test_trash_paths_are_deleted_as_files_not_folders():
    local = {".trash/E/files/a.pdf": local_file(".trash/E/files/a.pdf")}
    state = {".trash/E/files/a.pdf": base(".trash/E/files/a.pdf")}

    actions = plan_sync(local, {}, state)

    delete = [a for a in actions if a.kind == "delete_local"][0]
    assert delete.is_dir is False


def test_both_sides_missing_drops_state():
    actions = plan_sync({}, {}, {"a.pdf": base("a.pdf")})
    assert kinds(actions) == [("drop_state", "a.pdf", "")]


def test_local_file_rename_becomes_remote_move():
    actions = plan_sync(
        {"new.pdf": local_file("new.pdf")},
        {"old.pdf": remote_file("old.pdf")},
        {"old.pdf": base("old.pdf")},
        supports_move=True,
    )
    result = kinds(actions)
    assert ("move_remote", "old.pdf", "new.pdf") in result
    assert not [a for a in actions if a.kind in ("upload", "download")]


def test_remote_file_rename_becomes_local_move():
    actions = plan_sync(
        {"old.pdf": local_file("old.pdf")},
        {"new.pdf": remote_file("new.pdf")},
        {"old.pdf": base("old.pdf")},
        supports_move=True,
    )
    result = kinds(actions)
    assert ("move_local", "old.pdf", "new.pdf") in result
    assert not [a for a in actions if a.kind in ("upload", "download")]


def test_local_module_dir_rename_is_one_remote_move():
    local = {
        "New": local_dir("New"),
        "New/.meta": local_file("New/.meta", b"{}"),
        "New/a.pdf": local_file("New/a.pdf"),
    }
    remote = {
        "Old": remote_dir("Old"),
        "Old/.meta": remote_file("Old/.meta", b"{}"),
        "Old/a.pdf": remote_file("Old/a.pdf"),
    }
    state = {
        "Old": base("Old", kind="dir"),
        "Old/.meta": base("Old/.meta", b"{}"),
        "Old/a.pdf": base("Old/a.pdf"),
    }

    actions = plan_sync(local, remote, state, supports_move=True)

    moves = [a for a in actions if a.kind == "move_remote"]
    assert len(moves) == 1
    assert moves[0].rel_path == "Old"
    assert moves[0].dest_rel == "New"
    assert moves[0].is_dir
    assert not [
        a
        for a in actions
        if a.kind in ("upload", "delete_remote", "delete_local", "download")
    ]


def test_large_local_dir_rename_emits_only_one_move():
    local = {"New": local_dir("New")}
    remote = {"Old": remote_dir("Old")}
    state = {"Old": base("Old", kind="dir")}
    for index in range(30):
        rel = f"{index:02d}.pdf"
        local[f"New/{rel}"] = local_file(f"New/{rel}", data=rel.encode())
        remote[f"Old/{rel}"] = remote_file(f"Old/{rel}", data=rel.encode())
        state[f"Old/{rel}"] = base(f"Old/{rel}", data=rel.encode())

    actions = plan_sync(local, remote, state, supports_move=True)

    assert [a.kind for a in actions] == ["move_remote"]


def test_remote_module_dir_rename_is_one_local_move():
    local = {
        "Old": local_dir("Old"),
        "Old/.meta": local_file("Old/.meta", b"{}"),
        "Old/a.pdf": local_file("Old/a.pdf"),
    }
    remote = {
        "New": remote_dir("New"),
        "New/.meta": remote_file("New/.meta", b"{}"),
        "New/a.pdf": remote_file("New/a.pdf"),
    }
    state = {
        "Old": base("Old", kind="dir"),
        "Old/.meta": base("Old/.meta", b"{}"),
        "Old/a.pdf": base("Old/a.pdf"),
    }

    actions = plan_sync(local, remote, state, supports_move=True)

    moves = [a for a in actions if a.kind == "move_local"]
    assert len(moves) == 1
    assert moves[0].rel_path == "Old"
    assert moves[0].dest_rel == "New"
    assert not [
        a
        for a in actions
        if a.kind in ("upload", "delete_remote", "delete_local", "download", "mkdir_local")
    ]


def test_new_dirs_are_created_on_the_other_side():
    actions = plan_sync({"Empty": local_dir("Empty")}, {}, {})
    assert ("mkdir_remote", "Empty", "") in kinds(actions)

    actions = plan_sync({}, {"Empty": remote_dir("Empty")}, {})
    assert ("mkdir_local", "Empty", "") in kinds(actions)


def test_file_vs_dir_is_reported_not_deleted():
    actions = plan_sync(
        {"x": local_file("x")},
        {"x": remote_dir("x")},
        {},
    )
    assert [a.kind for a in actions] == ["type_conflict"]


def test_actions_are_ordered_mkdir_before_upload():
    actions = plan_sync(
        {"M": local_dir("M"), "M/a.pdf": local_file("M/a.pdf")},
        {},
        {},
    )
    assert [a.kind for a in actions] == ["mkdir_remote", "upload"]


def test_webdav_hashless_uses_size_and_mtime():
    local = {"a.pdf": local_file("a.pdf", b"x")}
    remote = {"a.pdf": remote_file("a.pdf", b"x", with_hash=False, mtime=1.0)}
    state = {
        "a.pdf": FileState(
            local_sha256=sha(b"x"),
            local_size=1,
            local_mtime_ns=1_000_000_000,
            remote_size=1,
            remote_mtime=1.0,
        )
    }

    actions = plan_sync(local, remote, state, provider_hash_kind=None)

    assert kinds(actions) == [("record", "a.pdf", "")]
