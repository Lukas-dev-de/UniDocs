"""Tests for the app-wide logging setup (app_logging)."""

import logging

import app_logging


def _isolate(monkeypatch):
    """Reset app_logging state so a test can configure it from scratch."""
    logger = logging.getLogger(app_logging.ROOT_LOGGER)
    monkeypatch.setattr(app_logging, "_configured", False)
    monkeypatch.setattr(logger, "handlers", list(logger.handlers))


def _own_handlers(logger):
    """Our handlers only - pytest attaches its own capture handler to the logger."""
    return [h for h in logger.handlers if h.get_name() == app_logging.ROOT_LOGGER]


def test_setup_logging_writes_to_file(tmp_path, monkeypatch):
    monkeypatch.setattr(app_logging, "user_log_dir", lambda *a, **k: str(tmp_path / "logs"))
    _isolate(monkeypatch)
    logger = logging.getLogger(app_logging.ROOT_LOGGER)

    path = app_logging.setup_logging()

    assert path == tmp_path / "logs" / app_logging.LOG_FILE_NAME
    app_logging.get_logger("ui.test").error("boom")
    for handler in logger.handlers:
        handler.flush()
    assert "boom" in path.read_text(encoding="utf-8")


def test_setup_logging_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(app_logging, "user_log_dir", lambda *a, **k: str(tmp_path / "logs"))
    _isolate(monkeypatch)
    logger = logging.getLogger(app_logging.ROOT_LOGGER)

    first = app_logging.setup_logging()
    second = app_logging.setup_logging()

    assert first == second
    assert len(_own_handlers(logger)) == 1


def test_setup_logging_falls_back_when_unwritable(tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(app_logging, "user_log_dir", lambda *a, **k: str(blocker / "logs"))
    _isolate(monkeypatch)
    logger = logging.getLogger(app_logging.ROOT_LOGGER)

    assert app_logging.setup_logging() is None
    assert len(_own_handlers(logger)) == 1
    assert isinstance(_own_handlers(logger)[0], logging.StreamHandler)


def test_get_logger_uses_namespace():
    assert app_logging.get_logger("ui.module_detail").name == "unidocs.ui.module_detail"
    assert app_logging.get_logger("src.ui.x").name == "unidocs.ui.x"
