from typing import Any, Literal

from pydantic import BaseModel, Field


ReviewStatus = Literal["ok", "review", "missing_data"]


class DetectedPoleRow(BaseModel):
    row_id: str
    document_id: str
    source_sheet: str | None = None
    source_row_number: int | None = None
    pole_code: str | None = None
    pole_type: str | None = None
    support_height_m: float | None = None
    span_m: float | None = None
    guying: str | None = None
    quantity: int = 1
    raw_data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    review_status: ReviewStatus = "review"


class PoleRowView(DetectedPoleRow):
    match_status: str | None = None
    match_score: float | None = None
    match_reason: str | None = None
    suggested_pool_id: str | None = None
    alternative_pool_ids: list[str] = Field(default_factory=list)

    calculation_status: str | None = None
    calculation_pool_id: str | None = None
    unit_mass_kg: float | None = None
    total_mass_kg: float | None = None

    correction_selected_pool_id: str | None = None
    correction_note: str | None = None
    has_manual_correction: bool = False