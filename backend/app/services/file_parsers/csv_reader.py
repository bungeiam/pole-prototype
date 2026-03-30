from pathlib import Path
import pandas as pd


class CsvReaderService:
    @staticmethod
    def read(path: str) -> list[dict]:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Tiedostoa ei löytynyt: {path}")

        df = pd.read_csv(file_path).fillna("")
        rows: list[dict] = []

        for index, row in df.iterrows():
            rows.append(
                {
                    "source_sheet": "csv",
                    "source_row_number": int(index) + 2,
                    "data": row.to_dict(),
                }
            )
        return rows