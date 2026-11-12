"""Sync API of the UniDocs server (FastAPI TestClient, no network)."""

import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from unidocs_server import auth
from unidocs_server.api import router

TOKEN = "test-token-123"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIDOCS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIDOCS_API_TOKEN", TOKEN)
    auth.reset_cache()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as c:
        yield c, tmp_path
    auth.reset_cache()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_status_requires_token(client):
    c, _ = client
    assert c.get("/api/v1/status").status_code == 401
    assert c.get("/api/v1/status", headers=AUTH).json()["ok"] is True


def test_upload_list_download(client):
    c, _ = client
    data = b"hello uni"
    resp = c.put("/api/v1/files/Math/doc.pdf", content=data, headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["sha256"] == _sha(data)
    assert body["etag"] == _sha(data)

    listing = c.get("/api/v1/files", headers=AUTH).json()["files"]
    by_path = {e["path"]: e for e in listing}
    assert set(by_path) == {"Math", "Math/doc.pdf"}
    assert by_path["Math"]["is_dir"] is True
    assert by_path["Math/doc.pdf"]["sha256"] == _sha(data)

    assert c.get("/api/v1/files/Math/doc.pdf", headers=AUTH).content == data


def test_upload_if_match_conflict(client):
    c, _ = client
    c.put("/api/v1/files/a.txt", content=b"one", headers=AUTH)
    # Wrong etag -> 412.
    resp = c.put(
        "/api/v1/files/a.txt",
        content=b"two",
        headers={**AUTH, "If-Match": "nope"},
    )
    assert resp.status_code == 412
    # Correct etag -> overwrite.
    etag = _sha(b"one")
    resp = c.put(
        "/api/v1/files/a.txt",
        content=b"two",
        headers={**AUTH, "If-Match": etag},
    )
    assert resp.status_code == 200
    assert c.get("/api/v1/files/a.txt", headers=AUTH).content == b"two"


def test_move_and_delete(client):
    c, _ = client
    c.put("/api/v1/files/x.pdf", content=b"pdf", headers=AUTH)
    assert (
        c.post("/api/v1/move", json={"from": "x.pdf", "to": "y.pdf"}, headers=AUTH).status_code
        == 200
    )
    assert c.get("/api/v1/files/x.pdf", headers=AUTH).status_code == 404
    assert c.get("/api/v1/files/y.pdf", headers=AUTH).content == b"pdf"

    assert c.delete("/api/v1/files/y.pdf", headers=AUTH).status_code == 200
    assert c.get("/api/v1/files/y.pdf", headers=AUTH).status_code == 404


def test_mkdir_and_recursive_delete(client):
    c, _ = client
    assert c.post("/api/v1/dirs/A/B", headers=AUTH).status_code == 200
    assert c.delete("/api/v1/files/A", headers=AUTH).status_code == 200
    assert c.get("/api/v1/files", headers=AUTH).json()["files"] == []


def test_path_traversal_rejected(client):
    c, _ = client
    assert c.get("/api/v1/files/../secret", headers=AUTH).status_code == 404
    assert c.put("/api/v1/files/../../evil", content=b"x", headers=AUTH).status_code == 404
