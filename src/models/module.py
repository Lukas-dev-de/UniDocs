import flet as ft
from models.document import Document


class Module:
    def __init__(
        self,
        title: str = "New Module",
        description: str = "",
        icon=ft.Icons.SQUARE,
        color: str | None = None,
    ):
        self.title = title
        self.description = description
        self.icon = icon
        # Accent colour as a "#RRGGBB" string. ``None`` means "follow the
        # theme", which is how every module created before v2.3.0 behaves.
        self.color = color
        self.documents = []

    def add_document(self, document: Document):
        self.documents.append(document)