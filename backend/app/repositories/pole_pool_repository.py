from pathlib import Path
import pandas as pd
from app.models.match import PolePoolItem


class PolePoolRepository:
    def __init__(self, csv_path: str = "data/pole_pool.csv") -> None:
        self.csv_path = Path(csv_path)

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
                    max_span_m=float(row["max_span_m"]) if pd.notna(row.get("max_span_m")) else None,
                    guying=str(row["guying"]) if pd.notna(row.get("guying")) else None,
                    unit_mass_kg=float(row["unit_mass_kg"]),
                    material_code=str(row["material_code"]) if pd.notna(row.get("material_code")) else None,
                )
            )
        return items