from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


class SupportListReaderService:
    """
    Reads a customer's support list Excel file and converts rows into raw_rows.

    The support list is the master data in the package flow. Drawing PDFs are
    used later to enrich these rows; PDFs should not create pole rows by themselves.
    """

    SUPPORT_SHEET_NAME = "support list"

    @classmethod
    def read(cls, path: str) -> list[dict]:
        file_path = Path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"Pylväsluetteloa ei löytynyt: {path}")

        sheets = pd.read_excel(file_path, sheet_name=None, header=None)
        support_sheet_name = cls._find_support_sheet_name(sheets)

        if support_sheet_name is None:
            raise ValueError("Excelistä ei löytynyt Support list -välilehteä.")

        df = sheets[support_sheet_name].fillna("")
        header_row_index = cls._find_header_row_index(df)

        if header_row_index is None:
            raise ValueError("Support list -välilehdeltä ei löytynyt otsikkoriviä.")

        rows: list[dict] = []

        # Tässä tiedostotyypissä otsikot ovat kahdella rivillä:
        # header_row_index     = pääotsikot, esim. Tower number, Tower, Support, H / m
        # header_row_index + 1 = alaotsikot, esim. Work, type, drawing no, document code, L, R
        # Varsinainen data alkaa kaksi riviä otsikkorivin jälkeen.
        first_data_row_index = header_row_index + 2

        for index in range(first_data_row_index, len(df)):
            row = df.iloc[index]
            data = cls._parse_support_list_row(row)

            if not data:
                continue

            rows.append(
                {
                    "source_sheet": support_sheet_name,
                    "source_row_number": int(index) + 1,
                    "data": data,
                }
            )

        return rows

    @classmethod
    def _find_support_sheet_name(cls, sheets: dict[str, pd.DataFrame]) -> str | None:
        for sheet_name in sheets.keys():
            if sheet_name.strip().lower() == cls.SUPPORT_SHEET_NAME:
                return sheet_name

        for sheet_name in sheets.keys():
            if "support" in sheet_name.strip().lower():
                return sheet_name

        return None

    @staticmethod
    def _find_header_row_index(df: pd.DataFrame) -> int | None:
        """
        Finds the first header row.

        The customer's support list uses two header rows. The first one contains
        values such as:
        - Tower number
        - Tower
        - Support
        - H / m

        The second one contains values such as:
        - Work
        - type
        - drawing no
        - document code
        - L
        - R

        Therefore we must not require all header words to exist on the same row.
        """

        for index in range(len(df)):
            row = df.iloc[index]
            values = [str(value).strip().lower() for value in row.tolist()]
            joined = " | ".join(values)

            next_joined = ""
            if index + 1 < len(df):
                next_values = [str(value).strip().lower() for value in df.iloc[index + 1].tolist()]
                next_joined = " | ".join(next_values)

            combined = f"{joined} | {next_joined}"

            if (
                "tower number" in combined
                and "tower" in combined
                and "type" in combined
                and "support" in combined
                and "drawing no" in combined
            ):
                return int(index)

            # Fallback juuri tähän Support list -rakenteeseen:
            # pääotsikkorivi sisältää tower number + tower + support + h / m.
            if (
                "tower number" in joined
                and "tower" in joined
                and "support" in joined
                and "h / m" in joined
            ):
                return int(index)

        return None

    @classmethod
    def _parse_support_list_row(cls, row: pd.Series) -> dict[str, Any] | None:
        tower_number = cls._clean(row.get(0))
        tower_type = cls._clean(row.get(4))

        if not tower_number or not tower_type:
            return None

        if tower_number.startswith("=") or tower_type.startswith("="):
            return None

        if not cls._looks_like_real_support_row(tower_number, tower_type):
            return None

        height_left = cls._to_float(row.get(7))
        height_right = cls._to_float(row.get(8))
        support_height = cls._select_height(height_left, height_right)

        support_drawing_no = cls._clean(row.get(5)) or None
        support_document_code = cls._clean(row.get(6)) or None

        return {
            "pole_code": tower_number,
            "pole_type": tower_type,
            "support_height_m": support_height,
            "quantity": 1,
            "support_drawing_no": support_drawing_no,
            "support_document_code": support_document_code,
            "height_left_m": height_left,
            "height_right_m": height_right,

            # Tämä on johtovälin span pylväsluettelosta, ei vaiheväli.
            # Matcherille tärkeä vaiheväli tulee myöhemmin piirustusanalyysistä kenttään span_m.
            "line_span_m": cls._to_float(row.get(15)),

            "conductors": cls._clean(row.get(18)) or None,
            "earth_wires": cls._clean(row.get(19)) or None,
            "crossings_and_remarks": cls._clean(row.get(20)) or None,
            "environment": cls._clean(row.get(21)) or None,
            "source_parser": "support_list_excel",
            "_support_list_master_row": True,
        }

    @staticmethod
    def _looks_like_real_support_row(tower_number: str, tower_type: str) -> bool:
        """
        Filters out terminal/substation rows that are present in some support lists
        but should not be handled as normal pole rows in this POC.

        Accepted examples:
        - 1Y / 4T
        - 2Y / 1T
        - 144 / 4Y
        - 146 / 1H

        Filtered example:
        - 0TEL / 5E
        """

        tower_number_upper = tower_number.strip().upper()
        tower_type_upper = tower_type.strip().upper()

        if tower_number_upper in {"0TEL", "TEL", "SUBSTATION"}:
            return False

        if "TEL" in tower_number_upper:
            return False

        # POC:ssa hyväksytään tavalliset pylvästyypit kuten 1H, 1HD, 1T, 4T, 1Y, 4Y.
        allowed_type_suffixes = ("HD", "HKD", "HK", "H", "T", "Y")

        if not any(tower_type_upper.endswith(suffix) for suffix in allowed_type_suffixes):
            return False

        return True

    @staticmethod
    def _clean(value: Any) -> str:
        if value is None:
            return ""

        if pd.isna(value):
            return ""

        text = str(value).strip()

        if text.endswith(".0"):
            number_part = text[:-2]
            if number_part.replace("-", "", 1).isdigit():
                return number_part

        return text

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None or pd.isna(value):
            return None

        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip().replace(",", ".")
        if not text:
            return None

        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _select_height(left: float | None, right: float | None) -> float | None:
        values = [value for value in [left, right] if value is not None]
        if not values:
            return None
        return max(values)
