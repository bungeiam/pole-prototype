import shutil
import uuid
from datetime import datetime
from pathlib import Path
from fastapi import UploadFile
from app.models.document import OfferDocument
from app.repositories.document_repository import DocumentRepository


class DocumentService:
    UPLOAD_DIR = Path("storage/uploads")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def save_upload(cls, file: UploadFile) -> OfferDocument:
        document_id = str(uuid.uuid4())
        suffix = Path(file.filename).suffix.lower()
        stored_filename = f"{document_id}{suffix}"
        stored_path = cls.UPLOAD_DIR / stored_filename

        with stored_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        document = OfferDocument(
            document_id=document_id,
            original_filename=file.filename,
            stored_path=str(stored_path),
            file_type=suffix.replace(".", ""),
            upload_time=datetime.utcnow(),
            status="uploaded",
        )
        return DocumentRepository.save(document)