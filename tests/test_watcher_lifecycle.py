"""Watcher lifecycle: stopping must be safe in every state.

The window-close handler in ``main`` calls ``stop_watching()`` without knowing
whether a watcher was ever started, so the stop path has to cope with ``None``
and with being called twice.
"""

from app_storage.module_store import ModuleStore


def test_stop_without_start_is_a_no_op(tmp_path):
    store = ModuleStore(root=tmp_path)
    store.stop_watching()
    store.stop_watching()
    assert store._observer is None


def test_stop_after_stop_keeps_observer_none(tmp_path):
    store = ModuleStore(root=tmp_path)
    store.start_watching()
    store.stop_watching()
    assert store._observer is None
    store.stop_watching()
    assert store._observer is None
