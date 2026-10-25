"""Tests for the model dataclasses and their serialisation."""

import flet as ft

from models.document import Document
from models.module import Module
from models.tag import DEFAULT_TAG_COLOR, Tag


def test_module_defaults():
    module = Module()

    assert module.title == "New Module"
    assert module.description == ""
    assert module.icon == ft.Icons.SQUARE
    assert module.color is None
    assert module.group is None
    assert module.documents == []


def test_module_documents_are_not_shared():
    first, second = Module(), Module()
    first.add_document(Document(title="a.pdf"))

    assert len(first.documents) == 1
    assert second.documents == []


def test_module_to_meta_shape():
    module = Module(description="notes", icon=ft.Icons.SCHOOL, color="#112233")

    assert module.to_meta("SCHOOL") == {
        "id": module.id,
        "description": "notes",
        "icon": "SCHOOL",
        "color": "#112233",
    }


def test_module_meta_round_trip():
    module = Module(description="notes", icon=ft.Icons.SCHOOL, color="#112233")

    back = Module.from_meta(
        title="School", meta=module.to_meta("SCHOOL"), icon=ft.Icons.SCHOOL, group="Uni"
    )

    assert (back.title, back.description, back.color, back.group) == (
        "School",
        "notes",
        "#112233",
        "Uni",
    )
    assert back.icon == ft.Icons.SCHOOL
    assert back.documents == []


def test_module_from_meta_falls_back_for_missing_keys():
    back = Module.from_meta(title="Old", meta={}, icon=ft.Icons.FOLDER)

    assert back.description == ""
    assert back.color is None
    assert back.group is None


def test_module_from_meta_treats_null_color_as_theme():
    back = Module.from_meta(title="Old", meta={"color": None}, icon=ft.Icons.FOLDER)

    assert back.color is None


def test_module_ids_are_unique():
    assert Module().id != Module().id


def test_module_meta_keeps_the_id():
    module = Module()

    back = Module.from_meta(title="x", meta=module.to_meta("FOLDER"), icon=None)

    assert back.id == module.id


def test_module_from_meta_generates_a_missing_id():
    first = Module.from_meta(title="Old", meta={}, icon=None)
    second = Module.from_meta(title="Old", meta={}, icon=None)

    assert first.id and second.id
    assert first.id != second.id


def test_document_defaults():
    doc = Document(title="a.pdf")

    assert doc.description == ""
    assert doc.filepath == ""
    assert doc.tags == []


def test_document_tags_are_not_shared():
    first, second = Document(title="a"), Document(title="b")
    first.tags.append(Tag.new("Lecture"))

    assert len(first.tags) == 1
    assert second.tags == []


def test_tag_round_trip():
    tag = Tag(id="abc", name="Lecture", color="#123456")

    assert Tag.from_dict(tag.to_dict()) == tag


def test_tag_from_dict_defaults_colour():
    tag = Tag.from_dict({"id": "abc", "name": "Lecture"})

    assert tag.color == DEFAULT_TAG_COLOR


def test_tag_new_gets_an_id():
    tag = Tag.new("Lecture")

    assert tag.name == "Lecture"
    assert tag.id
    assert tag.color == DEFAULT_TAG_COLOR
