#!/usr/bin/env python3
"""
serve_web.py
------------
Hosts UniDocs as a dynamic web app on a home server.

The Python side keeps running on the server: the browser (iPad, laptop, ...)
only renders the Flet UI. That means storage, imports and the filesystem
watcher stay where the documents are. Same idea as ``flet run --web``, but
with a stable port, a PWA name/icon and a download route for documents.

Usage
-----
    ./.venv/bin/python tools/serve_web.py
    ./.venv/bin/python tools/serve_web.py --host 0.0.0.0 --port 8550

Open the printed address (or ``http://<tailscale-ip>:8550``) in Safari and use
*Share -> Add to Home Screen*.

Requirements
------------
    ./.venv/bin/pip install -e '.[web]'
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from platformdirs import user_cache_dir

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from app_storage.app_config import AppConfig  # noqa: E402
from flet_web.fastapi import app as flet_app  # noqa: E402
from main import main as flet_main  # noqa: E402

APP_NAME = "UniDocs"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8550

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
    root = _document_root()
    target = (root / relative_path).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(status_code=404)
    if not target.is_file():
        raise HTTPException(status_code=404)
    return target


def create_app() -> FastAPI:
    """Build the ASGI app: download route first, Flet web app at ``/``."""
    upload_dir = Path(user_cache_dir(APP_NAME, appauthor=False)) / "web_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI()

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
    # index page, so /files must be registered before it.
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve UniDocs as a web app.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="bind address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port")
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
    )
    args = parser.parse_args()

    print(f"UniDocs web server: http://{args.host}:{args.port}/")
    uvicorn.run(
        create_app(),
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        ws="websockets-sansio",
    )


if __name__ == "__main__":
    main()
