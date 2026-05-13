from pathlib import Path
import re


class PdfReaderService:
    """
    Basic PDF reader for the POC.

    This is intentionally not a full table recognition solution yet.
    The goal of this phase is to remove the old PDF stub and convert
    PDF text into the same raw_rows format that CSV/Excel readers use.

    Later this can be replaced or complemented by Azure Document Intelligence.
    """

    POLE_KEYWORDS = [
        "pylväs",
        "pylvas",
        "pylvästyyppi",
        "pylvastyyppi",
        "pylväsnumero",
        "pylvasnumero",
        "support",
        "pole",
        "harus",
        "harustus",
        "harustettu",
        "vaiheväli",
        "vaihevali",
        "phase spacing",
        "phase span",
        "height",
        "korkeus",
    ]

    @staticmethod
    def read(path: str) -> list[dict]:
        file_path = Path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"Tiedostoa ei löytynyt: {path}")

        text_pages = PdfReaderService._read_text_pages(file_path)
        rows: list[dict] = []

        for page_number, page_text in text_pages:
            page_rows = PdfReaderService._extract_rows_from_page_text(
                page_text=page_text,
                page_number=page_number,
            )
            rows.extend(page_rows)

        return rows

    @staticmethod
    def _read_text_pages(file_path: Path) -> list[tuple[int, str]]:
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise RuntimeError(
                "PyMuPDF puuttuu. Asenna se komennolla: pip install pymupdf"
            ) from exc

        pages: list[tuple[int, str]] = []

        with fitz.open(str(file_path)) as document:
            for page_index, page in enumerate(document, start=1):
                text = page.get_text("text") or ""
                pages.append((page_index, text))

        return pages

    @classmethod
    def _extract_rows_from_page_text(
        cls,
        page_text: str,
        page_number: int,
    ) -> list[dict]:
        lines = cls._normalize_lines(page_text)
        rows: list[dict] = []

        for line_index, line in enumerate(lines, start=1):
            if not cls._looks_like_pole_row(line):
                continue

            parsed = cls._parse_line(line)

            if not cls._has_any_core_value(parsed):
                continue

            parsed["raw_text"] = line

            rows.append(
                {
                    "source_sheet": f"pdf_page_{page_number}",
                    "source_row_number": line_index,
                    "data": parsed,
                }
            )

        return rows

    @staticmethod
    def _normalize_lines(text: str) -> list[str]:
        lines: list[str] = []

        for raw_line in text.splitlines():
            line = raw_line.strip()
            line = re.sub(r"\s+", " ", line)

            if line:
                lines.append(line)

        return lines

    @classmethod
    def _looks_like_pole_row(cls, line: str) -> bool:
        normalized = line.lower()

        if any(keyword in normalized for keyword in cls.POLE_KEYWORDS):
            return True

        # Basic fallback for table-like rows:
        # Example: P1 S110 18 4.5 guyed 2
        table_like_pattern = re.compile(
            r"\b[A-ZÅÄÖ]{1,5}\d{1,4}[A-ZÅÄÖ]?\b.*\b\d{1,2}([,.]\d+)?\b",
            re.IGNORECASE,
        )

        return bool(table_like_pattern.search(line))

    @classmethod
    def _parse_line(cls, line: str) -> dict:
        return {
            "pole_code": cls._extract_pole_code(line),
            "pole_type": cls._extract_pole_type(line),
            "support_height_m": cls._extract_height(line),
            "span_m": cls._extract_span(line),
            "guying": cls._extract_guying(line),
            "quantity": cls._extract_quantity(line),
        }

    @staticmethod
    def _has_any_core_value(data: dict) -> bool:
        return any(
            [
                data.get("pole_code"),
                data.get("pole_type"),
                data.get("support_height_m"),
                data.get("span_m"),
                data.get("guying"),
            ]
        )

    @staticmethod
    def _extract_with_patterns(line: str, patterns: list[str]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    @classmethod
    def _extract_pole_code(cls, line: str) -> str | None:
        patterns = [
            r"(?:pylväsnumero|pylvasnumero|support number|support no\.?|pole code|pylväs|pylvas|nro|no\.?)\s*[:=#-]?\s*([A-ZÅÄÖ0-9_.\-\/]+)",
        ]

        value = cls._extract_with_patterns(line, patterns)

        if value:
            return value

        # Fallback: first token like P1, 101, T-12 etc. at the beginning of row.
        match = re.search(r"^\s*([A-ZÅÄÖ]?\d+[A-ZÅÄÖ0-9_.\-\/]*)\b", line, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()

        return None

    @classmethod
    def _extract_pole_type(cls, line: str) -> str | None:
        patterns = [
            r"(?:pylvästyyppi|pylvastyyppi|support type|pole type|tyyppi|type)\s*[:=#-]?\s*([A-ZÅÄÖ]{1,6}\s*\d{1,4}[A-ZÅÄÖ]?)",
        ]

        value = cls._extract_with_patterns(line, patterns)

        if value:
            return value

        # Fallback: common compact technical type, e.g. S110, H60, B170.
        match = re.search(r"\b([A-ZÅÄÖ]{1,6}\d{1,4}[A-ZÅÄÖ]?)\b", line, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()

        return None

    @classmethod
    def _extract_height(cls, line: str) -> str | None:
        patterns = [
            r"(?:pylväskorkeus|pylvaskorkeus|support height|pole height|korkeus|height)\s*[:=#-]?\s*(\d{1,2}(?:[,.]\d+)?)\s*(?:m\b|metriä|metria)?",
            r"\b(\d{1,2}(?:[,.]\d+)?)\s*m\b",
        ]

        return cls._extract_with_patterns(line, patterns)

    @classmethod
    def _extract_span(cls, line: str) -> str | None:
        patterns = [
            r"(?:vaiheväli|vaihevali|phase spacing|phase span|span|jänneväli|jannevali)\s*[:=#-]?\s*(\d{1,5}(?:[,.]\d+)?)\s*(?:mm\b|m\b)?",
        ]

        return cls._extract_with_patterns(line, patterns)

    @staticmethod
    def _extract_guying(line: str) -> str | None:
        normalized = line.lower()

        false_patterns = [
            r"\bei\s+haruksia\b",
            r"\bharukseton\b",
            r"\bunguyed\b",
            r"\bno\s+guy",
        ]

        true_patterns = [
            r"\bharustettu\b",
            r"\bharustus\b",
            r"\bharus\b",
            r"\bguyed\b",
            r"\bguy\b",
            r"\bkyllä\b",
            r"\bkylla\b",
        ]

        for pattern in false_patterns:
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                return "unguyed"

        for pattern in true_patterns:
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                return "guyed"

        return None

    @classmethod
    def _extract_quantity(cls, line: str) -> str | None:
        patterns = [
            r"(?:määrä|maara|quantity|qty|kpl|lukumäärä|lukumaara)\s*[:=#-]?\s*(\d+)",
            r"\b(\d+)\s*kpl\b",
        ]

        return cls._extract_with_patterns(line, patterns)