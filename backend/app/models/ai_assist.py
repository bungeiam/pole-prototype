from pydantic import BaseModel, Field


class AiAssistItem(BaseModel):
    row_id: str
    suggested_pole_type: str | None = None
    suggested_guying: str | None = None
    suggested_phase_spacing_m: float | None = None
    confidence: float = 0.0
    requires_manual_review: bool = True
    reasons: list[str] = Field(default_factory=list)


class AiAssistResult(BaseModel):
    document_id: str
    items: list[AiAssistItem] = Field(default_factory=list)
    summary: str | None = None