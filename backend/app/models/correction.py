from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class UserCorrection(BaseModel):
    correction_id: str
    row_id: str
    corrected_fields: dict[str, Any] = Field(default_factory=dict)
    selected_pool_id: str | None = None
    note: str | None = None
    corrected_at: datetime


class CorrectionRequest(BaseModel):
    corrected_fields: dict[str, Any] = Field(default_factory=dict)
    selected_pool_id: str | None = None
    note: str | None = None