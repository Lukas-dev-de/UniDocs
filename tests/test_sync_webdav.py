"""WebDAV provider against a small in-memory HTTP server (no network)."""

import httpx
import pytest
from webdav4.client import Client

from app_storage.trash_store import TrashStore
from sync.base import SyncAuthError, SyncNotFoundError
from sync.engine import SyncEngine
from sync.state import SyncState
from sync.webdav import WebDAVProvider

BASE = "https://cloud.example.com/dav"
PREFIX = "/dav"


class DavServer:
    def __init__(self):
        self.dirs = {"/dav/UniDocs"}
        self.files = {}
        self.requests = []
        self.force_status = None
        self.last_headers = {}
        self.headers_by_method = {}

    def handler(self, request: httpx.Request):
        self.requests.append((request.method, request.url.path))
        self.last_headers = dict(request.headers)
        self.headers_by_method[request.method] = dict(request.headers)
        if self.force_status:
            return httpx.Response(self.force_status)
        path = request.url.path.rstrip("/") or "/"
        method = request.method

        if method == "PROPFIND":
            return self._propfind(request, path)
        if method == "PUT":
            self.files[path] = request.content
            return httpx.Response(201)
        if method == "GET":
            if path not in self.files:
                return httpx.Response(404)
            return httpx.Response(200, content=self.files[path])
        if method == "MKCOL":
            if path in self.dirs or path in self.files:
                return httpx.Response(405)
            parent = path.rsplit("/", 1)[0]
            if parent not in self.dirs:
                return httpx.Response(409)
            self.dirs.add(path)
            return httpx.Response(201)
        if method == "MOVE":
            destination = httpx.URL(request.headers["Destination"]).path.rstrip("/")
            if path in self.files:
                self.files[destination] = self.files.pop(path)
            else:
                self._move_dir(path, destination)
            return httpx.Response(201)
        if method == "DELETE":
            if path in self.files:
                del self.files[path]
            else:
                self.files = {k: v for k, v in self.files.items() if not k.startswith(path + "/")}
                self.dirs = {d for d in self.dirs if d != path and not d.startswith(path + "/")}
            return httpx.Response(204)
        if method == "OPTIONS":
            return httpx.Response(200, headers={"DAV": "1,2"})
        return httpx.Response(405)

    def _move_dir(self, src, dst):
        self.dirs.add(dst)
        for key in list(self.files):
            if key.startswith(src + "/"):
                self.files[dst + key[len(src) :]] = self.files.pop(key)
        for key in list(self.dirs):
            if key.startswith(src + "/"):
                self.dirs.add(dst + key[len(src) :])
                self.dirs.discard(key)
        self.dirs.discard(src)

    def _propfind(self, request, path):
        if path not in self.dirs and path not in self.files:
            return httpx.Response(404)
        depth = request.headers.get("Depth", "1")
        entries = [path] if path in self.dirs else [path]
        if depth != "0" and path in self.dirs:
            entries += sorted(
                d for d in self.dirs if d.rsplit("/", 1)[0] == path and d != path
            )
            entries += sorted(
                f for f in self.files if f.rsplit("/", 1)[0] == path
            )
        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<d:multistatus xmlns:d="DAV:">'
            + "".join(self._response(path, entry) for entry in entries)
            + "</d:multistatus>"
        )
        return httpx.Response(207, content=body.encode("utf-8"))

    def _response(self, request_path, entry):
        name = entry.rsplit("/", 1)[-1] or "UniDocs"
        if entry in self.dirs:
            props = f"<d:displayname>{name}</d:displayname><d:resourcetype><d:collection/></d:resourcetype>"
        else:
            data = self.files[entry]
            props = (
                f"<d:displayname>{name}</d:displayname><d:resourcetype/>"
                f"<d:getcontentlength>{len(data)}</d:getcontentlength>"
                "<d:getlastmodified>Mon, 27 Oct 2026 14:05:00 GMT</d:getlastmodified>"
                '<d:getetag>"etag"</d:getetag>'
            )
        return (
            f"<d:response><d:href>{entry}</d:href><d:propstat><d:prop>{props}"
            "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
        )


@pytest.fixture
def server():
    srv = DavServer()
    srv.dirs.add("/dav")
    http = httpx.Client(transport=httpx.MockTransport(srv.handler))
    return srv, http


def provider(server, http, root="UniDocs"):
    srv, _ = server
    client = Client(BASE, auth=("u", "p"), http_client=http)
    return WebDAVProvider(BASE, "u", "p", remote_root=root, client=client)


def test_lists_recursively_and_strips_remote_root(server):
    srv, http = server
    srv.dirs.update({"/dav/UniDocs/Math"})
    srv.files["/dav/UniDocs/Math/a.pdf"] = b"abc"
    p = provider(server, http)

    entries = p.list_remote()

    assert set(entries) == {"Math", "Math/a.pdf"}
    assert entries["Math"].is_dir
    assert entries["Math/a.pdf"].size == 3
    assert entries["Math/a.pdf"].mtime > 0


def test_upload_creates_parent_dirs_and_returns_entry(server, tmp_path):
    srv, http = server
    p = provider(server, http)
    local = tmp_path / "a.pdf"
    local.write_bytes(b"hello")

    entry = p.upload_file(local, "Math/a.pdf")

    assert entry.rel_path == "Math/a.pdf"
    assert entry.size == 5
    assert "/dav/UniDocs/Math" in srv.dirs
    assert srv.files["/dav/UniDocs/Math/a.pdf"] == b"hello"


def test_upload_sends_if_match_header(server, tmp_path):
    srv, http = server
    p = provider(server, http)
    local = tmp_path / "a.pdf"
    local.write_bytes(b"hello")
    p.upload_file(local, "a.pdf")

    p.upload_file(local, "a.pdf", expected_etag='"old"')

    assert srv.headers_by_method["PUT"].get("if-match") == '"old"'


def test_download_read_text_move_and_delete(server, tmp_path):
    srv, http = server
    srv.files["/dav/UniDocs/a.pdf"] = b"hello"
    srv.files["/dav/UniDocs/b.pdf"] = b"json"
    p = provider(server, http)

    target = tmp_path / "a.pdf"
    p.download_file("a.pdf", target)
    assert target.read_bytes() == b"hello"
    assert p.read_text("b.pdf") == "json"

    p.move("a.pdf", "c.pdf", False)
    assert "/dav/UniDocs/c.pdf" in srv.files

    p.delete("c.pdf", False)
    assert "/dav/UniDocs/c.pdf" not in srv.files


def test_create_dir_and_root_exists(server):
    srv, http = server
    p = provider(server, http)
    assert p.root_exists()

    srv.dirs = {"/dav"}
    assert p.root_exists() is False
    p.ensure_root()
    assert "/dav/UniDocs" in srv.dirs


def test_auth_error_is_mapped(server):
    srv, http = server
    srv.force_status = 401
    p = provider(server, http)

    with pytest.raises(SyncAuthError):
        p.list_remote()
    with pytest.raises(SyncAuthError):
        p.test_connection()


def test_missing_root_lists_empty(server):
    srv, http = server
    srv.dirs.clear()
    p = provider(server, http)

    assert p.list_remote() == {}


def test_read_missing_file(server):
    srv, http = server
    p = provider(server, http)
    with pytest.raises(SyncNotFoundError):
        p.read_text("missing.txt")


def _sync(root, state_path, srv):
    http = httpx.Client(transport=httpx.MockTransport(srv.handler))
    p = provider((srv, http), http)
    state = SyncState("webdav:test", root, path=state_path).load()
    engine = SyncEngine(p, root, state, device_name="Laptop")
    try:
        return engine.run()
    finally:
        p.close()


def test_two_devices_over_webdav_and_trash(server, tmp_path):
    srv, _http = server
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "Math").mkdir()
    (a / "Math" / ".meta").write_text("{}", encoding="utf-8")
    (a / "Math" / "doc.pdf").write_bytes(b"data")

    assert not _sync(a, tmp_path / "sa", srv).errors
    assert not _sync(b, tmp_path / "sb", srv).errors
    assert (b / "Math" / "doc.pdf").read_bytes() == b"data"

    TrashStore(a, device_name="Laptop").move_to_trash(a / "Math" / "doc.pdf", "document")
    assert not _sync(a, tmp_path / "sa", srv).errors
    assert not _sync(b, tmp_path / "sb", srv).errors
    assert not (b / "Math" / "doc.pdf").exists()
    entries = TrashStore(b).list_entries()
    assert len(entries) == 1
    assert entries[0].payload.read_bytes() == b"data"
