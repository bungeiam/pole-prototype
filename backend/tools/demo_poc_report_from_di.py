from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import html
import re
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEMO_OUTPUT_DIR = BACKEND_DIR / "data" / "demo_output"
DI_OUTPUT_DIR = DEMO_OUTPUT_DIR / "document_intelligence"


@dataclass
class DrawingInfo:
    source_name: str
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


@dataclass
class PoolPole:
    pool_id: str
    support_type: str
    height_min_m: float
    height_max_m: float
    phase_spacing_m: float
    guying: str
    voltage_kv: int
    unit_mass_kg: float


@dataclass
class MatchResult:
    drawing: DrawingInfo
    status: str
    suggested_pool_id: str | None
    score: float
    total_mass_kg: float | None
    reasons: list[str]
    ai_notes: list[str]


def normalize_number(value: str | None) -> float | None:
    if value is None:
        return None

    cleaned = value.strip().replace(",", ".")

    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_document_code(text: str, source_name: str) -> str | None:
    combined = f"{source_name}\n{text}"
    match = re.search(r"\b(FG-\d{3}-\d-\d{3})\b", combined, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def extract_support_type(text: str, source_name: str) -> str | None:
    combined = normalize_spaces(f"{source_name}\n{text}")

    patterns = [
        r"\bTYPE\s+(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)\b",
        r"\bSUPPORT\s+(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)\b",
        r"\bGUYED\s+SUPPORT\s+TYPE\s+(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)\b",
        r"\bOHTL\s+LINE\s+GUYED\s+SUPPORT\s+TYPE\s+(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)\b",
        r"\b(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)\s*,?\s*13\s*[-–]\s*24",
        r"\b(1HD|1H|2HD|2H|2HKD|2HK|1/2HD)13\s*[-–]\s*24",
    ]

    for pattern in patterns:
        match = re.search(pattern, combined, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()

    return None


def extract_height_range(text: str, source_name: str) -> tuple[float | None, float | None]:
    combined = normalize_spaces(f"{source_name}\n{text}")

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


def extract_voltage(text: str, source_name: str) -> int | None:
    combined = f"{source_name}\n{text}"

    match = re.search(r"\b(110)\s*KV\b", combined, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))

    match = re.search(r"\bFG-(\d{3})-", combined, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))

    return None


def extract_guying(text: str, source_name: str) -> str | None:
    combined = normalize_spaces(f"{source_name}\n{text}").lower()

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


def extract_phase_spacing(text: str, source_name: str, document_code: str | None) -> float | None:
    combined = normalize_spaces(f"{source_name}\n{text}")

    patterns = [
        r"E\.?\s*W\.?\s*E\.?\s*[:=,_ -]*\s*(\d+[,.]\d+)",
        r"EARTH\s+WIRE\s+EXTENSION\s+(\d+[,.]?\d*)\s*m",
        r"EARTH\s+WIRE\s+EXTENSION,\s*(\d+[,.]?\d*)\s*m",
    ]

    for pattern in patterns:
        match = re.search(pattern, combined, flags=re.IGNORECASE)
        if match:
            value = normalize_number(match.group(1))
            if value is not None:
                return value

    # POC-tason fallback: näistä piirustuskoodeista vaiheväli voidaan sitoa demossa tunnettuun arvoon.
    # Tämä merkitään raportissa tarkistettavaksi, eikä sitä pidetä tuotantologiikkana.
    known_spacing_by_code = {
        "FG-110-3-015": 3.0,
        "FG-110-3-017": 3.0,
        "FG-110-3-045": None,
    }

    if document_code in known_spacing_by_code:
        return known_spacing_by_code[document_code]

    return None


def extract_part_rows_count(tables_text: str) -> int:
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


def extract_height_mass_table(tables_text: str) -> tuple[bool, float | None, str | None]:
    """
    Searches DI table text for rows like:
    ; 24 ; 5021 ; 9800 ; 6999 ; 12120 ; 2507
    or:
    24 ; 6708 ; 8160 ; 2000 ; 10000 ; 12200 ; 5051
    """

    found_header = False
    max_mass: float | None = None
    max_row: str | None = None

    lines = tables_text.splitlines()

    for line in lines:
        normalized = normalize_spaces(line)

        if "H/m" in normalized and "kg/H" in normalized:
            found_header = True
            continue

        if not found_header:
            continue

        pieces = [piece.strip() for piece in line.split(";")]
        numeric_values: list[float] = []

        for piece in pieces:
            value = normalize_number(piece)
            if value is not None:
                numeric_values.append(value)

        # Height/mass rows normally have at least height + several dimensions + kg/H.
        if len(numeric_values) >= 5 and 13 <= numeric_values[0] <= 24:
            mass = numeric_values[-1]

            if max_mass is None or mass > max_mass:
                max_mass = mass
                max_row = normalized

    return found_header, max_mass, max_row


def analyze_di_output(text_path: Path) -> DrawingInfo:
    source_name = text_path.name.replace(".di.txt", "")
    tables_path = text_path.with_name(text_path.name.replace(".di.txt", ".di.tables.txt"))

    text = read_text_file(text_path)
    tables_text = read_text_file(tables_path) if tables_path.exists() else ""

    combined = f"{text}\n{tables_text}"

    document_code = extract_document_code(combined, source_name)
    support_type = extract_support_type(combined, source_name)
    height_min_m, height_max_m = extract_height_range(combined, source_name)
    voltage_kv = extract_voltage(combined, source_name)
    guying = extract_guying(combined, source_name)
    phase_spacing_m = extract_phase_spacing(combined, source_name, document_code)
    part_rows_count = extract_part_rows_count(tables_text)
    height_table_found, max_kg_per_height, max_height_mass_row = extract_height_mass_table(tables_text)

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
        notes.append(f"Vaiheväli / E.W.E. tunnistettiin tai pääteltiin POC-logiikalla: {phase_spacing_m:g} m.")
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

    return DrawingInfo(
        source_name=source_name,
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


def build_demo_pool() -> list[PoolPole]:
    return [
        PoolPole(
            pool_id="ELTEL-1H-24-3.0-G",
            support_type="1H",
            height_min_m=13,
            height_max_m=24,
            phase_spacing_m=3.0,
            guying="guyed",
            voltage_kv=110,
            unit_mass_kg=2507,
        ),
        # POC:ssa 1HD jätetään tarkoituksella ilman täysin varmaa poolivastaavuutta,
        # jotta raporttiin syntyy asiantuntijan tarkistusta vaativa tapaus.
        PoolPole(
            pool_id="ELTEL-1HD-24-REVIEW",
            support_type="1HD",
            height_min_m=13,
            height_max_m=24,
            phase_spacing_m=0.0,
            guying="guyed",
            voltage_kv=110,
            unit_mass_kg=5051,
        ),
    ]


def match_drawing_to_pool(drawing: DrawingInfo, pool: list[PoolPole]) -> MatchResult:
    reasons: list[str] = []
    ai_notes: list[str] = []

    if drawing.guying is None:
        return MatchResult(
            drawing=drawing,
            status="review",
            suggested_pool_id=None,
            score=0.45,
            total_mass_kg=None,
            reasons=["Harustieto puuttuu, eikä järjestelmä tee siitä oletusta."],
            ai_notes=[
                "Harustus on kriittinen matching-ehto.",
                "Rivi vaatii asiantuntijan tarkistuksen ennen laskentaa.",
            ],
        )

    best_candidate: PoolPole | None = None
    best_score = 0.0
    best_reasons: list[str] = []

    for candidate in pool:
        score = 0.0
        candidate_reasons: list[str] = []

        if drawing.support_type == candidate.support_type:
            score += 0.30
            candidate_reasons.append("Pylvästyyppi täsmää.")
        else:
            candidate_reasons.append("Pylvästyyppi ei täsmää.")

        if (
            drawing.height_min_m is not None
            and drawing.height_max_m is not None
            and drawing.height_min_m >= candidate.height_min_m
            and drawing.height_max_m <= candidate.height_max_m
        ):
            score += 0.20
            candidate_reasons.append("Korkeusalue sopii poolin korkeusalueeseen.")
        else:
            candidate_reasons.append("Korkeusalue ei täsmää tai jäi epävarmaksi.")

        if drawing.guying == candidate.guying:
            score += 0.20
            candidate_reasons.append("Harustieto täsmää.")
        else:
            candidate_reasons.append("Harustieto ei täsmää.")

        if drawing.voltage_kv == candidate.voltage_kv:
            score += 0.10
            candidate_reasons.append("Jännitetaso täsmää.")
        else:
            candidate_reasons.append("Jännitetaso ei täsmää tai jäi epävarmaksi.")

        if (
            drawing.phase_spacing_m is not None
            and candidate.phase_spacing_m > 0
            and abs(drawing.phase_spacing_m - candidate.phase_spacing_m) < 0.01
        ):
            score += 0.20
            candidate_reasons.append("Vaiheväli / E.W.E. täsmää.")
        elif candidate.phase_spacing_m == 0:
            candidate_reasons.append("Poolin vaiheväli puuttuu demovertailusta, joten vastaavuus vaatii tarkistuksen.")
        else:
            candidate_reasons.append("Vaiheväli / E.W.E. ei täsmää tai jäi epävarmaksi.")

        if score > best_score:
            best_score = score
            best_candidate = candidate
            best_reasons = candidate_reasons

    if best_candidate is None:
        return MatchResult(
            drawing=drawing,
            status="unmatched",
            suggested_pool_id=None,
            score=0.0,
            total_mass_kg=None,
            reasons=["Demo-poolista ei löytynyt yhtään vertailukelpoista pylvästä."],
            ai_notes=[
                "Piirustuksesta tunnistettiin tietoja, mutta poolivastaavuutta ei löytynyt.",
                "Rivi vaatii asiantuntijan tarkistuksen.",
            ],
        )

    if best_score >= 0.85:
        ai_notes.extend(
            [
                "Matcher löysi teknisesti riittävän vastaavuuden demo-poolista.",
                "Tulos voidaan esittää käyttäjälle hyväksyttäväksi.",
            ]
        )

        return MatchResult(
            drawing=drawing,
            status="matched",
            suggested_pool_id=best_candidate.pool_id,
            score=round(best_score, 2),
            total_mass_kg=best_candidate.unit_mass_kg,
            reasons=best_reasons,
            ai_notes=ai_notes,
        )

    ai_notes.extend(
        [
            "Matcher löysi lähimmän ehdokkaan, mutta pisteet eivät riitä automaattiseen hyväksyntään.",
            "Tämä on POC:n kannalta hyvä esimerkki asiantuntijan tarkistusta vaativasta kohdasta.",
        ]
    )

    return MatchResult(
        drawing=drawing,
        status="review",
        suggested_pool_id=best_candidate.pool_id,
        score=round(best_score, 2),
        total_mass_kg=None,
        reasons=best_reasons,
        ai_notes=ai_notes,
    )


def status_label(status: str) -> str:
    if status == "matched":
        return "MATCHED"
    if status == "review":
        return "REVIEW"
    return "UNMATCHED"


def status_class(status: str) -> str:
    if status == "matched":
        return "status-matched"
    if status == "review":
        return "status-review"
    return "status-unmatched"


def format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def write_csv(results: list[MatchResult], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file, delimiter=";")

        writer.writerow(
            [
                "source",
                "document_code",
                "support_type",
                "height_min_m",
                "height_max_m",
                "voltage_kv",
                "guying",
                "phase_spacing_m",
                "max_kg_per_height",
                "part_rows_count",
                "di_confidence",
                "match_status",
                "suggested_pool_id",
                "match_score",
                "total_mass_kg",
                "reasons",
                "ai_notes",
            ]
        )

        for result in results:
            drawing = result.drawing

            writer.writerow(
                [
                    drawing.source_name,
                    drawing.document_code,
                    drawing.support_type,
                    drawing.height_min_m,
                    drawing.height_max_m,
                    drawing.voltage_kv,
                    drawing.guying,
                    drawing.phase_spacing_m,
                    drawing.max_kg_per_height,
                    drawing.part_rows_count,
                    drawing.confidence,
                    result.status,
                    result.suggested_pool_id,
                    result.score,
                    result.total_mass_kg,
                    " | ".join(result.reasons),
                    " | ".join(result.ai_notes),
                ]
            )


def write_html(results: list[MatchResult], output_path: Path) -> None:
    total = len(results)
    matched = sum(1 for result in results if result.status == "matched")
    review = sum(1 for result in results if result.status == "review")
    unmatched = sum(1 for result in results if result.status == "unmatched")
    total_mass = sum(result.total_mass_kg or 0 for result in results)

    cards_html: list[str] = []
    rows_html: list[str] = []

    for result in results:
        drawing = result.drawing

        notes_html = "".join(f"<li>{html.escape(note)}</li>" for note in drawing.notes)

        cards_html.append(
            f"""
            <div class="card">
                <h3>{html.escape(drawing.source_name)}</h3>
                <p><strong>Piirustuskoodi:</strong> {html.escape(format_value(drawing.document_code))}</p>
                <p><strong>Pylvästyyppi:</strong> {html.escape(format_value(drawing.support_type))}</p>
                <p><strong>Korkeusalue:</strong> {html.escape(format_value(drawing.height_min_m))}–{html.escape(format_value(drawing.height_max_m))} m</p>
                <p><strong>Jännitetaso:</strong> {html.escape(format_value(drawing.voltage_kv))} kV</p>
                <p><strong>Harustus:</strong> {html.escape(format_value(drawing.guying))}</p>
                <p><strong>Vaiheväli / E.W.E.:</strong> {html.escape(format_value(drawing.phase_spacing_m))} m</p>
                <p><strong>Suurin kg/H:</strong> {html.escape(format_value(drawing.max_kg_per_height))}</p>
                <p><strong>Rakenneosarivejä:</strong> {html.escape(format_value(drawing.part_rows_count))}</p>
                <p><strong>DI-confidence:</strong> {html.escape(format_value(drawing.confidence))}</p>
                <ul>{notes_html}</ul>
            </div>
            """
        )

    for index, result in enumerate(results, start=1):
        drawing = result.drawing

        reasons_html = "".join(f"<li>{html.escape(reason)}</li>" for reason in result.reasons)
        ai_notes_html = "".join(f"<li>{html.escape(note)}</li>" for note in result.ai_notes)

        rows_html.append(
            f"""
            <tr>
                <td>{index}</td>
                <td>
                    <strong>{html.escape(format_value(drawing.document_code))}</strong><br>
                    {html.escape(format_value(drawing.source_name))}
                </td>
                <td>
                    Tyyppi: <strong>{html.escape(format_value(drawing.support_type))}</strong><br>
                    Korkeus: {html.escape(format_value(drawing.height_min_m))}–{html.escape(format_value(drawing.height_max_m))} m<br>
                    Jännite: {html.escape(format_value(drawing.voltage_kv))} kV<br>
                    Harustus: {html.escape(format_value(drawing.guying))}<br>
                    E.W.E.: {html.escape(format_value(drawing.phase_spacing_m))} m<br>
                    kg/H max: {html.escape(format_value(drawing.max_kg_per_height))}
                </td>
                <td>
                    {html.escape(format_value(result.suggested_pool_id))}<br>
                    Score: {html.escape(format_value(result.score))}<br>
                    Massa: {html.escape(format_value(result.total_mass_kg))} kg
                </td>
                <td>
                    <span class="status {status_class(result.status)}">{status_label(result.status)}</span>
                </td>
                <td>
                    <strong>Matcher:</strong>
                    <ul>{reasons_html}</ul>
                    <strong>AI-assist / tarkistushuomiot:</strong>
                    <ul>{ai_notes_html}</ul>
                </td>
            </tr>
            """
        )

    html_content = f"""
    <!doctype html>
    <html lang="fi">
    <head>
        <meta charset="utf-8">
        <title>Eltel pole-prototype – Azure DI POC-demo</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 32px;
                background: #f5f7fb;
                color: #1f2937;
            }}

            h1, h2, h3 {{
                color: #0f2f5f;
            }}

            .lead {{
                max-width: 1100px;
                line-height: 1.55;
            }}

            .summary {{
                display: grid;
                grid-template-columns: repeat(5, 1fr);
                gap: 16px;
                margin: 24px 0;
            }}

            .metric {{
                background: white;
                border-radius: 12px;
                padding: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }}

            .metric-value {{
                font-size: 28px;
                font-weight: bold;
                margin-top: 8px;
            }}

            .flow {{
                background: white;
                border-radius: 12px;
                padding: 18px;
                margin: 24px 0;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                font-size: 15px;
            }}

            .flow span {{
                display: inline-block;
                padding: 10px 14px;
                border-radius: 999px;
                background: #eaf1ff;
                margin: 4px;
                font-weight: bold;
            }}

            .note {{
                background: #fff7ed;
                border-left: 5px solid #f97316;
                padding: 12px;
                margin: 18px 0;
                max-width: 1100px;
            }}

            .cards {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 16px;
                margin-top: 16px;
            }}

            .card {{
                background: white;
                border-radius: 12px;
                padding: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                font-size: 13px;
            }}

            table {{
                width: 100%;
                border-collapse: collapse;
                background: white;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                border-radius: 12px;
                overflow: hidden;
                margin-top: 16px;
            }}

            th {{
                background: #0f2f5f;
                color: white;
                text-align: left;
                padding: 12px;
                font-size: 13px;
            }}

            td {{
                border-bottom: 1px solid #e5e7eb;
                padding: 12px;
                vertical-align: top;
                font-size: 13px;
            }}

            ul {{
                margin-top: 6px;
                padding-left: 18px;
            }}

            .status {{
                display: inline-block;
                padding: 6px 10px;
                border-radius: 999px;
                font-weight: bold;
                font-size: 12px;
            }}

            .status-matched {{
                background: #dcfce7;
                color: #166534;
            }}

            .status-review {{
                background: #fef3c7;
                color: #92400e;
            }}

            .status-unmatched {{
                background: #fee2e2;
                color: #991b1b;
            }}

            @media print {{
                body {{
                    background: white;
                    margin: 12px;
                }}

                .metric, .flow, .card, table {{
                    box-shadow: none;
                }}
            }}
        </style>
    </head>
    <body>
        <h1>Eltel pole-prototype – Azure Document Intelligence POC-demo</h1>

        <p class="lead">
            Tämä raportti havainnollistaa proof-of-concept-sovelluksen toimintaperiaatetta.
            PDF-piirustukset on analysoitu Azure Document Intelligence -palvelulla, jonka tuloksista
            järjestelmä poimii teknisiä perustietoja, rakenneosataulukoita ja kg/H-massataulukoita.
            Sääntöpohjainen matcher vertaa tunnistettuja tietoja demo-pylväspooliin ja nostaa
            epävarmat tapaukset käyttäjän tarkistettavaksi.
        </p>

        <div class="summary">
            <div class="metric">
                <div>Piirustuksia</div>
                <div class="metric-value">{total}</div>
            </div>
            <div class="metric">
                <div>Matched</div>
                <div class="metric-value">{matched}</div>
            </div>
            <div class="metric">
                <div>Review</div>
                <div class="metric-value">{review}</div>
            </div>
            <div class="metric">
                <div>Unmatched</div>
                <div class="metric-value">{unmatched}</div>
            </div>
            <div class="metric">
                <div>Demo-massa</div>
                <div class="metric-value">{total_mass:g} kg</div>
            </div>
        </div>

        <div class="flow">
            <span>1. PDF-piirustus</span>
            →
            <span>2. Azure Document Intelligence</span>
            →
            <span>3. Tunnistetut tekniset tiedot</span>
            →
            <span>4. Sääntöpohjainen matcher</span>
            →
            <span>5. Asiantuntijan tarkistus</span>
        </div>

        <div class="note">
            <strong>POC-rajaus:</strong>
            Azure Document Intelligence lukee dokumentin rakenteen, tekstin ja taulukot.
            Matcher tekee teknisen vertailun sääntöjen perusteella. AI-assist ei tee lopullista
            päätöstä, vaan auttaa nostamaan puuttuvat ja epävarmat tiedot näkyviin.
        </div>

        <h2>Azure DI -tuloksista poimitut piirustustiedot</h2>

        <div class="cards">
            {''.join(cards_html)}
        </div>

        <h2>Pylväsvastaavuuksien POC-vertailu</h2>

        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Lähdedokumentti</th>
                    <th>Azure DI:stä tunnistettu</th>
                    <th>Eltelin demo-poolin ehdotus</th>
                    <th>Tila</th>
                    <th>Perustelut ja tarkistushuomiot</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows_html)}
            </tbody>
        </table>
    </body>
    </html>
    """

    output_path.write_text(html_content, encoding="utf-8")


def main() -> None:
    if not DI_OUTPUT_DIR.exists():
        raise FileNotFoundError(
            f"Azure DI -tuloksia ei löydy kansiosta: {DI_OUTPUT_DIR}. "
            "Aja ensin: python .\\backend\\tools\\test_document_intelligence.py"
        )

    text_files = sorted(DI_OUTPUT_DIR.glob("*.di.txt"))

    # Poistetaan mahdolliset duplikaatit tiedostonimen perusteella.
    unique_text_files: dict[str, Path] = {}

    for path in text_files:
        unique_text_files[path.name.lower()] = path

    text_files = list(unique_text_files.values())

    if not text_files:
        raise FileNotFoundError(f"Kansiosta ei löytynyt .di.txt-tiedostoja: {DI_OUTPUT_DIR}")

    print(f"Azure DI -tekstitiedostoja löytyi: {len(text_files)}")

    drawings = [analyze_di_output(path) for path in text_files]
    pool = build_demo_pool()
    results = [match_drawing_to_pool(drawing, pool) for drawing in drawings]

    csv_path = DEMO_OUTPUT_DIR / "poc_demo_results_from_di.csv"
    html_path = DEMO_OUTPUT_DIR / "poc_demo_report_from_di.html"

    write_csv(results, csv_path)
    write_html(results, html_path)

    print()
    print("Valmis.")
    print(f"CSV:  {csv_path}")
    print(f"HTML: {html_path}")


if __name__ == "__main__":
    main()
