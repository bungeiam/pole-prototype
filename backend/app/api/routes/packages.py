from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.ai_assist import AiAssistResult
from app.models.calculation import MassCalculationResult
from app.models.match import PoleMatch
from app.models.pole import DetectedPoleRow, PoleRowView
from app.models.summary import DocumentSummary
from app.repositories.in_memory_store import (
    AI_ASSISTS_BY_DOCUMENT,
    CALCULATIONS_BY_DOCUMENT,
    CORRECTIONS_BY_ROW,
    MATCHES_BY_DOCUMENT,
    POLES_BY_DOCUMENT,
)
from app.repositories.pole_pool_repository import PolePoolRepository
from app.services.ai.ai_assist_service import AiAssistService
from app.services.calculations.mass_calculation_service import MassCalculationService
from app.services.extraction.pole_extraction_service import PoleExtractionService
from app.services.matching.pole_matcher_service import PoleMatcherService
from app.services.packages.package_analysis_service import PackageAnalysisService
from app.services.packages.package_service import PackageService
from app.services.summary.summary_service import SummaryService


router = APIRouter(prefix="/api/packages", tags=["packages"])


def _build_pole_row_views(package_id: str) -> list[PoleRowView]:
    poles = POLES_BY_DOCUMENT.get(package_id, [])
    matches = MATCHES_BY_DOCUMENT.get(package_id, [])
    calculations = CALCULATIONS_BY_DOCUMENT.get(package_id, [])

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
                correction_selected_pool_id=correction.selected_pool_id if correction else None,
                correction_note=correction.note if correction else None,
                has_manual_correction=bool(correction),
            )
        )

    return result


@router.post("/upload")
async def upload_package(
    support_list: UploadFile = File(...),
    drawings: list[UploadFile] = File(default=[]),
):
    try:
        return PackageService.create_package(
            support_list=support_list,
            drawings=drawings,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("")
async def list_packages():
    return PackageService.list_all()


@router.get("/{package_id}")
async def get_package(package_id: str):
    package = PackageService.get(package_id)

    if not package:
        raise HTTPException(status_code=404, detail="Tarjouspakettia ei löytynyt")

    return package


@router.post("/{package_id}/analyze", response_model=list[DetectedPoleRow])
async def analyze_package(package_id: str):
    package = PackageService.get(package_id)

    if not package:
        raise HTTPException(status_code=404, detail="Tarjouspakettia ei löytynyt")

    try:
        raw_rows, _drawing_catalog = PackageAnalysisService.build_enriched_raw_rows(package_id)

        poles = PoleExtractionService.extract(
            document_id=package_id,
            raw_rows=raw_rows,
        )

        POLES_BY_DOCUMENT[package_id] = poles

        package["status"] = "analyzed"
        PackageService.save(package)

        return poles
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{package_id}/poles", response_model=list[PoleRowView])
async def get_package_poles(package_id: str):
    package = PackageService.get(package_id)

    if not package:
        raise HTTPException(status_code=404, detail="Tarjouspakettia ei löytynyt")

    return _build_pole_row_views(package_id)


@router.post("/{package_id}/match", response_model=list[PoleMatch])
async def match_package(package_id: str):
    package = PackageService.get(package_id)

    if not package:
        raise HTTPException(status_code=404, detail="Tarjouspakettia ei löytynyt")

    poles = POLES_BY_DOCUMENT.get(package_id, [])

    if not poles:
        raise HTTPException(status_code=400, detail="Analysoituja pylväsrivejä ei löydy")

    pool_items = PolePoolRepository().load_all()
    matches = PoleMatcherService.match_rows(poles, pool_items)

    MATCHES_BY_DOCUMENT[package_id] = matches

    package["status"] = "matched"
    PackageService.save(package)

    return matches


@router.post("/{package_id}/calculate", response_model=list[MassCalculationResult])
async def calculate_package(package_id: str):
    package = PackageService.get(package_id)

    if not package:
        raise HTTPException(status_code=404, detail="Tarjouspakettia ei löytynyt")

    poles = POLES_BY_DOCUMENT.get(package_id, [])
    matches = MATCHES_BY_DOCUMENT.get(package_id, [])

    if not poles or not matches:
        raise HTTPException(status_code=400, detail="Matchaus pitää tehdä ennen laskentaa")

    pool_items = PolePoolRepository().load_all()

    calculations = MassCalculationService.calculate(
        poles,
        matches,
        pool_items,
    )

    CALCULATIONS_BY_DOCUMENT[package_id] = calculations

    package["status"] = "calculated"
    PackageService.save(package)

    return calculations


@router.get("/{package_id}/summary", response_model=DocumentSummary)
async def get_package_summary(package_id: str):
    package = PackageService.get(package_id)

    if not package:
        raise HTTPException(status_code=404, detail="Tarjouspakettia ei löytynyt")

    return SummaryService.build(
        document_id=package_id,
        document_status=package.get("status", "uploaded"),
    )


@router.post("/{package_id}/ai-assist", response_model=AiAssistResult)
async def generate_package_ai_assist(package_id: str):
    package = PackageService.get(package_id)

    if not package:
        raise HTTPException(status_code=404, detail="Tarjouspakettia ei löytynyt")

    poles = POLES_BY_DOCUMENT.get(package_id, [])

    if not poles:
        raise HTTPException(status_code=400, detail="Analysoituja pylväsrivejä ei löydy")

    matches = MATCHES_BY_DOCUMENT.get(package_id, [])

    result = AiAssistService.analyze(
        document_id=package_id,
        rows=poles,
        matches=matches,
    )

    AI_ASSISTS_BY_DOCUMENT[package_id] = result

    return result


@router.get("/{package_id}/ai-assist", response_model=AiAssistResult)
async def get_package_ai_assist(package_id: str):
    package = PackageService.get(package_id)

    if not package:
        raise HTTPException(status_code=404, detail="Tarjouspakettia ei löytynyt")

    result = AI_ASSISTS_BY_DOCUMENT.get(package_id)

    if not result:
        raise HTTPException(status_code=404, detail="AI-analyysiä ei löydy tarjouspaketille")

    return result