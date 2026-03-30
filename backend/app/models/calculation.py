from typing import Literal
from pydantic import BaseModel


CalculationStatus = Literal["calculated", "incomplete"]


class MassCalculationResult(BaseModel):
    row_id: str
    pool_id: str | None = None
    quantity: int = 0
    unit_mass_kg: float | None = None
    total_mass_kg: float | None = None
    status: CalculationStatus = "incomplete"