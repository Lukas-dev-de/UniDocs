"""App-wide logging.

Errors that get swallowed in the UI (or that only ever hit ``print``) land in a
rotating log file, so a bug report can still show what went wrong. Location:

    Linux    ~/.local/state/UniDocs/log/UniDocs.log
    macOS    ~/Library/Logs/UniDocs/UniDocs.log
    Windows  %LOCALAPPDATA%\\UniDocs\\Logs\\UniDocs.log

Usage: ``get_logger(__name__)`` at module level, ``setup_logging()`` once from
``main()``. Logging never raises: if the log folder is unusable the handlers
fall back to stderr and the app keeps running.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from platformdirs import user_log_dir

APP_NAME = "UniDocs"
LOG_FILE_NAME = "UniDocs.log"
MAX_BYTES = 512 * 1024
BACKUP_COUNT = 2
ROOT_LOGGER = "unidocs"

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_configured = False


def get_logger(name: str) -> logging.Logger:
    """Logger inside the ``unidocs.*`` namespace."""
    short = name[len("src."):] if name.startswith("src.") else name
    return logging.getLogger(f"{ROOT_LOGGER}.{short}")


def log_path() -> Path:
    """Path the log file is written to (whether or not it exists)."""
    return Path(user_log_dir(APP_NAME, appauthor=False)) / LOG_FILE_NAME


def setup_logging(level: int = logging.INFO) -> Path | None:
    """Attach one rotating file handler to ``unidocs``; idempotent.

    Returns the log path, or ``None`` when the file could not be opened (the
    handler then writes to stderr instead).
    """
    global _configured
    logger = logging.getLogger(ROOT_LOGGER)
    if _configured:
        return log_path() if _file_handler_installed(logger) else None
    _configured = True
    logger.setLevel(level)
    # Keep app records out of the root logger, so flet/urllib noise stays out
    # of our file and our records are not printed twice.
    logger.propagate = False

    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.set_name(ROOT_LOGGER)  # lets tests (and debuggers) spot our handler
    logger.addHandler(handler)
    return path if isinstance(handler, RotatingFileHandler) else None


def _file_handler_installed(logger: logging.Logger) -> bool:
    return any(isinstance(h, RotatingFileHandler) for h in logger.handlers)
