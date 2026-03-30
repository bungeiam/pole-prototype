from typing import Literal
from pydantic import BaseModel, Field


MatchStatus = Literal["matched", "ambiguous", "unmatched"]


class PolePoolItem(BaseModel):
    pool_id: str
    pole_type: str
    support_height_m: float
    max_span_m: float | None = None
    guying: str | None = None
    unit_mass_kg: float
    material_code: str | None = None


class PoleMatch(BaseModel):
    row_id: str
    suggested_pool_id: str | None = None
    score: float = 0.0
    reason: str = ""
    alternatives: list[str] = Field(default_factory=list)
    status: MatchStatus = "unmatched"