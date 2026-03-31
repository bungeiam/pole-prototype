from pathlib import Path

import pandas as pd

from app.models.match import PolePoolItem


class PolePoolRepository:
    def __init__(self, csv_path: str = "data/pole_pool.csv") -> None:
        self.csv_path = Path(csv_path)

    @staticmethod
    def _to_optional_float(value) -> float | None:
        if pd.isna(value):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_optional_str(value) -> str | None:
        if pd.isna(value):
            return None
        text = str(value).strip()
        return text or None

    def load_all(self) -> list[PolePoolItem]:
        if not self.csv_path.exists():
            return []

        df = pd.read_csv(self.csv_path)

        items: list[PolePoolItem] = []

        for _, row in df.iterrows():
            items.append(
                PolePoolItem(
                    pool_id=str(row["pool_id"]),
                    pole_type=str(row["pole_type"]),
                    support_height_m=float(row["support_height_m"]),
                    max_span_m=self._to_optional_float(row.get("max_span_m")),
                    guying=self._to_optional_str(row.get("guying")),
                    unit_mass_kg=float(row["unit_mass_kg"]),
                    material_code=self._to_optional_str(row.get("material_code")),

                    # ✅ UUSI: vaihevälikentät (fallback-safe)
                    phase_spacing_left_mm=self._to_optional_float(row.get("phase_spacing_left_mm")),
                    phase_spacing_right_mm=self._to_optional_float(row.get("phase_spacing_right_mm")),
                    phase_spacing_text=self._to_optional_str(row.get("phase_spacing_text")),
                )
            )

        return items