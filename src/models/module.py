import flet as ft
from models.document import Document


class Module:
    def __init__(
        self,
        title: str = "New Module",
        description: str = "",
        icon=ft.Icons.SQUARE,
    ):
        self.title = title
        self.description = description
        self.icon = icon
        self.documents = []

    def add_document(self, document: Document):
        self.documents.append(document)