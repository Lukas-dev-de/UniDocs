"""Google Drive provider against an in-memory Drive service."""

import hashlib
import re
from pathlib import Path

import pytest

from app_storage.trash_store import TrashStore
from sync.base import SyncAuthError, SyncNotFoundError
from sync.engine import SyncEngine
from sync.gdrive import (
    FOLDER_MIME,
    GDriveProvider,
    load_credentials,
    resolve_client_secret,
)
from sync.state import SyncState

MD5_FIELDS = ("id", "name", "mimeType", "size", "modifiedTime", "md5Checksum", "parents", "trashed")


class FakeHttpError(Exception):
    def __init__(self, status):
        self.status_code = status
        super().__init__(f"HTTP {status}")


class FakeRequest:
    def __init__(self, value, drive=None):
        self.value = value
        self.headers = {}
        self.drive = drive

    def execute(self):
        if self.drive is not None:
            self.drive.last_headers = dict(self.headers)
        return self.value


class FakeDrive:
    def __init__(self):
        self.items = {
            "root": {
                "id": "root",
                "name": "My Drive",
                "mimeType": FOLDER_MIME,
                "parents": [],
                "trashed": False,
            }
        }
        self.counter = 0
        self.fail_status = None
        self.page_size = 1000
        self.closed = False
        self.last_headers = {}

    def next_id(self):
        self.counter += 1
        return f"id{self.counter}"

    def about(self):
        return FakeAbout(self)

    def files(self):
        return FakeFiles(self)

    def close(self):
        self.closed = True

    def _mkfile(self, name, mime, parent, data=b""):
        ident = self.next_id()
        self.items[ident] = {
            "id": ident,
            "name": name,
            "mimeType": mime,
            "parents": [parent],
            "size": len(data),
            "md5Checksum": hashlib.md5(data).hexdigest() if data else None,
            "modifiedTime": "2026-10-27T14:00:00Z",
            "trashed": False,
            "_data": data,
        }
        return self.items[ident]

    def query(self, q, page_token=None):
        if self.fail_status:
            raise FakeHttpError(self.fail_status)
        parent = re.search(r"'([^']+)' in parents", q).group(1)
        name_match = re.search(r"name = '((?:\\.|[^'])*)'", q)
        name = name_match.group(1).replace("\\'", "'") if name_match else None
        want_folder = f"mimeType = '{FOLDER_MIME}'" in q
        not_folder = f"mimeType != '{FOLDER_MIME}'" in q
        matches = []
        for item in self.items.values():
            if item["id"] == "root" or item.get("trashed"):
                continue
            if parent not in item.get("parents", []):
                continue
            if name is not None and item["name"] != name:
                continue
            if want_folder and item["mimeType"] != FOLDER_MIME:
                continue
            if not_folder and item["mimeType"] == FOLDER_MIME:
                continue
            matches.append(item)
        matches.sort(key=lambda item: item["id"])
        start = int(page_token or 0)
        page = matches[start : start + self.page_size]
        token = str(start + self.page_size) if start + self.page_size < len(matches) else None
        return page, token

    def public(self, item):
        return {key: item.get(key) for key in MD5_FIELDS if key in item}


class FakeAbout:
    def __init__(self, drive):
        self.drive = drive

    def get(self, **kwargs):
        return FakeRequest({"user": {"emailAddress": "test@example.com"}}, self.drive)


class FakeFiles:
    def __init__(self, drive):
        self.drive = drive

    def get(self, fileId, fields=None, **kwargs):
        if fileId not in self.drive.items:
            raise FakeHttpError(404)
        return FakeRequest(self.drive.public(self.drive.items[fileId]), self.drive)

    def list(self, q=None, pageSize=1000, fields=None, pageToken=None, **kwargs):
        page, token = self.drive.query(q, pageToken)
        return FakeRequest({"files": [self.drive.public(i) for i in page], "nextPageToken": token}, self.drive)

    def create(self, body=None, media_body=None, fields=None, headers=None, **kwargs):
        if self.drive.fail_status:
            raise FakeHttpError(self.drive.fail_status)
        data = _media_bytes(media_body)
        item = self.drive._mkfile(body["name"], body.get("mimeType", "application/octet-stream"), body["parents"][0], data)
        return FakeRequest(self.drive.public(item), self.drive)

    def update(self, fileId, body=None, media_body=None, addParents=None, removeParents=None, fields=None, headers=None, **kwargs):
        if self.drive.fail_status:
            raise FakeHttpError(self.drive.fail_status)
        item = self.drive.items[fileId]
        if body:
            if body.get("trashed"):
                item["trashed"] = True
                return FakeRequest(self.drive.public(item), self.drive)
            if "name" in body:
                item["name"] = body["name"]
        if addParents:
            item["parents"] = [addParents]
        if media_body is not None:
            data = _media_bytes(media_body)
            item["_data"] = data
            item["size"] = len(data)
            item["md5Checksum"] = hashlib.md5(data).hexdigest()
        return FakeRequest(self.drive.public(item), self.drive)

    def delete(self, fileId, **kwargs):
        if fileId not in self.drive.items:
            raise FakeHttpError(404)
        self._remove(fileId)
        return FakeRequest(None, self.drive)

    def _remove(self, file_id):
        for child in [i for i in self.drive.items.values() if file_id in i.get("parents", [])]:
            self._remove(child["id"])
        self.drive.items.pop(file_id, None)

    def get_media(self, fileId, **kwargs):
        item = self.drive.items.get(fileId)
        if item is None:
            raise FakeHttpError(404)
        return FakeRequest(item.get("_data", b""), self.drive)


def _media_bytes(media):
    if media is None:
        return b""
    return Path(media._filename).read_bytes()


def make_provider(drive, folder_id="", token_store=None):
    return GDriveProvider(
        service=drive,
        credentials=None,
        folder_id=folder_id,
        token_store=token_store,
    )


def test_root_find_create_and_list(tmp_path):
    drive = FakeDrive()
    provider = make_provider(drive)
    assert provider.root_exists() is False

    provider.ensure_root()
    assert provider.folder_id
    drive._mkfile("Math", FOLDER_MIME, provider.folder_id)
    math_id = [i["id"] for i in drive.items.values() if i["name"] == "Math"][0]
    drive._mkfile("a.pdf", "application/pdf", math_id, b"abc")

    entries = provider.list_remote()

    assert set(entries) == {"Math", "Math/a.pdf"}
    assert entries["Math"].is_dir
    assert entries["Math/a.pdf"].hash == hashlib.md5(b"abc").hexdigest()
    assert entries["Math/a.pdf"].hash_kind == "md5"


def test_upload_creates_parents_and_updates_existing(tmp_path):
    drive = FakeDrive()
    provider = make_provider(drive, folder_id="root")
    local = tmp_path / "a.pdf"
    local.write_bytes(b"one")

    first = provider.upload_file(local, "Math/a.pdf")
    assert first.hash_kind == "md5"
    assert drive.items[first.remote_id]["parents"][0] != "root"

    local.write_bytes(b"two")
    second = provider.upload_file(local, "Math/a.pdf")

    assert second.remote_id == first.remote_id
    assert drive.items[second.remote_id]["_data"] == b"two"
    files = [i for i in drive.items.values() if i.get("name") == "a.pdf"]
    assert len(files) == 1


def test_download_and_read_text(tmp_path):
    drive = FakeDrive()
    provider = make_provider(drive, folder_id="root")
    drive._mkfile("a.pdf", "application/pdf", "root", b"hello")

    target = tmp_path / "a.pdf"
    provider.download_file("a.pdf", target)
    assert target.read_bytes() == b"hello"
    assert provider.read_text("a.pdf") == "hello"


def test_move_and_delete(tmp_path):
    drive = FakeDrive()
    provider = make_provider(drive, folder_id="root")
    local = tmp_path / "a.pdf"
    local.write_bytes(b"x")
    entry = provider.upload_file(local, "a.pdf")
    provider.create_dir("Sub")

    provider.move("a.pdf", "Sub/b.pdf", False)

    item = drive.items[entry.remote_id]
    assert item["name"] == "b.pdf"
    assert drive.items[[i["id"] for i in drive.items.values() if i["name"] == "Sub"][0]]["id"] in item["parents"]

    provider.delete("Sub/b.pdf", False)
    assert drive.items[entry.remote_id]["trashed"] is True

    trash_id = drive._mkfile("x", "application/octet-stream", "root", b"y")["id"]
    provider._rel_to_id[".trash/E/files/x"] = trash_id
    provider.delete(".trash/E/files/x", False)
    assert trash_id not in drive.items


def test_native_google_files_are_skipped(tmp_path):
    drive = FakeDrive()
    provider = make_provider(drive, folder_id="root")
    drive._mkfile("Doc", "application/vnd.google-apps.document", "root")
    drive._mkfile("a.pdf", "application/pdf", "root", b"x")

    entries = provider.list_remote()

    assert set(entries) == {"a.pdf"}


def test_pagination(tmp_path):
    drive = FakeDrive()
    drive.page_size = 2
    provider = make_provider(drive, folder_id="root")
    for index in range(5):
        drive._mkfile(f"{index}.pdf", "application/pdf", "root", b"x")

    entries = provider.list_remote()

    assert len([rel for rel in entries if rel.endswith(".pdf")]) == 5


def test_auth_and_not_found_errors(tmp_path):
    drive = FakeDrive()
    drive.fail_status = 401
    provider = make_provider(drive, folder_id="root")

    with pytest.raises(SyncAuthError):
        provider.list_remote()

    drive.fail_status = None
    with pytest.raises(SyncNotFoundError):
        provider.read_text("missing.pdf")


class NullStore:
    def get_secret(self, name):
        return None

    def set_secret(self, name, value):
        pass


def test_load_credentials_without_token_needs_interaction(tmp_path):
    with pytest.raises(SyncAuthError):
        load_credentials(str(tmp_path / "missing.json"), NullStore(), interactive=False)


def test_resolve_client_secret_order(tmp_path, monkeypatch):
    import sync.gdrive as gdrive

    bundled = tmp_path / "bundled.json"
    env_file = tmp_path / "env.json"
    configured = tmp_path / "configured.json"
    monkeypatch.setattr(gdrive, "BUNDLED_CLIENT_SECRET", bundled)
    monkeypatch.delenv("UNIDOCS_GDRIVE_CLIENT_SECRET", raising=False)

    assert resolve_client_secret("") == ""

    bundled.write_text("{}", encoding="utf-8")
    assert resolve_client_secret("") == str(bundled)

    env_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("UNIDOCS_GDRIVE_CLIENT_SECRET", str(env_file))
    assert resolve_client_secret("") == str(env_file)

    configured.write_text("{}", encoding="utf-8")
    assert resolve_client_secret(str(configured)) == str(configured)


def _sync(root, state_path, drive):
    provider = make_provider(drive, folder_id="root")
    state = SyncState("gdrive:root", root, path=state_path).load()
    return SyncEngine(provider, root, state, device_name="Laptop").run()


def test_two_devices_over_gdrive_and_trash(tmp_path):
    drive = FakeDrive()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "Math").mkdir()
    (a / "Math" / ".meta").write_text("{}", encoding="utf-8")
    (a / "Math" / "doc.pdf").write_bytes(b"data")

    assert not _sync(a, tmp_path / "sa", drive).errors
    assert not _sync(b, tmp_path / "sb", drive).errors
    assert (b / "Math" / "doc.pdf").read_bytes() == b"data"

    TrashStore(a, device_name="Laptop").move_to_trash(a / "Math" / "doc.pdf", "document")
    assert not _sync(a, tmp_path / "sa", drive).errors
    assert not _sync(b, tmp_path / "sb", drive).errors
    assert not (b / "Math" / "doc.pdf").exists()
    entries = TrashStore(b).list_entries()
    assert len(entries) == 1
    assert entries[0].payload.read_bytes() == b"data"


def test_upload_uses_if_match_for_known_remote_file(tmp_path):
    drive = FakeDrive()
    provider = make_provider(drive, folder_id="root")
    local = tmp_path / "a.pdf"
    local.write_bytes(b"one")
    first = provider.upload_file(local, "a.pdf")

    local.write_bytes(b"two")
    second = provider.upload_file(local, "a.pdf", expected_etag=first.etag)

    assert second.remote_id == first.remote_id
    assert drive.last_headers.get("If-Match") == first.etag
