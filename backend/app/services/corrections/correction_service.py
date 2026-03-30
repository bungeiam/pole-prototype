import uuid
from datetime import datetime
from app.models.correction import UserCorrection
from app.repositories.in_memory_store import CORRECTIONS_BY_ROW, POLES_BY_DOCUMENT


class CorrectionService:
    EDITABLE_FIELDS = {
        "pole_code",
        "pole_type",
        "support_height_m",
        "span_m",
        "guying",
        "quantity",
    }

    @staticmethod
    def save(row_id: str, corrected_fields: dict, selected_pool_id: str | None, note: str | None) -> UserCorrection:
        correction = UserCorrection(
            correction_id=str(uuid.uuid4()),
            row_id=row_id,
            corrected_fields=corrected_fields,
            selected_pool_id=selected_pool_id,
            note=note,
            corrected_at=datetime.utcnow(),
        )
        CORRECTIONS_BY_ROW[row_id] = correction
        CorrectionService.apply_to_row(row_id, corrected_fields)
        return correction

    @staticmethod
    def get(row_id: str) -> UserCorrection | None:
        return CORRECTIONS_BY_ROW.get(row_id)

    @staticmethod
    def apply_to_row(row_id: str, corrected_fields: dict) -> None:
        for document_id, rows in POLES_BY_DOCUMENT.items():
            for row in rows:
                if row.row_id == row_id:
                    for field_name, value in corrected_fields.items():
                        if field_name not in CorrectionService.EDITABLE_FIELDS:
                            continue
                        if hasattr(row, field_name):
                            setattr(row, field_name, value)

                    if row.pole_type and row.support_height_m:
                        row.review_status = "ok"
                        row.confidence = max(row.confidence, 0.95)
                    else:
                        row.review_status = "review"
                    return