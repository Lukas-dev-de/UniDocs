"""Pure sync planning: compare local tree, remote tree and last state.

No network or filesystem writes happen here. The engine executes the returned
actions.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath

from app_storage.naming import conflict_name
from sync.types import FileState, LocalEntry, RemoteEntry, SyncAction

TRASH_PREFIX = ".trash/"
MTIME_TOLERANCE = 2.0


def plan_sync(
    local: dict[str, LocalEntry],
    remote: dict[str, RemoteEntry],
    state: dict[str, FileState],
    provider_hash_kind: str | None = None,
    supports_move: bool = True,
    device_name: str = "Device",
    now: datetime | None = None,
) -> list[SyncAction]:
    actions: list[SyncAction] = []
    handled: set[str] = set()
    used_conflicts: set[str] = set()

    dropped = _dedupe_trash(local, remote, provider_hash_kind, handled, actions)
    local_trash = _trash_payloads(local, exclude_ids=dropped)
    remote_trash = _trash_payloads(remote, exclude_ids=dropped)

    _plan_trash(
        local,
        remote,
        state,
        local_trash,
        remote_trash,
        provider_hash_kind,
        supports_move,
        handled,
        actions,
    )
    if supports_move:
        _plan_renames(local, remote, state, provider_hash_kind, handled, actions)

    for rel in sorted(set(local) | set(remote) | set(state)):
        if rel in handled or _under_handled(rel, handled):
            continue
        local_entry = local.get(rel)
        remote_entry = remote.get(rel)
        base = state.get(rel)

        if local_entry and remote_entry:
            if local_entry.is_dir != remote_entry.is_dir:
                actions.append(
                    SyncAction("type_conflict", rel_path=rel, note="file/folder mismatch")
                )
                continue
            if local_entry.is_dir:
                actions.append(SyncAction("record", rel_path=rel, is_dir=True))
                continue
            if base is None:
                if _local_equals_remote(local_entry, remote_entry, provider_hash_kind):
                    actions.append(SyncAction("record", rel_path=rel))
                else:
                    actions.append(
                        _conflict_action(
                            rel, local, remote, used_conflicts, device_name, now
                        )
                    )
                continue
            loc_changed = not _local_matches_base(local_entry, base)
            rem_changed = not _remote_matches_base(remote_entry, base, provider_hash_kind)
            if not loc_changed and not rem_changed:
                actions.append(SyncAction("record", rel_path=rel))
            elif loc_changed and not rem_changed:
                actions.append(SyncAction("upload", rel_path=rel))
            elif not loc_changed and rem_changed:
                actions.append(SyncAction("download", rel_path=rel))
            elif _local_equals_remote(local_entry, remote_entry, provider_hash_kind):
                actions.append(SyncAction("record", rel_path=rel))
            else:
                actions.append(
                    _conflict_action(rel, local, remote, used_conflicts, device_name, now)
                )
            continue

        if local_entry and not remote_entry:
            if local_entry.is_dir:
                if base is None:
                    actions.append(SyncAction("mkdir_remote", rel_path=rel, is_dir=True))
                elif rel.startswith(TRASH_PREFIX):
                    actions.append(SyncAction("delete_local", rel_path=rel, is_dir=True))
                elif _local_subtree_unchanged(local, state, rel) and not any(
                    original == rel or original.startswith(rel + "/")
                    for original in remote_trash
                ):
                    actions.append(SyncAction("trash_local_new", rel_path=rel, is_dir=True))
                    _mark_subtree(handled, local, rel)
                else:
                    # Children decide; this only removes an empty leftover
                    # folder after adoptions/deletions.
                    actions.append(SyncAction("delete_local", rel_path=rel, is_dir=True))
                continue
            if base is None:
                actions.append(SyncAction("upload", rel_path=rel))
                continue
            if not _local_matches_base(local_entry, base):
                actions.append(SyncAction("upload", rel_path=rel))  # edit wins
            elif rel.startswith(TRASH_PREFIX):
                actions.append(SyncAction("delete_local", rel_path=rel))
            elif rel in remote_trash:
                entry_id = remote_trash[rel][0]
                actions.append(
                    SyncAction("trash_local_adopt", rel_path=rel, entry_id=entry_id)
                )
                handled.add(remote_trash[rel][1])
            else:
                # Remote deleted it outside the app: keep a local trash copy.
                actions.append(SyncAction("trash_local_new", rel_path=rel))
            continue

        if remote_entry and not local_entry:
            if remote_entry.is_dir:
                if base is None:
                    actions.append(SyncAction("mkdir_local", rel_path=rel, is_dir=True))
                else:
                    actions.append(SyncAction("delete_remote", rel_path=rel, is_dir=True))
                continue
            if base is None:
                actions.append(SyncAction("download", rel_path=rel))
                continue
            if not _remote_matches_base(remote_entry, base, provider_hash_kind):
                actions.append(SyncAction("download", rel_path=rel))  # edit wins
            elif rel.startswith(TRASH_PREFIX):
                actions.append(SyncAction("delete_remote", rel_path=rel))
            elif rel in local_trash:
                entry_id, payload_rel, payload_entry = local_trash[rel]
                if supports_move and payload_entry.sha256 == base.local_sha256:
                    actions.append(
                        SyncAction(
                            "trash_remote_move",
                            rel_path=rel,
                            dest_rel=payload_rel,
                            entry_id=entry_id,
                        )
                    )
                    handled.add(payload_rel)
                else:
                    actions.append(SyncAction("delete_remote", rel_path=rel))
            else:
                # Deleted outside the app: no local trash copy to preserve.
                actions.append(SyncAction("delete_remote", rel_path=rel))
            continue

        # Neither side has it but the state remembers it.
        if base is not None:
            actions.append(SyncAction("drop_state", rel_path=rel))

    return _order_actions(actions)


# -- trash pre-pass -----------------------------------------------------------


def _trash_payloads(
    entries: dict[str, LocalEntry] | dict[str, RemoteEntry],
    exclude_ids: set[str] | None = None,
) -> dict[str, tuple[str, str, object]]:
    """Map original path -> (entry id, payload rel path, entry)."""
    found: dict[str, tuple[str, str, object]] = {}
    exclude_ids = exclude_ids or set()
    for rel, entry in entries.items():
        if not rel.startswith(TRASH_PREFIX):
            continue
        parts = PurePosixPath(rel).parts
        if len(parts) < 4 or parts[2] != "files":
            continue
        entry_id = parts[1]
        if entry_id in exclude_ids:
            continue
        original = "/".join(parts[3:])
        if original and original not in found:
            found[original] = (entry_id, rel, entry)
    return found


def _trash_entries(
    entries: dict[str, LocalEntry] | dict[str, RemoteEntry],
) -> dict[str, dict[str, object]]:
    """entry id -> {original path: payload entry} for files and folders."""
    result: dict[str, dict[str, object]] = {}
    for rel, entry in entries.items():
        if not rel.startswith(TRASH_PREFIX):
            continue
        parts = PurePosixPath(rel).parts
        if len(parts) < 4 or parts[2] != "files":
            continue
        entry_id = parts[1]
        original = "/".join(parts[3:])
        result.setdefault(entry_id, {})[original] = entry
    return result


def _dedupe_trash(
    local: dict[str, LocalEntry],
    remote: dict[str, RemoteEntry],
    provider_hash_kind: str | None,
    handled: set[str],
    actions: list[SyncAction],
) -> set[str]:
    """Drop duplicate entries for the same deleted content (hashes only).

    Two devices that delete the same file offline create one entry each. If
    both entries carry identical payloads, keep the lexicographically smaller
    id and hard-delete the other entry on both sides.
    """
    local_entries = _trash_entries(local)
    remote_entries = _trash_entries(remote)
    dropped: set[str] = set()
    for local_id, local_payloads in sorted(local_entries.items()):
        for remote_id, remote_payloads in sorted(remote_entries.items()):
            if local_id == remote_id:
                continue
            if local_id in dropped or remote_id in dropped:
                continue
            if not _same_trash_payloads(
                local_payloads, remote_payloads, provider_hash_kind
            ):
                continue
            dropped.add(max(local_id, remote_id))
    for loser in dropped:
        prefix = f".trash/{loser}/"
        for rel in list(local):
            if rel.startswith(prefix):
                actions.append(
                    SyncAction(
                        "delete_local", rel_path=rel, is_dir=local[rel].is_dir
                    )
                )
                handled.add(rel)
        for rel in list(remote):
            if rel.startswith(prefix):
                actions.append(
                    SyncAction(
                        "delete_remote", rel_path=rel, is_dir=remote[rel].is_dir
                    )
                )
                handled.add(rel)
    return dropped


def _same_trash_payloads(
    local_payloads: dict[str, object],
    remote_payloads: dict[str, object],
    provider_hash_kind: str | None,
) -> bool:
    local_files = {
        rel: entry
        for rel, entry in local_payloads.items()
        if not getattr(entry, "is_dir", False)
    }
    remote_files = {
        rel: entry
        for rel, entry in remote_payloads.items()
        if not getattr(entry, "is_dir", False)
    }
    if not local_files or set(local_files) != set(remote_files):
        return False
    for rel, local_entry in local_files.items():
        remote_entry = remote_files[rel]
        remote_hash = getattr(remote_entry, "hash", None)
        hash_kind = getattr(remote_entry, "hash_kind", None) or provider_hash_kind
        if not remote_hash:
            return False
        if hash_kind == "md5":
            if getattr(local_entry, "md5", None) != remote_hash:
                return False
        elif hash_kind == "sha256":
            if getattr(local_entry, "sha256", None) != remote_hash:
                return False
        else:
            return False
    return True


def _plan_trash(
    local: dict[str, LocalEntry],
    remote: dict[str, RemoteEntry],
    state: dict[str, FileState],
    local_trash: dict[str, tuple[str, str, object]],
    remote_trash: dict[str, tuple[str, str, object]],
    provider_hash_kind: str | None,
    supports_move: bool,
    handled: set[str],
    actions: list[SyncAction],
) -> None:
    # Local delete: move the unchanged remote file into the same trash entry.
    if supports_move:
        for original, (entry_id, payload_rel, payload) in local_trash.items():
            base = state.get(original)
            if (
                base is None
                or base.kind != "file"
                or original in local
                or original not in remote
                or original.startswith(TRASH_PREFIX)
            ):
                continue
            if not _remote_matches_base(remote[original], base, provider_hash_kind):
                continue
            if not isinstance(payload, LocalEntry) or payload.sha256 != base.local_sha256:
                continue
            actions.append(
                SyncAction(
                    "trash_remote_move",
                    rel_path=original,
                    dest_rel=payload_rel,
                    entry_id=entry_id,
                )
            )
            handled.add(original)
            handled.add(payload_rel)

    # Remote delete: adopt the local unchanged file into the remote entry.
    for original, (entry_id, payload_rel, _payload) in remote_trash.items():
        base = state.get(original)
        if (
            base is None
            or original not in local
            or original in remote
            or original.startswith(TRASH_PREFIX)
        ):
            continue
        if local[original].is_dir or base.kind != "file":
            continue
        if not _local_matches_base(local[original], base):
            continue  # local edit wins
        actions.append(
            SyncAction("trash_local_adopt", rel_path=original, entry_id=entry_id)
        )
        handled.add(original)
        handled.add(payload_rel)


# -- rename pre-pass ----------------------------------------------------------


def _plan_renames(
    local: dict[str, LocalEntry],
    remote: dict[str, RemoteEntry],
    state: dict[str, FileState],
    provider_hash_kind: str | None,
    handled: set[str],
    actions: list[SyncAction],
) -> None:
    # Directories first: a module/group rename must not degrade into one file
    # move per document.
    renamed_remote_dirs: set[str] = set()
    new_local_dirs = [
        rel
        for rel, entry in local.items()
        if entry.is_dir and rel not in state and rel not in remote
    ]
    for old, base in sorted(state.items()):
        if base.kind != "dir" or old in local:
            continue
        if old.startswith(TRASH_PREFIX) or _is_handled(old, handled):
            continue
        remote_old = remote.get(old)
        if remote_old is None or not remote_old.is_dir:
            continue
        if not _remote_subtree_unchanged(remote, state, old, provider_hash_kind):
            continue
        base_fp = _local_dir_fingerprint(state, old)
        if not base_fp:
            continue
        candidates = [
            new
            for new in new_local_dirs
            if new not in renamed_remote_dirs
            and new != old
            and not new.startswith(TRASH_PREFIX)
            and not _is_handled(new, handled)
            and not new.startswith(old + "/")
            and not old.startswith(new + "/")
            and _local_dir_fingerprint(local, new) == base_fp
        ]
        if len(candidates) != 1:
            continue
        new = candidates[0]
        actions.append(SyncAction("move_remote", rel_path=old, dest_rel=new, is_dir=True))
        _mark_subtree(handled, remote, old)
        _mark_subtree(handled, local, new)
        renamed_remote_dirs.add(new)

    new_remote_dirs = [
        rel
        for rel, entry in remote.items()
        if entry.is_dir and rel not in state and rel not in local
    ]
    renamed_local_dirs: set[str] = set()
    for old, base in sorted(state.items()):
        if base.kind != "dir" or old in remote:
            continue
        if old.startswith(TRASH_PREFIX) or _is_handled(old, handled):
            continue
        local_old = local.get(old)
        if local_old is None or not local_old.is_dir:
            continue
        if not _local_subtree_unchanged(local, state, old):
            continue
        base_fp = _remote_dir_fingerprint(state, old)
        if not base_fp:
            continue
        candidates = [
            new
            for new in new_remote_dirs
            if new not in renamed_local_dirs
            and new != old
            and not new.startswith(TRASH_PREFIX)
            and not _is_handled(new, handled)
            and not new.startswith(old + "/")
            and not old.startswith(new + "/")
            and _remote_dir_fingerprint(remote, new) == base_fp
        ]
        if len(candidates) != 1:
            continue
        new = candidates[0]
        actions.append(SyncAction("move_local", rel_path=old, dest_rel=new, is_dir=True))
        _mark_subtree(handled, local, old)
        _mark_subtree(handled, remote, new)
        renamed_local_dirs.add(new)

    # Local file rename: remote still has the old path, local has the new one.
    moved_local: set[str] = set()
    new_local = {
        rel: entry
        for rel, entry in local.items()
        if not entry.is_dir
        and rel not in state
        and rel not in remote
        and not rel.startswith(TRASH_PREFIX)
        and not _is_handled(rel, handled)
    }
    for old, base in sorted(state.items()):
        if base.kind != "file" or old in local or old in moved_local:
            continue
        if old.startswith(TRASH_PREFIX) or _is_handled(old, handled):
            continue
        remote_old = remote.get(old)
        if remote_old is None or remote_old.is_dir:
            continue
        if not _remote_matches_base(remote_old, base, provider_hash_kind):
            continue
        matches = [
            rel
            for rel, entry in new_local.items()
            if rel not in moved_local and entry.sha256 and entry.sha256 == base.local_sha256
        ]
        if len(matches) != 1:
            continue
        new = matches[0]
        actions.append(SyncAction("move_remote", rel_path=old, dest_rel=new))
        handled.update((old, new))
        moved_local.add(new)

    # Remote file rename: local still has the old path, remote has the new one.
    new_remote = {
        rel: entry
        for rel, entry in remote.items()
        if not entry.is_dir
        and rel not in state
        and rel not in local
        and not rel.startswith(TRASH_PREFIX)
        and not _is_handled(rel, handled)
    }
    moved_remote: set[str] = set()
    for old, base in sorted(state.items()):
        if base.kind != "file" or old in remote or old in moved_remote:
            continue
        if old.startswith(TRASH_PREFIX) or _is_handled(old, handled):
            continue
        local_old = local.get(old)
        if local_old is None or local_old.is_dir:
            continue
        if not _local_matches_base(local_old, base):
            continue
        matches = [
            rel
            for rel, entry in new_remote.items()
            if rel not in moved_remote and _remote_hash_matches(entry, base)
        ]
        if len(matches) != 1:
            continue
        new = matches[0]
        actions.append(SyncAction("move_local", rel_path=old, dest_rel=new))
        handled.update((old, new))
        moved_remote.add(new)


def _remote_subtree_unchanged(
    remote: dict[str, RemoteEntry],
    state: dict[str, FileState],
    prefix: str,
    provider_hash_kind: str | None,
) -> bool:
    for rel, base in state.items():
        if not rel.startswith(prefix + "/"):
            continue
        entry = remote.get(rel)
        if entry is None or not _remote_matches_base(entry, base, provider_hash_kind):
            return False
    return True


def _local_subtree_unchanged(
    local: dict[str, LocalEntry], state: dict[str, FileState], prefix: str
) -> bool:
    for rel, base in state.items():
        if not rel.startswith(prefix + "/"):
            continue
        entry = local.get(rel)
        if entry is None or not _local_matches_base(entry, base):
            return False
    return True


def _local_dir_fingerprint(
    entries: dict[str, LocalEntry] | dict[str, FileState], prefix: str
) -> tuple[tuple[str, str | None], ...]:
    out = []
    for rel, entry in entries.items():
        if not rel.startswith(prefix + "/"):
            continue
        if isinstance(entry, LocalEntry):
            if entry.is_dir:
                continue
            out.append((rel[len(prefix) + 1 :], entry.sha256))
        else:
            if entry.kind == "dir":
                continue
            out.append((rel[len(prefix) + 1 :], entry.local_sha256))
    return tuple(sorted(out))


def _remote_dir_fingerprint(
    entries: dict[str, RemoteEntry] | dict[str, FileState], prefix: str
) -> tuple[tuple[str, str | None], ...]:
    out = []
    for rel, entry in entries.items():
        if not rel.startswith(prefix + "/"):
            continue
        if isinstance(entry, RemoteEntry):
            if entry.is_dir:
                continue
            value = entry.hash if entry.hash else f"{entry.size}:{entry.mtime:.0f}"
            out.append((rel[len(prefix) + 1 :], value))
        else:
            if entry.kind == "dir":
                continue
            value = (
                entry.remote_hash
                if entry.remote_hash
                else f"{entry.remote_size}:{entry.remote_mtime:.0f}"
            )
            out.append((rel[len(prefix) + 1 :], value))
    return tuple(sorted(out))


def _mark_subtree(handled: set[str], entries: dict, prefix: str) -> None:
    for rel in entries:
        if rel == prefix or rel.startswith(prefix + "/"):
            handled.add(rel)


# -- comparison helpers -------------------------------------------------------


def _local_matches_base(entry: LocalEntry, base: FileState) -> bool:
    if entry.is_dir:
        return base.kind == "dir"
    if base.kind != "file":
        return False
    if base.local_sha256 and entry.sha256:
        return entry.sha256 == base.local_sha256
    return entry.size == base.local_size and entry.mtime_ns == base.local_mtime_ns


def _remote_matches_base(
    entry: RemoteEntry, base: FileState, provider_hash_kind: str | None
) -> bool:
    if entry.is_dir:
        return base.kind == "dir"
    if base.kind != "file":
        return False
    if entry.hash and base.remote_hash:
        kind = entry.hash_kind or provider_hash_kind
        return entry.hash == base.remote_hash and kind == (base.remote_hash_kind or kind)
    if entry.size != base.remote_size:
        return False
    if not entry.mtime or not base.remote_mtime:
        return True
    return abs(entry.mtime - base.remote_mtime) <= MTIME_TOLERANCE


def _remote_hash_matches(entry: RemoteEntry, base: FileState) -> bool:
    if not entry.hash or not base.remote_hash:
        return False
    return entry.hash == base.remote_hash and (
        entry.hash_kind is None
        or base.remote_hash_kind is None
        or entry.hash_kind == base.remote_hash_kind
    )


def _local_equals_remote(
    local: LocalEntry, remote: RemoteEntry, provider_hash_kind: str | None
) -> bool:
    if local.is_dir or remote.is_dir:
        return local.is_dir and remote.is_dir
    if local.size != remote.size:
        return False
    if remote.hash and remote.hash_kind == "md5" and local.md5:
        return local.md5 == remote.hash
    if remote.hash and remote.hash_kind == "sha256" and local.sha256:
        return local.sha256 == remote.hash
    if remote.hash and provider_hash_kind == "md5" and local.md5:
        return local.md5 == remote.hash
    if remote.hash and provider_hash_kind == "sha256" and local.sha256:
        return local.sha256 == remote.hash
    if remote.mtime and local.mtime_ns:
        return abs(remote.mtime - local.mtime_ns / 1_000_000_000) <= MTIME_TOLERANCE
    return False


# -- conflicts ----------------------------------------------------------------


def _conflict_action(
    rel: str,
    local: dict[str, LocalEntry],
    remote: dict[str, RemoteEntry],
    used: set[str],
    device_name: str,
    now: datetime | None,
) -> SyncAction:
    path = PurePosixPath(rel)
    counter = 0
    while True:
        name = conflict_name(path.name, device_name, now, counter)
        candidate = str(path.with_name(name))
        if (
            candidate not in local
            and candidate not in remote
            and candidate not in used
        ):
            used.add(candidate)
            return SyncAction("conflict", rel_path=rel, dest_rel=candidate)
        counter += 1


def _is_handled(rel: str, handled: set[str]) -> bool:
    return rel in handled or any(rel.startswith(prefix + "/") for prefix in handled)


def _under_handled(rel: str, handled: set[str]) -> bool:
    return any(rel.startswith(prefix + "/") for prefix in handled)


# -- ordering -----------------------------------------------------------------


_PHASE = {
    "mkdir_local": 0,
    "mkdir_remote": 0,
    "download": 1,
    "record": 2,
    "trash_local_adopt": 3,
    "trash_local_new": 3,
    "move_local": 4,
    "move_remote": 4,
    "trash_remote_move": 4,
    "upload": 5,
    "conflict": 6,
    "delete_remote": 7,
    "delete_local": 8,
    "drop_state": 9,
    "type_conflict": 10,
}


def _order_actions(actions: list[SyncAction]) -> list[SyncAction]:
    def key(action: SyncAction):
        phase = _PHASE.get(action.kind, 10)
        if action.kind in ("delete_local", "delete_remote"):
            # Files before their parent folders, deepest folder first.
            return (
                phase,
                1 if action.is_dir else 0,
                -action.rel_path.count("/") if action.is_dir else 0,
                action.rel_path,
            )
        return (phase, 0, 0, action.rel_path)

    return sorted(actions, key=key)
