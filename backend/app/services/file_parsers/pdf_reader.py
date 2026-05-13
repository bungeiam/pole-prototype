from __future__ import annotations

from pathlib import Path
import re

from app.services.ai.document_intelligence_service import DocumentIntelligenceService


class PdfReaderService:
    """
    PDF reader for the normal POC pipeline.

    Priority:
    1. Azure Document Intelligence, if enabled
    2. Local PyMuPDF text fallback

    Output format must match CSV/Excel readers:
    [
        {
            "source_sheet": "...",
            "source_row_number": 1,
            "data": {...}
        }
    ]
    """

    @classmethod
    def read(cls, path: str) -> list[dict]:
        try:
            azure_rows = DocumentIntelligenceService.analyze(path)
            if azure_rows:
                return azure_rows
        except Exception as exc:
            # POC fallback: if Azure DI fails, do not stop the whole pipeline.
            fallback_rows = cls._read_with_local_fallback(path)
            for row in fallback_rows:
                row["data"]["azure_di_error"] = str(exc)
            return fallback_rows

        return cls._read_with_local_fallback(path)

    @classmethod
    def _read_with_local_fallback(cls, path: str) -> list[dict]:
        file_path = Path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"PDF-tiedostoa ei löytynyt: {path}")

        text = cls._read_pdf_text(file_path)
        combined_text = f"{file_path.name}\n{text}"

        document_code = cls._extract_document_code(combined_text)
        support_type = cls._extract_support_type(combined_text)
        height_min_m, height_max_m = cls._extract_height_range(combined_text)
        voltage_kv = cls._extract_voltage(combined_text)
        guying = cls._extract_guying(combined_text)
        phase_spacing_m = cls._extract_phase_spacing(combined_text, document_code)

        if not any(
            [
                document_code,
                support_type,
                height_min_m is not None,
                height_max_m is not None,
                voltage_kv is not None,
                guying,
                phase_spacing_m is not None,
            ]
        ):
            return []

        notes = [
            "PDF luettiin paikallisella fallback-lukijalla.",
        ]

        if document_code:
            notes.append(f"Piirustuskoodi tunnistettu: {document_code}.")
        else:
            notes.append("Piirustuskoodia ei tunnistettu varmasti.")

        if support_type:
            notes.append(f"Pylvästyyppi tunnistettu: {support_type}.")
        else:
            notes.append("Pylvästyyppi jäi epävarmaksi.")

        if height_min_m is not None and height_max_m is not None:
            notes.append(f"Korkeusalue tunnistettu: {height_min_m:g}-{height_max_m:g} m.")
        else:
            notes.append("Korkeusaluetta ei tunnistettu varmasti.")

        if guying:
            notes.append(f"Harustieto tunnistettu: {guying}.")
        else:
            notes.append("Harustieto puuttuu tai jäi epävarmaksi.")

        if phase_spacing_m is not None:
            notes.append(f"Vaiheväli / E.W.E. tunnistettu: {phase_spacing_m:g} m.")
        else:
            notes.append("Vaiheväli / E.W.E. jäi epävarmaksi.")

        return [
            {
                "source_sheet": "pdf_local_fallback",
                "source_row_number": 1,
                "data": {
                    "pole_code": document_code,
                    "pole_type": support_type,
                    "support_height_m": height_max_m,
                    "span_m": phase_spacing_m,
                    "guying": guying,
                    "quantity": 1,
                    "document_code": document_code,
                    "voltage_kv": voltage_kv,
                    "height_min_m": height_min_m,
                    "height_max_m": height_max_m,
                    "source_file": file_path.name,
                    "source_parser": "pymupdf_fallback",
                    "raw_text_preview": text[:2500],
                    "_review_reasons": notes,
                    "_azure_di": False,
                },
            }
        ]

    @staticmethod
    def _read_pdf_text(file_path: Path) -> str:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError(
                "PyMuPDF puuttuu. Asenna se komennolla: pip install pymupdf"
            ) from exc

        parts: list[str] = []

        with fitz.open(str(file_path)) as document:
            for page in document:
                parts.append(page.get_text("text") or "")

        return "\n".join(parts)

    @staticmethod
    def _normalize_number(value: str | None) -> float | None:
        if value is None:
            return None

        cleaned = value.strip().replace(",", ".")

        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def _normalize_spaces(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @classmethod
    def _extract_document_code(cls, text: str) -> str | None:
        match = re.search(r"\b(FG-\d{3}-\d-\d{3})\b", text, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
        return None

    @classmethod
    def _extract_support_type(cls, text: str) -> str | None:
        combined = cls._normalize_spaces(text)

        patterns = [
            r"\bGUYED\s+SUPPORT\s+TYPE\s+(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)\b",
            r"\bOHTL\s+LINE\s+GUYED\s+SUPPORT\s+TYPE\s+(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)\b",
            r"\bTYPE\s+(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)\b",
            r"\bSUPPORT\s+(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)\b",
            r"\b(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)\s*,?\s*13\s*[-–]\s*24",
            r"\b(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)13\s*[-–]\s*24",
        ]

        for pattern in patterns:
            match = re.search(pattern, combined, flags=re.IGNORECASE)
            if match:
                return match.group(1).upper()

        return None

    @classmethod
    def _extract_height_range(cls, text: str) -> tuple[float | None, float | None]:
        combined = cls._normalize_spaces(text)

        patterns = [
            r"\b(?:TYPE|SUPPORT)?\s*(?:1HD|1H|2HD|2H|2HKD|2HK|1/2HD)?\s*,?\s*(\d{2})\s*[-–]\s*(\d{2})\s*M\b",
            r"\b(?:TYPE|SUPPORT)?\s*(?:1HD|1H|2HD|2H|2HKD|2HK|1/2HD)?\s*(\d{2})\s*[-–]\s*(\d{2})\s*m\b",
            r"\b(\d{2})\s*[-–]\s*(\d{2})\s*M\b",
            r"\b(\d{2})\s*[-–]\s*(\d{2})\s*m\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, combined, flags=re.IGNORECASE)
            if match:
                return float(match.group(1)), float(match.group(2))

        return None, None

    @classmethod
    def _extract_voltage(cls, text: str) -> int | None:
        match = re.search(r"\b(110)\s*KV\b", text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))

        match = re.search(r"\bFG-(\d{3})-", text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))

        return None

    @classmethod
    def _extract_guying(cls, text: str) -> str | None:
        combined = cls._normalize_spaces(text).lower()

        if "unguyed" in combined or "non-guyed" in combined:
            return "unguyed"

        guying_indicators = [
            "guyed support",
            "guy anchor",
            "guy rope",
            "guy ropes",
            "tension of guyes",
            "direction of the guyes",
            "fixing part for guy",
            "fixing part for guyes",
            "2-guy anchors",
        ]

        if any(indicator in combined for indicator in guying_indicators):
            return "guyed"

        return None

    @classmethod
    def _extract_phase_spacing(
        cls,
        text: str,
        document_code: str | None,
    ) -> float | None:
        combined = cls._normalize_spaces(text)

        patterns = [
            r"E\.?\s*W\.?\s*E\.?\s*[:=,_ -]*\s*(\d+[,.]\d+)",
            r"EARTH\s+WIRE\s+EXTENSION\s+(\d+[,.]?\d*)\s*m",
            r"EARTH\s+WIRE\s+EXTENSION,\s*(\d+[,.]?\d*)\s*m",
        ]

        for pattern in patterns:
            match = re.search(pattern, combined, flags=re.IGNORECASE)
            if match:
                value = cls._normalize_number(match.group(1))
                if value is not None:
                    return value

        known_spacing_by_code = {
            "FG-110-3-015": 3.0,
            "FG-110-3-017": 3.0,
            "FG-110-3-045": None,
        }

        if document_code in known_spacing_by_code:
            return known_spacing_by_code[document_code]

        return None