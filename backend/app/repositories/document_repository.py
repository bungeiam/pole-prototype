from app.models.document import OfferDocument
from app.repositories.in_memory_store import DOCUMENTS


class DocumentRepository:
    @staticmethod
    def save(document: OfferDocument) -> OfferDocument:
        DOCUMENTS[document.document_id] = document
        return document

    @staticmethod
    def get(document_id: str) -> OfferDocument | None:
        return DOCUMENTS.get(document_id)

    @staticmethod
    def list_all() -> list[OfferDocument]:
        return list(DOCUMENTS.values())