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
        "numero",
        "tunnus",
        "code",
        "id",
    ],
    "pole_type": [
        "pole_type",
        "pole type",
        "support type",
        "support_type",
        "type",
        "family",
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
        "max span",
        "phase span",
        "phase_span",
        "phase spacing",
        "phase spacing mm",
        "phase spacing m",
        "vaiheväli",
        "vaihevali",
        "vaiheiden väli",
        "vaiheiden vali",
        "jänneväli",
        "jannevali",
        "väli",
        "vali",
    ],
    "guying": [
        "guying",
        "guy",
        "guyed",
        "harus",
        "harukset",
        "harustus",
        "harustettu",
        "is_guyed",
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

GUYING_TRUE_VALUES = {
    "yes",
    "y",
    "true",
    "1",
    "kyllä",
    "kylla",
    "guyed",
    "harus",
    "harukset",
    "harustettu",
    "harustus",
}

GUYING_FALSE_VALUES = {
    "no",
    "n",
    "false",
    "0",
    "ei",
    "unguyed",
    "ei haruksia",
    "harukseton",
}

PHASE_SPACING_ALIASES = {
    "phase span",
    "phase_span",
    "phase spacing",
    "phase spacing mm",
    "phase spacing m",
    "vaiheväli",
    "vaihevali",
    "vaiheiden väli",
    "vaiheiden vali",
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


def normalize_pole_type(value) -> tuple[str | None, list[str]]:
    if value is None:
        return None, []

    raw = str(value).strip()
    if raw == "":
        return None, []

    normalized = raw.upper().replace(" ", "")
    reasons: list[str] = []

    if normalized != raw:
        reasons.append(f'Pylvästyyppi normalisoitiin muodosta "{raw}"')

    return normalized, reasons


def normalize_guying(value) -> tuple[str | None, list[str]]:
    if value is None:
        return None, []

    raw = str(value).strip()
    if raw == "":
        return None, []

    normalized = normalize_text(raw)

    if normalized in GUYING_TRUE_VALUES:
        if raw != "guyed":
            return "guyed", [f'Harustieto normalisoitiin muodosta "{raw}"']
        return "guyed", []

    if normalized in GUYING_FALSE_VALUES:
        if raw != "unguyed":
            return "unguyed", [f'Harustieto normalisoitiin muodosta "{raw}"']
        return "unguyed", []

    return raw, []


def parse_span_value(value, source_key: str | None) -> tuple[float | None, list[str]]:
    parsed = parse_float(value)
    if parsed is None:
        return None, []

    source_normalized = normalize_text(source_key) if source_key else ""
    raw_text = str(value).strip()
    text_normalized = normalize_text(raw_text)
    reasons: list[str] = []

    if source_normalized in PHASE_SPACING_ALIASES:
        phase_spacing_m = parsed

        if "mm" in text_normalized:
            phase_spacing_m = parsed / 1000.0
        elif " m" in f" {text_normalized}" or text_normalized.endswith("m"):
            phase_spacing_m = parsed
        elif parsed >= 100:
            # Esim. 4500 tulkitaan 4500 mm -> 4.5 m
            phase_spacing_m = parsed / 1000.0

        normalized_text = (
            str(int(phase_spacing_m))
            if float(phase_spacing_m).is_integer()
            else str(phase_spacing_m)
        )

        if raw_text != normalized_text:
            reasons.append(f'Vaiheväli normalisoitiin muodosta "{value}"')

        return float(phase_spacing_m), reasons

    normalized_text = str(int(parsed)) if float(parsed).is_integer() else str(parsed)
    if raw_text != normalized_text:
        reasons.append(f'Jänne-/vaiheväli normalisoitiin muodosta "{value}"')

    return parsed, reasons


class PoleExtractionService:
    @staticmethod
    def _find_value(data: dict, target_field: str):
        normalized_map = {normalize_text(k): (k, v) for k, v in data.items()}
        aliases = FIELD_ALIASES[target_field]

        for alias in aliases:
            key = normalize_text(alias)
            if key in normalized_map:
                original_key, value = normalized_map[key]
                if str(value).strip() != "":
                    return value, original_key, key != normalize_text(target_field)

        return None, None, False

    @staticmethod
    def _build_review_status(
        pole_type: str | None,
        support_height_m: float | None,
        quantity: int,
        review_reasons: list[str],
    ) -> tuple[str, float, list[str]]:
        reasons = list(review_reasons)
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

        if reasons and any(
            reason in {"Pylvästyyppi puuttuu", "Pylväskorkeus puuttuu", "Määrä ei ole kelvollinen"}
            for reason in reasons
        ):
            return "review", confidence, reasons

        return "ok", confidence, reasons

    @classmethod
    def extract(cls, document_id: str, raw_rows: list[dict]) -> list[DetectedPoleRow]:
        detected_rows: list[DetectedPoleRow] = []

        for raw_row in raw_rows:
            data = raw_row["data"]
            review_reasons: list[str] = []

            pole_code, pole_code_source, pole_code_alias = cls._find_value(data, "pole_code")
            pole_type_raw, pole_type_source, pole_type_alias = cls._find_value(data, "pole_type")
            support_height, support_height_source, support_height_alias = cls._find_value(data, "support_height_m")
            span_raw, span_source, span_alias = cls._find_value(data, "span_m")
            guying_raw, guying_source, guying_alias = cls._find_value(data, "guying")
            quantity_raw, quantity_source, quantity_alias = cls._find_value(data, "quantity")
            structural_solution, _, _ = cls._find_value(data, "structural_solution")

            if pole_code_alias:
                review_reasons.append(f'Sarake "pole_code" löytyi aliasnimellä "{pole_code_source}"')
            if pole_type_alias:
                review_reasons.append(f'Sarake "pole_type" löytyi aliasnimellä "{pole_type_source}"')
            if support_height_alias:
                review_reasons.append(f'Sarake "support_height_m" löytyi aliasnimellä "{support_height_source}"')
            if span_alias:
                review_reasons.append(f'Sarake "span_m" löytyi aliasnimellä "{span_source}"')
            if guying_alias:
                review_reasons.append(f'Sarake "guying" löytyi aliasnimellä "{guying_source}"')
            if quantity_alias:
                review_reasons.append(f'Sarake "quantity" löytyi aliasnimellä "{quantity_source}"')

            support_height_m = parse_float(support_height)
            if support_height not in (None, "") and support_height_m is not None:
                support_height_text = str(support_height).strip()
                normalized_height_text = (
                    str(int(support_height_m))
                    if support_height_m.is_integer()
                    else str(support_height_m)
                )
                if support_height_text != normalized_height_text:
                    review_reasons.append(f'Korkeus normalisoitiin muodosta "{support_height}"')

            span_m, span_reasons = parse_span_value(span_raw, span_source)
            review_reasons.extend(span_reasons)

            quantity_int = parse_int(quantity_raw, default=1)
            if quantity_raw in (None, ""):
                review_reasons.append("Määrä puuttui, oletusarvo 1 käytetty")
            elif parse_float(quantity_raw) is not None:
                quantity_text = str(quantity_raw).strip()
                if quantity_text != str(quantity_int):
                    review_reasons.append(f'Määrä normalisoitiin muodosta "{quantity_raw}"')

            pole_type, pole_type_reasons = normalize_pole_type(pole_type_raw)
            review_reasons.extend(pole_type_reasons)

            guying, guying_reasons = normalize_guying(guying_raw)
            review_reasons.extend(guying_reasons)

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
                pole_type=pole_type,
                support_height_m=support_height_m,
                quantity=quantity_int,
                review_reasons=review_reasons,
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
                    pole_type=pole_type,
                    support_height_m=support_height_m,
                    span_m=span_m,
                    guying=guying,
                    quantity=quantity_int,
                    raw_data=enriched_raw_data,
                    confidence=confidence,
                    review_status=review_status,
                )
            )

        return detected_rows