"""Sync API for the UniDocs server.

The desktop app talks to these endpoints through ``src/sync/unidocs.py``. Every
route requires ``Authorization: Bearer <token>`` (see ``auth``).

The served tree is the server's UniDocs folder (``AppConfig.unidocs_location``,
or ``UNIDOCS_DATA_DIR`` when set - useful in Docker). Files expose a SHA-256
hash as both ``sha256`` and ``etag``; an upload with an ``If-Match`` header
fails with ``412`` when the current content differs, which is how the sync
engine detects concurrent edits.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from app_info import APP_VERSION
from app_storage.app_config import AppConfig
from app_storage.naming import SYNC_TMP_DIRNAME, UnsafePathError, normalize_rel
from sync.local_scan import hash_file, is_ignored_name
from unidocs_server.auth import require_token

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_token)])

_UPLOAD_SUFFIX = ".unidocs-upload"


class _PathError(HTTPException):
    def __init__(self, status: int, detail: str):
        super().__init__(status_code=status, detail=detail)


def default_root() -> Path:
    """The server's documents folder (honours ``UNIDOCS_DATA_DIR``)."""
    return AppConfig().unidocs_location.resolve()


async def get_root() -> Path:
    return default_root()


def _resolve(root: Path, rel: str) -> Path:
    """Resolve *rel* under *root*, refusing traversal."""
    try:
        clean = normalize_rel(rel)
    except UnsafePathError as exc:
        raise _PathError(404, str(exc)) from exc
    target = (root / clean).resolve()
    if target != root and root not in target.parents:
        raise _PathError(404, f"path escapes the root: {rel!r}")
    return target


def _entry(rel: str, path: Path) -> dict:
    if path.is_dir():
        stat = path.stat()
        return {
            "path": rel,
            "is_dir": True,
            "size": 0,
            "mtime": stat.st_mtime,
            "sha256": None,
            "etag": None,
        }
    stat = path.stat()
    sha, _ = hash_file(path, want_md5=False)
    return {
        "path": rel,
        "is_dir": False,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "sha256": sha,
        "etag": sha,
    }


@router.get("/status")
def status(root: Path = Depends(get_root)) -> dict:
    return {
        "ok": True,
        "name": "UniDocs server",
        "version": APP_VERSION,
        "root": str(root),
    }


@router.get("/files")
def list_files(root: Path = Depends(get_root)) -> dict:
    files: list[dict] = []
    if not root.is_dir():
        return {"files": files}
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        rel_dir = current_path.relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name != SYNC_TMP_DIRNAME
            and not is_ignored_name(name)
            and not (current_path / name).is_symlink()
        )
        filenames[:] = sorted(
            name
            for name in filenames
            if not is_ignored_name(name) and not (current_path / name).is_symlink()
        )
        if rel_dir:
            files.append(_entry(rel_dir, current_path))
        for name in filenames:
            rel = f"{rel_dir}/{name}" if rel_dir else name
            files.append(_entry(rel, current_path / name))
    return {"files": files}


@router.get("/files/{path:path}")
def download(path: str, root: Path = Depends(get_root)) -> FileResponse:
    target = _resolve(root, path)
    if not target.is_file():
        raise _PathError(404, f"not found: {path}")
    return FileResponse(target, filename=target.name)


@router.put("/files/{path:path}")
async def upload(path: str, request: Request, root: Path = Depends(get_root)) -> dict:
    target = _resolve(root, path)
    if_match = request.headers.get("if-match")
    if if_match:
        current = _etag_of(target) if target.exists() else None
        if current != if_match:
            raise _PathError(412, f"precondition failed for {path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + _UPLOAD_SUFFIX)
    try:
        with tmp.open("wb") as out:
            async for chunk in request.stream():
                out.write(chunk)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return _entry(path, target)


@router.post("/dirs/{path:path}")
def create_dir(path: str, root: Path = Depends(get_root)) -> dict:
    target = _resolve(root, path)
    target.mkdir(parents=True, exist_ok=True)
    return _entry(path, target)


@router.post("/move")
async def move(request: Request, root: Path = Depends(get_root)) -> JSONResponse:
    body = await request.json()
    src = body.get("from") or body.get("src")
    dst = body.get("to") or body.get("dst")
    is_dir = bool(body.get("is_dir", False))
    if not src or not dst:
        raise _PathError(400, "move needs 'from' and 'to'")
    src_path = _resolve(root, src)
    dst_path = _resolve(root, dst)
    if not src_path.exists():
        raise _PathError(404, f"not found: {src}")
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    if dst_path.exists():
        raise _PathError(409, f"destination exists: {dst}")
    shutil.move(str(src_path), str(dst_path))
    return JSONResponse({"ok": True, "from": src, "to": dst, "is_dir": is_dir})


@router.delete("/files/{path:path}")
def delete(path: str, root: Path = Depends(get_root)) -> dict:
    target = _resolve(root, path)
    if not target.exists():
        raise _PathError(404, f"not found: {path}")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"ok": True, "path": path}


def _etag_of(path: Path) -> str | None:
    if not path.is_file():
        return None
    sha, _ = hash_file(path, want_md5=False)
    return sha
