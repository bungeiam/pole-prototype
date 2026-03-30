from fastapi import APIRouter, HTTPException
from app.models.correction import CorrectionRequest, UserCorrection
from app.repositories.in_memory_store import POLES_BY_DOCUMENT
from app.services.corrections.correction_service import CorrectionService


router = APIRouter(prefix="/api/poles", tags=["poles"])


@router.post("/{row_id}/corrections", response_model=UserCorrection)
async def save_correction(row_id: str, payload: CorrectionRequest):
    row_exists = False
    for _, rows in POLES_BY_DOCUMENT.items():
        if any(row.row_id == row_id for row in rows):
            row_exists = True
            break

    if not row_exists:
        raise HTTPException(status_code=404, detail="Pylväsriviä ei löytynyt")

    return CorrectionService.save(
        row_id=row_id,
        corrected_fields=payload.corrected_fields,
        selected_pool_id=payload.selected_pool_id,
        note=payload.note,
    )


@router.get("/{row_id}/corrections", response_model=UserCorrection | None)
async def get_correction(row_id: str):
    return CorrectionService.get(row_id)