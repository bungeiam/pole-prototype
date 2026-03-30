import re
import uuid
from app.models.pole import DetectedPoleRow


FIELD_ALIASES = {
    "pole_code": [
        "pole_code",
        "pole code",
        "support number",
        "support no",
        "support_number",
        "pylväsnumero",
        "pylvasnumero",
        "tunnus",
        "code",
    ],
    "pole_type": [
        "pole_type",
        "pole type",
        "support type",
        "support_type",
        "type",
        "pylvästyyppi",
        "pylvastyyppi",
        "tyyppi",
    ],
    "support_height_m": [
        "support_height_m",
        "support height",
        "support_height",
        "height",
        "pole height",
        "pylväskorkeus",
        "pylvaskorkeus",
        "korkeus",
        "height m",
        "korkeus m",
    ],
    "span_m": [
        "span_m",
        "span",
        "phase span",
        "phase_span",
        "vaiheväli",
        "vaihevali",
        "jänneväli",
        "jannevali",
        "väli",
        "vali",
    ],
    "guying": [
        "guying",
        "guy",
        "guyed",
        "harukset",
        "harustus",
        "harustettu",
    ],
    "quantity": [
        "quantity",
        "qty",
        "count",
        "määrä",
        "maara",
        "kpl",
        "lukumäärä",
        "lukumaara",
    ],
    "structural_solution": [
        "structural solution",
        "structure",
        "construction",
        "rakenteellinen ratkaisu",
        "rakenne",
        "ratkaisu",
    ],
}


def normalize_text(value: str) -> str:
    value = str(value).strip().lower()
    value = value.replace("\n", " ")
    value = value.replace("_", " ")
    value = re.sub(r"\s+", " ", value)
    return value


def parse_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", ".")
    if text == "":
        return None

    match = re.search(r"-?\d+(\.\d+)?", text)
    if not match:
        return None

    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_int(value, default: int = 1) -> int:
    number = parse_float(value)
    if number is None:
        return default
    return int(number)


class PoleExtractionService:
    @staticmethod
    def _find_value(data: dict, target_field: str):
        normalized_map = {normalize_text(k): v for k, v in data.items()}
        aliases = FIELD_ALIASES[target_field]

        for alias in aliases:
            key = normalize_text(alias)
            if key in normalized_map and str(normalized_map[key]).strip() != "":
                return normalized_map[key]

        return None

    @staticmethod
    def _build_review_status(
        pole_type: str | None,
        support_height_m: float | None,
        quantity: int,
    ) -> tuple[str, float, list[str]]:
        reasons: list[str] = []
        confidence = 0.95

        if not pole_type:
            reasons.append("Pylvästyyppi puuttuu")
            confidence = min(confidence, 0.45)

        if support_height_m is None:
            reasons.append("Pylväskorkeus puuttuu")
            confidence = min(confidence, 0.55)

        if quantity <= 0:
            reasons.append("Määrä ei ole kelvollinen")
            confidence = min(confidence, 0.40)

        if reasons:
            return "review", confidence, reasons

        return "ok", confidence, []

    @classmethod
    def extract(cls, document_id: str, raw_rows: list[dict]) -> list[DetectedPoleRow]:
        detected_rows: list[DetectedPoleRow] = []

        for raw_row in raw_rows:
            data = raw_row["data"]

            pole_code = cls._find_value(data, "pole_code")
            pole_type = cls._find_value(data, "pole_type")
            support_height = cls._find_value(data, "support_height_m")
            span = cls._find_value(data, "span_m")
            guying = cls._find_value(data, "guying")
            quantity = cls._find_value(data, "quantity")
            structural_solution = cls._find_value(data, "structural_solution")

            support_height_m = parse_float(support_height)
            span_m = parse_float(span)
            quantity_int = parse_int(quantity, default=1)

            has_any_core_field = any(
                [
                    pole_code,
                    pole_type,
                    support_height_m is not None,
                    span_m is not None,
                    structural_solution,
                ]
            )

            if not has_any_core_field:
                continue

            review_status, confidence, review_reasons = cls._build_review_status(
                pole_type=str(pole_type).strip() if pole_type else None,
                support_height_m=support_height_m,
                quantity=quantity_int,
            )

            enriched_raw_data = dict(data)
            enriched_raw_data["_review_reasons"] = review_reasons
            enriched_raw_data["_structural_solution"] = structural_solution

            detected_rows.append(
                DetectedPoleRow(
                    row_id=str(uuid.uuid4()),
                    document_id=document_id,
                    source_sheet=raw_row.get("source_sheet"),
                    source_row_number=raw_row.get("source_row_number"),
                    pole_code=str(pole_code).strip() if pole_code else None,
                    pole_type=str(pole_type).strip() if pole_type else None,
                    support_height_m=support_height_m,
                    span_m=span_m,
                    guying=str(guying).strip() if guying else None,
                    quantity=quantity_int,
                    raw_data=enriched_raw_data,
                    confidence=confidence,
                    review_status=review_status,
                )
            )

        return detected_rows