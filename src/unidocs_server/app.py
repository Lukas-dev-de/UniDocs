"""FastAPI app for the UniDocs server: sync API + web UI in one process."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from platformdirs import user_cache_dir

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app_storage.app_config import AppConfig  # noqa: E402
from unidocs_server.api import router as sync_router  # noqa: E402

APP_NAME = "UniDocs"

# Shown in the browser tab instead of downloading when possible. Everything
# else is sent as an attachment, so iOS puts it into the Files app.
_INLINE_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".txt",
    ".md",
    ".mp3",
    ".wav",
    ".mp4",
    ".webm",
}


def _document_root() -> Path:
    """Storage folder currently configured in the app.

    Read on every request because the setting can change while the server is
    running (Settings -> storage location).
    """
    return AppConfig().unidocs_location.resolve()


def _safe_document_path(relative_path: str) -> Path:
    """Resolve *relative_path* and refuse anything outside the document root."""
    from fastapi import HTTPException

    root = _document_root()
    target = (root / relative_path).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(status_code=404)
    if not target.is_file():
        raise HTTPException(status_code=404)
    return target


def create_app() -> FastAPI:
    """Build the ASGI app: sync API first, then the web UI at ``/``."""
    from flet_web.fastapi import app as flet_app
    from main import main as flet_main

    upload_dir = Path(user_cache_dir(APP_NAME, appauthor=False)) / "web_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI()

    # Authenticated sync API for the desktop app.
    app.include_router(sync_router, prefix="/api/v1")

    # Browser download route for the web UI (no login, tailnet only).
    @app.get("/files/{relative_path:path}")
    def download_document(relative_path: str):
        target = _safe_document_path(relative_path)
        disposition = (
            "inline" if target.suffix.lower() in _INLINE_SUFFIXES else "attachment"
        )
        return FileResponse(
            target,
            filename=target.name,
            content_disposition_type=disposition,
        )

    # Mounted last: Flet's static handler answers every unknown path with the
    # index page, so /files and /api must be registered before it.
    app.mount(
        "/",
        flet_app(
            flet_main,
            assets_dir=str(SRC / "assets"),
            upload_dir=str(upload_dir),
            app_name=APP_NAME,
            app_short_name=APP_NAME,
            app_description="Document management on your own server",
        ),
    )
    return app
