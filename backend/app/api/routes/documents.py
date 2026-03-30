from fastapi import APIRouter, UploadFile, File, HTTPException
from app.models.document import OfferDocument
from app.models.pole import DetectedPoleRow
from app.models.match import PoleMatch
from app.models.calculation import MassCalculationResult
from app.repositories.document_repository import DocumentRepository
from app.repositories.in_memory_store import (
    POLES_BY_DOCUMENT,
    MATCHES_BY_DOCUMENT,
    CALCULATIONS_BY_DOCUMENT,
)
from app.repositories.pole_pool_repository import PolePoolRepository
from app.services.document_service import DocumentService
from app.services.analysis_service import AnalysisService
from app.services.extraction.pole_extraction_service import PoleExtractionService
from app.services.matching.pole_matcher_service import PoleMatcherService
from app.services.calculations.mass_calculation_service import MassCalculationService


router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=OfferDocument)
async def upload_document(file: UploadFile = File(...)):
    return DocumentService.save_upload(file)


@router.get("", response_model=list[OfferDocument])
async def list_documents():
    return DocumentRepository.list_all()


@router.get("/{document_id}", response_model=OfferDocument)
async def get_document(document_id: str):
    document = DocumentRepository.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Dokumenttia ei löytynyt")
    return document


@router.post("/{document_id}/analyze", response_model=list[DetectedPoleRow])
async def analyze_document(document_id: str):
    document = DocumentRepository.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Dokumenttia ei löytynyt")

    raw_rows = AnalysisService.extract_raw_rows(document.stored_path)
    poles = PoleExtractionService.extract(document_id=document_id, raw_rows=raw_rows)

    POLES_BY_DOCUMENT[document_id] = poles
    document.status = "analyzed"
    DocumentRepository.save(document)

    return poles


@router.get("/{document_id}/poles", response_model=list[DetectedPoleRow])
async def get_poles(document_id: str):
    return POLES_BY_DOCUMENT.get(document_id, [])


@router.post("/{document_id}/match", response_model=list[PoleMatch])
async def match_document(document_id: str):
    document = DocumentRepository.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Dokumenttia ei löytynyt")

    poles = POLES_BY_DOCUMENT.get(document_id, [])
    if not poles:
        raise HTTPException(status_code=400, detail="Analysoituja pylväsrivejä ei löydy")

    pool_items = PolePoolRepository().load_all()
    matches = PoleMatcherService.match_rows(poles, pool_items)

    MATCHES_BY_DOCUMENT[document_id] = matches
    document.status = "matched"
    DocumentRepository.save(document)

    return matches


@router.get("/{document_id}/matches", response_model=list[PoleMatch])
async def get_matches(document_id: str):
    return MATCHES_BY_DOCUMENT.get(document_id, [])


@router.post("/{document_id}/calculate", response_model=list[MassCalculationResult])
async def calculate_document(document_id: str):
    document = DocumentRepository.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Dokumenttia ei löytynyt")

    poles = POLES_BY_DOCUMENT.get(document_id, [])
    matches = MATCHES_BY_DOCUMENT.get(document_id, [])

    if not poles or not matches:
        raise HTTPException(status_code=400, detail="Matchaus pitää tehdä ennen laskentaa")

    pool_items = PolePoolRepository().load_all()
    calculations = MassCalculationService.calculate(poles, matches, pool_items)

    CALCULATIONS_BY_DOCUMENT[document_id] = calculations
    document.status = "calculated"
    DocumentRepository.save(document)

    return calculations


@router.get("/{document_id}/calculations", response_model=list[MassCalculationResult])
async def get_calculations(document_id: str):
    return CALCULATIONS_BY_DOCUMENT.get(document_id, [])