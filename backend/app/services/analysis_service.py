from pathlib import Path
from app.services.file_parsers.excel_reader import ExcelReaderService
from app.services.file_parsers.csv_reader import CsvReaderService
from app.services.file_parsers.pdf_reader import PdfReaderService


class AnalysisService:
    @staticmethod
    def extract_raw_rows(path: str) -> list[dict]:
        suffix = Path(path).suffix.lower()

        if suffix in [".xlsx", ".xls"]:
            return ExcelReaderService.read(path)
        if suffix == ".csv":
            return CsvReaderService.read(path)
        if suffix == ".pdf":
            return PdfReaderService.read(path)

        raise ValueError(f"Tiedostotyyppiä ei tueta vielä: {suffix}")