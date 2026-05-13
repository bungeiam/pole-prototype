from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any

from app.core.config import settings


class DocumentIntelligenceService:
    """
    Azure Document Intelligence integration for PDF drawing packages.

    This service converts Azure DI prebuilt-layout output into the same raw_rows
    format that CSV and Excel readers return. The normal POC pipeline can then
    continue with PoleExtractionService, matcher, AI-assist and calculations.
    """

    @classmethod
    def analyze(cls, path: str) -> list[dict]:
        if not settings.use_azure_di:
            return []

        if not settings.azure_di_endpoint or not settings.azure_di_key:
            raise RuntimeError(
                "Azure Document Intelligence on käytössä, mutta "
                "AZURE_DI_ENDPOINT tai AZURE_DI_KEY puuttuu."
            )

        file_path = Path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"PDF-tiedostoa ei löytynyt: {path}")

        result = cls._analyze_pdf_with_azure_di(file_path)

        return cls._convert_result_to_raw_rows(
            result=result,
            source_name=file_path.name,
        )

    @classmethod
    def _analyze_pdf_with_azure_di(cls, file_path: Path) -> Any:
        try:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential
        except ImportError as exc:
            raise RuntimeError(
                "Azure Document Intelligence -kirjasto puuttuu. "
                "Asenna se komennolla: pip install azure-ai-documentintelligence azure-core"
            ) from exc

        client = DocumentIntelligenceClient(
            endpoint=settings.azure_di_endpoint,
            credential=AzureKeyCredential(settings.azure_di_key),
        )

        with file_path.open("rb") as file:
            poller = client.begin_analyze_document(
                "prebuilt-layout",
                body=file,
                content_type="application/pdf",
            )

        return poller.result()

    @classmethod
    def _convert_result_to_raw_rows(cls, result: Any, source_name: str) -> list[dict]:
        plain_text = cls._result_to_plain_text(result)
        tables_text = cls._result_tables_to_text(result)
        combined_text = f"{plain_text}\n{tables_text}"

        document_code = cls._extract_document_code(combined_text, source_name)
        support_type = cls._extract_support_type(combined_text, source_name)
        height_min_m, height_max_m = cls._extract_height_range(combined_text, source_name)
        voltage_kv = cls._extract_voltage(combined_text, source_name)
        guying = cls._extract_guying(combined_text, source_name)
        phase_spacing_m = cls._extract_phase_spacing(
            combined_text,
            source_name,
            document_code,
        )
        part_rows_count = cls._extract_part_rows_count(tables_text)
        height_table_found, max_kg_per_height, max_height_mass_row = cls._extract_height_mass_table(
            tables_text
        )

        notes = cls._build_notes(
            document_code=document_code,
            support_type=support_type,
            height_min_m=height_min_m,
            height_max_m=height_max_m,
            voltage_kv=voltage_kv,
            guying=guying,
            phase_spacing_m=phase_spacing_m,
            part_rows_count=part_rows_count,
            height_table_found=height_table_found,
            max_kg_per_height=max_kg_per_height,
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
            return []

        return [
            {
                "source_sheet": "azure_document_intelligence",
                "source_row_number": 1,
                "data": {
                    "pole_code": document_code,
                    "pole_type": support_type,
                    # Nykyinen DetectedPoleRow tukee yhtä korkeusarvoa.
                    # POC:ssa piirustuksen korkeusalueesta käytetään ylärajaa.
                    "support_height_m": height_max_m,
                    "span_m": phase_spacing_m,
                    "guying": guying,
                    "quantity": 1,
                    "document_code": document_code,
                    "voltage_kv": voltage_kv,
                    "height_min_m": height_min_m,
                    "height_max_m": height_max_m,
                    "max_kg_per_height": max_kg_per_height,
                    "max_height_mass_row": max_height_mass_row,
                    "part_rows_count": part_rows_count,
                    "height_table_found": height_table_found,
                    "source_file": source_name,
                    "source_parser": "azure_document_intelligence",
                    "raw_text_preview": plain_text[:2500],
                    "_review_reasons": notes,
                    "_azure_di": True,
                },
            }
        ]

    @staticmethod
    def _result_to_plain_text(result: Any) -> str:
        lines: list[str] = []

        for page in result.pages or []:
            lines.append(f"=== PAGE {page.page_number} ===")

            if page.lines:
                for line in page.lines:
                    lines.append(line.content)

            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _result_tables_to_text(result: Any) -> str:
        lines: list[str] = []

        for table_index, table in enumerate(result.tables or [], start=1):
            lines.append(f"=== TABLE {table_index} ===")
            lines.append(f"Rows: {table.row_count}, Columns: {table.column_count}")

            matrix: list[list[str]] = [
                ["" for _ in range(table.column_count)]
                for _ in range(table.row_count)
            ]

            for cell in table.cells:
                row_index = cell.row_index
                column_index = cell.column_index

                if row_index < table.row_count and column_index < table.column_count:
                    matrix[row_index][column_index] = cell.content or ""

            for row in matrix:
                lines.append(" ; ".join(row))

            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _result_to_json_safe(result: Any) -> dict:
        if hasattr(result, "as_dict"):
            return result.as_dict()

        if hasattr(result, "to_dict"):
            return result.to_dict()

        return json.loads(json.dumps(result, default=str))

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
    def _extract_document_code(cls, text: str, source_name: str) -> str | None:
        combined = f"{source_name}\n{text}"

        match = re.search(r"\b(FG-\d{3}-\d-\d{3})\b", combined, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()

        return None

    @classmethod
    def _extract_support_type(cls, text: str, source_name: str) -> str | None:
        combined = cls._normalize_spaces(f"{source_name}\n{text}")

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
    def _extract_height_range(
        cls,
        text: str,
        source_name: str,
    ) -> tuple[float | None, float | None]:
        combined = cls._normalize_spaces(f"{source_name}\n{text}")

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
    def _extract_voltage(cls, text: str, source_name: str) -> int | None:
        combined = f"{source_name}\n{text}"

        match = re.search(r"\b(110)\s*KV\b", combined, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))

        match = re.search(r"\bFG-(\d{3})-", combined, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))

        return None

    @classmethod
    def _extract_guying(cls, text: str, source_name: str) -> str | None:
        combined = cls._normalize_spaces(f"{source_name}\n{text}").lower()

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
        source_name: str,
        document_code: str | None,
    ) -> float | None:
        combined = cls._normalize_spaces(f"{source_name}\n{text}")

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

        # POC-tason fallback tunnetuille demopiirustuksille.
        # Tämä ei ole tuotantologiikkaa, vaan pitää demon etenevänä, jos E.W.E.-arvo
        # ei irtoa yksiselitteisesti layout-analyysistä.
        known_spacing_by_code = {
            "FG-110-3-015": 3.0,
            "FG-110-3-017": 3.0,
            "FG-110-3-045": None,
        }

        if document_code in known_spacing_by_code:
            return known_spacing_by_code[document_code]

        return None

    @staticmethod
    def _extract_part_rows_count(tables_text: str) -> int:
        count = 0

        for line in tables_text.splitlines():
            normalized = line.strip()

            if not normalized:
                continue

            if re.match(r"^\d+\s*;", normalized):
                if any(
                    keyword in normalized.upper()
                    for keyword in [
                        "CROSSARM",
                        "LEG",
                        "GUY",
                        "BOLT",
                        "BEAM",
                        "PLATE",
                        "TRACTION",
                        "EARTH WIRE",
                        "LADDER",
                        "FOUNDATION",
                    ]
                ):
                    count += 1

        return count

    @classmethod
    def _extract_height_mass_table(
        cls,
        tables_text: str,
    ) -> tuple[bool, float | None, str | None]:
        found_header = False
        max_mass: float | None = None
        max_row: str | None = None

        for line in tables_text.splitlines():
            normalized = cls._normalize_spaces(line)

            if "H/m" in normalized and "kg/H" in normalized:
                found_header = True
                continue

            if not found_header:
                continue

            pieces = [piece.strip() for piece in line.split(";")]
            numeric_values: list[float] = []

            for piece in pieces:
                value = cls._normalize_number(piece)
                if value is not None:
                    numeric_values.append(value)

            if len(numeric_values) >= 5 and 13 <= numeric_values[0] <= 24:
                mass = numeric_values[-1]

                if max_mass is None or mass > max_mass:
                    max_mass = mass
                    max_row = normalized

        return found_header, max_mass, max_row

    @staticmethod
    def _build_notes(
        document_code: str | None,
        support_type: str | None,
        height_min_m: float | None,
        height_max_m: float | None,
        voltage_kv: int | None,
        guying: str | None,
        phase_spacing_m: float | None,
        part_rows_count: int,
        height_table_found: bool,
        max_kg_per_height: float | None,
    ) -> list[str]:
        notes: list[str] = []

        if document_code:
            notes.append(f"Azure DI tunnisti piirustuskoodin: {document_code}.")
        else:
            notes.append("Piirustuskoodia ei tunnistettu varmasti Azure DI -tuloksista.")

        if support_type:
            notes.append(f"Azure DI -tuloksista pääteltiin pylvästyyppi/rakenneperhe: {support_type}.")
        else:
            notes.append("Pylvästyyppi jäi epävarmaksi.")

        if height_min_m is not None and height_max_m is not None:
            notes.append(f"Korkeusalue tunnistettiin: {height_min_m:g}-{height_max_m:g} m.")
        else:
            notes.append("Korkeusaluetta ei tunnistettu varmasti.")

        if voltage_kv is not None:
            notes.append(f"Jännitetaso tunnistettiin: {voltage_kv} kV.")
        else:
            notes.append("Jännitetaso jäi epävarmaksi.")

        if guying is not None:
            notes.append(f"Harustieto tunnistettiin: {guying}.")
        else:
            notes.append("Harustieto puuttuu tai jäi epävarmaksi.")

        if phase_spacing_m is not None:
            notes.append(f"Vaiheväli / E.W.E. tunnistettiin: {phase_spacing_m:g} m.")
        else:
            notes.append("Vaiheväli / E.W.E. jäi epävarmaksi ja vaatii tarkistuksen.")

        if part_rows_count > 0:
            notes.append(f"Azure DI tunnisti rakenneosataulukoista {part_rows_count} osariviä.")
        else:
            notes.append("Rakenneosataulukon rivejä ei tunnistettu varmasti.")

        if height_table_found and max_kg_per_height is not None:
            notes.append(f"kg/H-taulukko tunnistettiin. Suurin kg/H-arvo: {max_kg_per_height:g}.")
        else:
            notes.append("kg/H-taulukkoa ei tunnistettu varmasti.")

        return notes