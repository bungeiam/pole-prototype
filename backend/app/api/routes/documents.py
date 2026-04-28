from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.ai_assist import AiAssistResult
from app.models.calculation import MassCalculationResult
from app.models.document import OfferDocument
from app.models.match import PoleMatch
from app.models.pole import DetectedPoleRow, PoleRowView
from app.repositories.document_repository import DocumentRepository
from app.repositories.in_memory_store import (
    AI_ASSISTS_BY_DOCUMENT,
    CALCULATIONS_BY_DOCUMENT,
    CORRECTIONS_BY_ROW,
    MATCHES_BY_DOCUMENT,
    POLES_BY_DOCUMENT,
)
from app.repositories.pole_pool_repository import PolePoolRepository
from app.services.ai.ai_assist_service import AiAssistService
from app.services.analysis_service import AnalysisService
from app.services.calculations.mass_calculation_service import MassCalculationService
from app.services.document_service import DocumentService
from app.services.extraction.pole_extraction_service import PoleExtractionService
from app.services.matching.pole_matcher_service import PoleMatcherService

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _build_pole_row_views(document_id: str) -> list[PoleRowView]:
    poles = POLES_BY_DOCUMENT.get(document_id, [])
    matches = MATCHES_BY_DOCUMENT.get(document_id, [])
    calculations = CALCULATIONS_BY_DOCUMENT.get(document_id, [])

    match_by_row_id = {item.row_id: item for item in matches}
    calculation_by_row_id = {item.row_id: item for item in calculations}

    result: list[PoleRowView] = []

    for row in poles:
        match = match_by_row_id.get(row.row_id)
        calculation = calculation_by_row_id.get(row.row_id)
        correction = CORRECTIONS_BY_ROW.get(row.row_id)

        result.append(
            PoleRowView(
                **row.model_dump(),
                match_status=match.status if match else None,
                match_score=match.score if match else None,
                match_reason=match.reason if match else None,
                suggested_pool_id=match.suggested_pool_id if match else None,
                alternative_pool_ids=match.alternatives if match else [],
                calculation_status=calculation.status if calculation else None,
                calculation_pool_id=calculation.pool_id if calculation else None,
                unit_mass_kg=calculation.unit_mass_kg if calculation else None,
                total_mass_kg=calculation.total_mass_kg if calculation else None,
                correction_selected_pool_id=correction.selected_pool_id
                if correction
                else None,
                correction_note=correction.note if correction else None,
                has_manual_correction=bool(correction),
            )
        )

    return result


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

    poles = PoleExtractionService.extract(
        document_id=document_id,
        raw_rows=raw_rows,
    )

    POLES_BY_DOCUMENT[document_id] = poles

    document.status = "analyzed"
    DocumentRepository.save(document)

    return poles


@router.get("/{document_id}/poles", response_model=list[PoleRowView])
async def get_poles(document_id: str):
    document = DocumentRepository.get(document_id)

    if not document:
        raise HTTPException(status_code=404, detail="Dokumenttia ei löytynyt")

    return _build_pole_row_views(document_id)


@router.post("/{document_id}/match", response_model=list[PoleMatch])
async def match_document(document_id: str):
    document = DocumentRepository.get(document_id)

    if not document:
        raise HTTPException(status_code=404, detail="Dokumenttia ei löytynyt")

    poles = POLES_BY_DOCUMENT.get(document_id, [])

    if not poles:
        raise HTTPException(
            status_code=400,
            detail="Analysoituja pylväsrivejä ei löydy",
        )

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
        raise HTTPException(
            status_code=400,
            detail="Matchaus pitää tehdä ennen laskentaa",
        )

    pool_items = PolePoolRepository().load_all()

    calculations = MassCalculationService.calculate(
        poles,
        matches,
        pool_items,
    )

    CALCULATIONS_BY_DOCUMENT[document_id] = calculations

    document.status = "calculated"
    DocumentRepository.save(document)

    return calculations


@router.get("/{document_id}/calculations", response_model=list[MassCalculationResult])
async def get_calculations(document_id: str):
    return CALCULATIONS_BY_DOCUMENT.get(document_id, [])


@router.post("/{document_id}/ai-assist", response_model=AiAssistResult)
async def generate_ai_assist(document_id: str):
    document = DocumentRepository.get(document_id)

    if not document:
        raise HTTPException(status_code=404, detail="Dokumenttia ei löytynyt")

    poles = POLES_BY_DOCUMENT.get(document_id, [])

    if not poles:
        raise HTTPException(
            status_code=400,
            detail="Analysoituja pylväsrivejä ei löydy",
        )

    matches = MATCHES_BY_DOCUMENT.get(document_id, [])

    result = AiAssistService.analyze(
        document_id=document_id,
        rows=poles,
        matches=matches,
    )

    AI_ASSISTS_BY_DOCUMENT[document_id] = result

    return result


@router.get("/{document_id}/ai-assist", response_model=AiAssistResult)
async def get_ai_assist(document_id: str):
    document = DocumentRepository.get(document_id)

    if not document:
        raise HTTPException(status_code=404, detail="Dokumenttia ei löytynyt")

    result = AI_ASSISTS_BY_DOCUMENT.get(document_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail="AI-analyysiä ei löydy dokumentille",
        )

    return result