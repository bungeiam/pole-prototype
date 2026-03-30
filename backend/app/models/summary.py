from pydantic import BaseModel, Field


class SummaryRow(BaseModel):
    pool_id: str | None = None
    pole_type: str | None = None
    quantity: int = 0
    unit_mass_kg: float | None = None
    total_mass_kg: float | None = None


class ReviewItem(BaseModel):
    row_id: str
    source_row_number: int | None = None
    pole_code: str | None = None
    pole_type: str | None = None
    review_status: str
    match_status: str | None = None
    calculation_status: str | None = None
    suggested_pool_id: str | None = None
    selected_pool_id: str | None = None
    reasons: list[str] = Field(default_factory=list)


class DocumentSummary(BaseModel):
    document_id: str
    document_status: str
    total_detected_rows: int
    total_matches: int
    matched_rows: int
    ambiguous_rows: int
    unmatched_rows: int
    calculated_rows: int
    incomplete_rows: int
    total_quantity: int
    total_mass_kg: float
    rows_by_pool: list[SummaryRow] = Field(default_factory=list)
    review_items: list[ReviewItem] = Field(default_factory=list)