from fastapi import APIRouter, HTTPException
from app.models.summary import DocumentSummary
from app.repositories.document_repository import DocumentRepository
from app.services.summary.summary_service import SummaryService


router = APIRouter(prefix="/api/documents", tags=["summary"])


@router.get("/{document_id}/summary", response_model=DocumentSummary)
async def get_summary(document_id: str):
    document = DocumentRepository.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Dokumenttia ei löytynyt")

    return SummaryService.build(
        document_id=document_id,
        document_status=document.status,
    )