from pathlib import Path
import pandas as pd


class ExcelReaderService:
    @staticmethod
    def read(path: str) -> list[dict]:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Tiedostoa ei löytynyt: {path}")

        sheets = pd.read_excel(file_path, sheet_name=None)
        rows: list[dict] = []

        for sheet_name, df in sheets.items():
            df = df.fillna("")
            for index, row in df.iterrows():
                rows.append(
                    {
                        "source_sheet": sheet_name,
                        "source_row_number": int(index) + 2,
                        "data": row.to_dict(),
                    }
                )
        return rows