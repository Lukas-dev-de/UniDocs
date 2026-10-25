"""Tests for the global search matcher in ``ui.components.search_dialog``."""

from models.document import Document
from models.module import Module
from ui.components.search_dialog import search_modules


def _module(title, description="", group=None, documents=()):
    return Module(
        title=title,
        description=description,
        group=group,
        documents=[Document(title=name) for name in documents],
    )


def test_empty_query_returns_nothing():
    modules = [_module("Algebra")]
    assert search_modules(modules, "") == ([], [])
    assert search_modules(modules, "   ") == ([], [])
    assert search_modules(modules, None) == ([], [])


def test_module_title_match_is_case_insensitive():
    ana = _module("Analysis")
    modules = [_module("Algebra"), ana]
    module_hits, document_hits = search_modules(modules, "ALY")
    assert module_hits == [ana]
    assert document_hits == []


def test_module_description_matches():
    stoch = _module("Stochastik", description="Wahrscheinlichkeit und Zufall")
    module_hits, _ = search_modules([_module("Algebra"), stoch], "zufall")
    assert module_hits == [stoch]


def test_document_titles_are_searched_and_keep_their_module():
    algebra = _module("Algebra", documents=["Blatt 1", "Blatt 2"])
    analysis = _module("Analysis", documents=["Skript Blatt"])
    module_hits, document_hits = search_modules([algebra, analysis], "blatt")

    assert module_hits == []
    assert [module for module, _ in document_hits] == [algebra, algebra, analysis]
    assert [doc.title for _, doc in document_hits] == [
        "Blatt 1",
        "Blatt 2",
        "Skript Blatt",
    ]


def test_module_hits_come_before_document_hits():
    algebra = _module("Algebra", documents=["Algebra Skript"])
    module_hits, document_hits = search_modules([algebra], "algebra")
    assert module_hits == [algebra]
    assert [doc.title for _, doc in document_hits] == ["Algebra Skript"]


def test_store_order_is_preserved():
    home = _module("Home Modul")
    grouped = _module("Group Modul", group="Semester 1")
    module_hits, _ = search_modules([home, grouped], "modul")
    assert module_hits == [home, grouped]


def test_no_match_returns_both_lists_empty():
    assert search_modules([_module("Algebra")], "physik") == ([], [])
