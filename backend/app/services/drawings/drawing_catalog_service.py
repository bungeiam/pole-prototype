from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import re

from app.core.config import settings
from app.services.ai.document_intelligence_service import DocumentIntelligenceService


@dataclass
class DrawingCatalogItem:
    source_file: str
    source_path: str
    document_code: str | None
    support_type: str | None
    height_min_m: float | None
    height_max_m: float | None
    voltage_kv: int | None
    guying: str | None
    phase_spacing_m: float | None
    max_kg_per_height: float | None
    max_height_mass_row: str | None
    part_rows_count: int
    height_table_found: bool
    confidence: float
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DrawingCatalogService:
    """
    Builds a package-specific drawing catalog from PDF drawings uploaded
    together with one support list.

    Important:
    - The catalog belongs only to the current package.
    - The main drawing identity must be detected from filename/title first.
    - Component drawing codes inside the PDF must not override the main drawing code.
    """

    @classmethod
    def build_catalog(cls, pdf_paths: list[str]) -> list[DrawingCatalogItem]:
        catalog: list[DrawingCatalogItem] = []

        for pdf_path in pdf_paths:
            path = Path(pdf_path)

            if not path.exists():
                continue

            item = cls.analyze_pdf(path)

            if item:
                catalog.append(item)

        return catalog

    @classmethod
    def analyze_pdf(cls, path: Path) -> DrawingCatalogItem | None:
        if settings.use_azure_di:
            try:
                return cls._analyze_pdf_with_azure_di(path)
            except Exception as exc:
                fallback = cls._analyze_pdf_with_local_text(path)
                if fallback:
                    fallback.notes.insert(
                        0,
                        f"Azure DI epäonnistui, käytettiin fallback-lukua: {exc}",
                    )
                return fallback

        return cls._analyze_pdf_with_local_text(path)

    @classmethod
    def _analyze_pdf_with_azure_di(cls, path: Path) -> DrawingCatalogItem | None:
        if not settings.azure_di_endpoint or not settings.azure_di_key:
            raise RuntimeError("Azure DI -asetukset puuttuvat.")

        result = DocumentIntelligenceService._analyze_pdf_with_azure_di(path)
        plain_text = DocumentIntelligenceService._result_to_plain_text(result)
        tables_text = DocumentIntelligenceService._result_tables_to_text(result)

        return cls._build_item_from_text(
            source_file=path.name,
            source_path=str(path),
            plain_text=plain_text,
            tables_text=tables_text,
            parser_name="azure_document_intelligence",
        )

    @classmethod
    def _analyze_pdf_with_local_text(cls, path: Path) -> DrawingCatalogItem | None:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF puuttuu. Asenna: pip install pymupdf") from exc

        parts: list[str] = []

        with fitz.open(str(path)) as document:
            for page in document:
                parts.append(page.get_text("text") or "")

        return cls._build_item_from_text(
            source_file=path.name,
            source_path=str(path),
            plain_text="\n".join(parts),
            tables_text="",
            parser_name="pymupdf_fallback",
        )

    @classmethod
    def _build_item_from_text(
        cls,
        source_file: str,
        source_path: str,
        plain_text: str,
        tables_text: str,
        parser_name: str,
    ) -> DrawingCatalogItem | None:
        title_area = cls._get_title_area(plain_text)
        combined = f"{source_file}\n{title_area}\n{plain_text}\n{tables_text}"

        document_code = cls._extract_main_document_code(
            source_file=source_file,
            title_area=title_area,
            full_text=combined,
        )

        support_type = cls._extract_main_support_type(
            source_file=source_file,
            title_area=title_area,
            full_text=combined,
        )

        height_min_m, height_max_m = cls._extract_main_height_range(
            source_file=source_file,
            title_area=title_area,
            full_text=combined,
        )

        voltage_kv = cls._extract_voltage(combined)
        guying = cls._extract_guying(combined)

        phase_spacing_m = cls._extract_phase_spacing(
            text=combined,
            document_code=document_code,
            source_file=source_file,
        )

        part_rows_count = DocumentIntelligenceService._extract_part_rows_count(tables_text)
        height_table_found, max_kg_per_height, max_height_mass_row = (
            DocumentIntelligenceService._extract_height_mass_table(tables_text)
        )

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
            return None

        notes = [
            f"Piirustus analysoitiin parserilla: {parser_name}.",
        ]

        if document_code:
            notes.append(f"Pääpiirustuskoodi tunnistettiin: {document_code}.")
        else:
            notes.append("Pääpiirustuskoodia ei tunnistettu varmasti.")

        if support_type:
            notes.append(f"Pylvästyyppi/rakenneperhe tunnistettiin: {support_type}.")
        else:
            notes.append("Pylvästyyppi/rakenneperhe jäi epävarmaksi.")

        if height_min_m is not None and height_max_m is not None:
            notes.append(f"Korkeusalue tunnistettiin: {height_min_m:g}-{height_max_m:g} m.")
        else:
            notes.append("Korkeusaluetta ei tunnistettu varmasti.")

        if voltage_kv:
            notes.append(f"Jännitetaso tunnistettiin: {voltage_kv} kV.")
        else:
            notes.append("Jännitetasoa ei tunnistettu varmasti.")

        if guying:
            notes.append(f"Harustieto tunnistettiin: {guying}.")
        else:
            notes.append("Harustieto jäi epävarmaksi.")

        if phase_spacing_m is not None:
            notes.append(f"Vaiheväli / E.W.E. tunnistettiin: {phase_spacing_m:g} m.")
        else:
            notes.append("Vaiheväli / E.W.E. jäi epävarmaksi.")

        if height_table_found and max_kg_per_height is not None:
            notes.append(f"kg/H-taulukko tunnistettiin. Suurin kg/H-arvo: {max_kg_per_height:g}.")
        else:
            notes.append("kg/H-taulukkoa ei tunnistettu varmasti.")

        score_parts = [
            document_code is not None,
            support_type is not None,
            height_min_m is not None and height_max_m is not None,
            voltage_kv is not None,
            guying is not None,
            phase_spacing_m is not None,
            part_rows_count > 0,
            height_table_found,
        ]

        confidence = round(sum(1 for item in score_parts if item) / len(score_parts), 2)

        return DrawingCatalogItem(
            source_file=source_file,
            source_path=source_path,
            document_code=document_code,
            support_type=support_type,
            height_min_m=height_min_m,
            height_max_m=height_max_m,
            voltage_kv=voltage_kv,
            guying=guying,
            phase_spacing_m=phase_spacing_m,
            max_kg_per_height=max_kg_per_height,
            max_height_mass_row=max_height_mass_row,
            part_rows_count=part_rows_count,
            height_table_found=height_table_found,
            confidence=confidence,
            notes=notes,
        )

    @staticmethod
    def _normalize_spaces(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _get_title_area(text: str) -> str:
        """
        Uses the beginning and title-related lines of the PDF text.
        This avoids selecting component drawing codes from the parts list.
        """

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        title_lines: list[str] = []
        for index, line in enumerate(lines):
            upper_line = line.upper()

            if "TITLE" in upper_line:
                title_lines.extend(lines[index : index + 8])

            if "TABLE OF CONTENTS" in upper_line:
                title_lines.extend(lines[index : index + 20])

            if "GENERAL DRAWING" in upper_line:
                title_lines.extend(lines[max(0, index - 8) : index + 8])

            if "SUPPORT" in upper_line and ("13" in upper_line or "24" in upper_line):
                title_lines.append(line)

        title_area = "\n".join(title_lines)

        # Also include the first part of the document because table of contents
        # often contains the main support type.
        first_lines = "\n".join(lines[:120])

        return f"{first_lines}\n{title_area}"


    @classmethod
    def _extract_main_document_code(
        cls,
        source_file: str,
        title_area: str,
        full_text: str,
    ) -> str | None:
        """
        Main document code must be selected from filename or title area first.

        Important:
        Python regex word boundary \\b does not work reliably here because
        uploaded files may be stored as 001_FG-110-3-015_..., and underscore
        is treated as a word character. Therefore filename matching is done
        without \\b boundaries.
        """

        filename_match = re.search(
            r"(FG-\d{3}-\d-\d{3})",
            source_file,
            flags=re.IGNORECASE,
        )
        if filename_match:
            return filename_match.group(1).upper()

        title_match = re.search(
            r"(FG-\d{3}-\d-\d{3})",
            title_area,
            flags=re.IGNORECASE,
        )
        if title_match:
            return title_match.group(1).upper()

        # Last fallback: use the first FG code from full text.
        # This may find component drawing codes, so it is intentionally last.
        full_match = re.search(
            r"(FG-\d{3}-\d-\d{3})",
            full_text,
            flags=re.IGNORECASE,
        )
        if full_match:
            return full_match.group(1).upper()

        return None


    @classmethod
    def _extract_main_support_type(
        cls,
        source_file: str,
        title_area: str,
        full_text: str,
    ) -> str | None:
        """
        Support type is primarily read from filename/title, not from component rows.

        Filenames may contain patterns such as:
        - FG-110-3-015_1H13-24m...
        - FG-110-3-045_1HD...
        """

        filename = source_file.upper()

        filename_patterns = [
            r"(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)\s*13\s*[-?]?\s*24\s*M?",
            r"[_\-\s](1HD|1H|2HD|2H|2HKD|2HK|1/2HD)(?=[_\-\s\.])",
        ]

        for pattern in filename_patterns:
            match = re.search(pattern, filename, flags=re.IGNORECASE)
            if match:
                return match.group(1).upper()

        search_blocks = [
            title_area,
            full_text,
        ]

        patterns = [
            r"(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)\s*13\s*[-?]\s*24\s*M?",
            r"(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)\s*,?\s*13\s*[-?]\s*24\s*M?",
            r"GUYED\s+SUPPORT\s+TYPE\s+(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)",
            r"SUPPORT\s+(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)",
            r"TYPE\s+(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)",
        ]

        for block in search_blocks:
            normalized = cls._normalize_spaces(block).upper()

            for pattern in patterns:
                match = re.search(pattern, normalized, flags=re.IGNORECASE)
                if match:
                    return match.group(1).upper()

        return None


    @classmethod
    def _extract_main_height_range(
        cls,
        source_file: str,
        title_area: str,
        full_text: str,
    ) -> tuple[float | None, float | None]:
        """
        Height range is read from filename/title first.

        Example filename:
        FG-110-3-015_1H13-24m_N_ALL_PAGES_M5.PDF
        """

        search_blocks = [
            source_file,
            title_area,
            full_text,
        ]

        patterns = [
            r"(?:1HD|1H|2HD|2H|2HKD|2HK|1/2HD)?\s*,?\s*(\d{2})\s*[-?]\s*(\d{2})\s*M",
            r"(?:1HD|1H|2HD|2H|2HKD|2HK|1/2HD)?\s*(\d{2})\s*[-?]\s*(\d{2})\s*m",
            r"(\d{2})\s*[-?]\s*(\d{2})\s*M",
            r"(\d{2})\s*[-?]\s*(\d{2})\s*m",
        ]

        for block in search_blocks:
            normalized = cls._normalize_spaces(block).upper()

            for pattern in patterns:
                match = re.search(pattern, normalized, flags=re.IGNORECASE)
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
        source_file: str,
    ) -> float | None:
        combined = cls._normalize_spaces(f"{source_file}\n{text}")

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
            "FG-110-3-017": 3.6,
            "FG-110-3-045": 4.0,
        }

        if document_code in known_spacing_by_code:
            return known_spacing_by_code[document_code]

        return None

    @staticmethod
    def _normalize_number(value: str | None) -> float | None:
        if value is None:
            return None

        cleaned = value.strip().replace(",", ".")

        try:
            return float(cleaned)
        except ValueError:
            return None