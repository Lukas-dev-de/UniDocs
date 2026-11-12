"""UniDocs provider against a small in-memory HTTP API (no network)."""

import hashlib
import json

import httpx
import pytest

from sync.base import SyncAuthError, SyncConflictError, SyncNotFoundError
from sync.unidocs import UniDocsProvider

TOKEN = "provider-token"
BASE = "http://test"
PREFIX = "/api/v1"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ApiServer:
    """Minimal in-memory stand-in for the UniDocs server sync API."""

    def __init__(self, token):
        self.token = token
        self.files: dict[str, bytes] = {}
        self.dirs: set[str] = set()
        self.requests: list[tuple[str, str]] = []
        self.if_match: dict[str, str] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, request.url.path))
        auth = request.headers.get("authorization")
        if auth != f"Bearer {self.token}":
            return httpx.Response(401, json={"detail": "invalid token"})

        path = request.url.path
        method = request.method
        if path == f"{PREFIX}/status":
            return httpx.Response(200, json={"ok": True, "name": "UniDocs server"})
        if path == f"{PREFIX}/files" and method == "GET":
            return self._list()
        if path == f"{PREFIX}/move" and method == "POST":
            return self._move(request)
        rel = path[len(f"{PREFIX}/files/") :] if path.startswith(f"{PREFIX}/files/") else None
        if rel is not None:
            rel = rel.rstrip("/")
            if method == "GET":
                return self._download(rel)
            if method == "PUT":
                return self._upload(rel, request)
            if method == "DELETE":
                return self._delete(rel)
        if path.startswith(f"{PREFIX}/dirs/") and method == "POST":
            return self._mkdir(path[len(f"{PREFIX}/dirs/") :])
        return httpx.Response(404, json={"detail": "not found"})

    def _list(self) -> httpx.Response:
        entries = []
        for d in sorted(self.dirs):
            entries.append({"path": d, "is_dir": True, "size": 0, "mtime": 1.0,
                            "sha256": None, "etag": None})
        for rel, data in sorted(self.files.items()):
            entries.append({"path": rel, "is_dir": False, "size": len(data),
                            "mtime": 1.0, "sha256": _sha(data), "etag": _sha(data)})
        return httpx.Response(200, json={"files": entries})

    def _download(self, rel: str) -> httpx.Response:
        if rel not in self.files:
            return httpx.Response(404, json={"detail": "not found"})
        return httpx.Response(200, content=self.files[rel])

    def _upload(self, rel: str, request: httpx.Request) -> httpx.Response:
        if_match = request.headers.get("if-match")
        if if_match:
            if rel not in self.files or _sha(self.files[rel]) != if_match:
                return httpx.Response(412, json={"detail": "precondition failed"})
        data = request.content
        self.files[rel] = data
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        if parent:
            self.dirs.add(parent)
        return httpx.Response(200, json={
            "path": rel, "is_dir": False, "size": len(data), "mtime": 1.0,
            "sha256": _sha(data), "etag": _sha(data),
        })

    def _mkdir(self, rel: str) -> httpx.Response:
        self.dirs.add(rel)
        return httpx.Response(200, json={"path": rel, "is_dir": True, "mtime": 0.0})

    def _move(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        src, dst = body["from"], body["to"]
        if src not in self.files and src not in self.dirs:
            return httpx.Response(404, json={"detail": "not found"})
        if src in self.files:
            self.files[dst] = self.files.pop(src)
        else:
            prefix = src + "/"
            for key in list(self.files):
                if key.startswith(prefix):
                    self.files[dst + "/" + key[len(prefix) :]] = self.files.pop(key)
            self.dirs.discard(src)
            for d in list(self.dirs):
                if d.startswith(prefix):
                    self.dirs.add(dst + "/" + d[len(prefix) :])
                    self.dirs.discard(d)
            self.dirs.add(dst)
        return httpx.Response(200, json={"ok": True})

    def _delete(self, rel: str) -> httpx.Response:
        if rel in self.files:
            del self.files[rel]
        elif rel in self.dirs:
            prefix = rel + "/"
            self.files = {k: v for k, v in self.files.items() if not k.startswith(prefix)}
            self.dirs = {d for d in self.dirs if d != rel and not d.startswith(prefix)}
        else:
            return httpx.Response(404, json={"detail": "not found"})
        return httpx.Response(200, json={"ok": True})


@pytest.fixture
def provider():
    srv = ApiServer(TOKEN)
    client = httpx.Client(
        transport=httpx.MockTransport(srv.handler),
        base_url=BASE,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    return UniDocsProvider(BASE, TOKEN, client=client), srv


def test_test_connection_and_root(provider):
    p, _ = provider
    p.test_connection()
    assert p.root_exists()


def test_upload_list_download(provider, tmp_path):
    p, _ = provider
    local = tmp_path / "doc.pdf"
    local.write_bytes(b"hello")

    entry = p.upload_file(local, "Math/doc.pdf")
    assert entry.rel_path == "Math/doc.pdf"
    assert entry.hash_kind == "sha256"

    entries = p.list_remote()
    assert set(entries) == {"Math", "Math/doc.pdf"}
    assert entries["Math"].is_dir

    out = tmp_path / "out.pdf"
    p.download_file("Math/doc.pdf", out)
    assert out.read_bytes() == b"hello"
    assert p.read_text("Math/doc.pdf") == "hello"


def test_upload_if_match_maps_conflict(provider, tmp_path):
    p, _ = provider
    local = tmp_path / "a.txt"
    local.write_bytes(b"one")
    p.upload_file(local, "a.txt")

    with pytest.raises(SyncConflictError):
        p.upload_file(local, "a.txt", expected_etag="wrong")


def test_move_and_delete(provider, tmp_path):
    p, _ = provider
    local = tmp_path / "x.txt"
    local.write_bytes(b"x")
    p.upload_file(local, "x.txt")
    p.move("x.txt", "y.txt", False)
    with pytest.raises(SyncNotFoundError):
        p.read_text("x.txt")
    assert p.read_text("y.txt") == "x"
    p.delete("y.txt", False)
    with pytest.raises(SyncNotFoundError):
        p.read_text("y.txt")


def test_create_dir(provider):
    p, _ = provider
    p.create_dir("A/B")
    assert "A/B" in p.list_remote()


def test_wrong_token_maps_auth_error(tmp_path):
    srv = ApiServer(TOKEN)
    client = httpx.Client(
        transport=httpx.MockTransport(srv.handler),
        base_url=BASE,
        headers={"Authorization": "Bearer wrong-token"},
    )
    p = UniDocsProvider(BASE, "wrong-token", client=client)
    with pytest.raises(SyncAuthError):
        p.test_connection()


def _sync(root, state_path, srv):
    client = httpx.Client(
        transport=httpx.MockTransport(srv.handler),
        base_url=BASE,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    p = UniDocsProvider(BASE, TOKEN, client=client)
    from sync.engine import SyncEngine
    from sync.state import SyncState

    state = SyncState("unidocs:test", root, path=state_path).load()
    engine = SyncEngine(p, root, state, device_name="Laptop")
    try:
        return engine.run()
    finally:
        p.close()


def test_two_devices_over_unidocs_and_trash(tmp_path):
    srv = ApiServer(TOKEN)
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

    # A local delete on device A propagates to device B via the trash flow.
    from app_storage.trash_store import TrashStore

    TrashStore(a, device_name="Laptop").move_to_trash(a / "Math" / "doc.pdf", "document")
    assert not _sync(a, tmp_path / "sa", srv).errors
    assert not _sync(b, tmp_path / "sb", srv).errors
    assert not (b / "Math" / "doc.pdf").exists()
    entries = TrashStore(b).list_entries()
    assert len(entries) == 1
    assert entries[0].payload.read_bytes() == b"data"
