"""API token auth for the UniDocs sync server.

A single long-lived token protects the sync API. It lives in a 0600 file in the
per-user config folder and is generated on first start; ``UNIDOCS_API_TOKEN``
overrides it (Docker, systemd).
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from fastapi import HTTPException, Request
from platformdirs import user_config_dir

logger = logging.getLogger(__name__)

TOKEN_FILE_NAME = "server_token.txt"
_ENV_TOKEN = "UNIDOCS_API_TOKEN"
_AUTH_SCHEME = "Bearer"

_cached: str | None = None


def token_path() -> Path:
    return Path(user_config_dir("UniDocs", appauthor=False)) / TOKEN_FILE_NAME


def load_or_create_token() -> str:
    """Return the server API token, creating the token file on first start.

    An ``UNIDOCS_API_TOKEN`` environment variable always wins, so a container
    or systemd unit can pin the token without touching the config dir.
    """
    env = os.environ.get(_ENV_TOKEN, "").strip()
    if env:
        return env
    path = token_path()
    if path.exists():
        raw = path.read_text(encoding="utf-8").strip()
        if raw:
            return raw
    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(token + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # Windows: ACLs inherit from the user profile
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    logger.info("generated a new UniDocs API token at %s", path)
    return token


def current_token() -> str:
    """Cached token; loaded once per process (see ``reset_cache`` for tests)."""
    global _cached
    if _cached is None:
        _cached = load_or_create_token()
    return _cached


def reset_cache() -> None:
    """Drop the cached token so the next call re-reads the file/env."""
    global _cached
    _cached = None


def require_token(request: Request) -> str:
    """Validate ``Authorization: Bearer <token>`` and return the token.

    Raises ``HTTPException(401)`` when the header is missing or wrong.
    """
    expected = current_token()
    header = request.headers.get("Authorization", "")
    if header.startswith(_AUTH_SCHEME + " "):
        supplied = header[len(_AUTH_SCHEME) + 1 :].strip()
        if supplied and secrets.compare_digest(supplied, expected):
            return supplied
    raise HTTPException(status_code=401, detail="missing or invalid API token")
