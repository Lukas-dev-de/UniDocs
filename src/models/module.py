from models.document import Document
class Module:
    def __init__(self, title: str = "New Module", description : str = ""):
        self.title = title
        self.description = description
        self.documents = []
    
    def add_document(self, document):
        self.documents.append(document)