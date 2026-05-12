from models.tag import Tag
class Document:
    def __init__(self, title, description, filepath, tags=None):
        self.title = title
        self.description = description
        self.filepath = filepath
        self.tags = tags if tags else []