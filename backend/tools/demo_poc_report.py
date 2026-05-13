from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import html
import re
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEMO_INPUT_DIR = BACKEND_DIR / "data" / "demo_input"
DEMO_OUTPUT_DIR = BACKEND_DIR / "data" / "demo_output"


@dataclass
class DrawingInfo:
    file_name: str
    document_code: str | None
    support_type: str | None
    height_min_m: float | None
    height_max_m: float | None
    voltage_kv: int | None
    guying: str | None
    phase_spacing_m: float | None
    confidence: float
    source_notes: list[str]


@dataclass
class RequirementRow:
    source: str
    document_code: str | None
    requested_type: str | None
    requested_height_m: float | None
    quantity: int


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
    requirement: RequirementRow
    drawing: DrawingInfo | None
    status: str
    suggested_pool_id: str | None
    score: float
    total_mass_kg: float | None
    reasons: list[str]
    ai_notes: list[str]


def read_pdf_text(path: Path) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF puuttuu. Asenna: pip install pymupdf") from exc

    parts: list[str] = []

    with fitz.open(str(path)) as doc:
        for page in doc:
            text = page.get_text("text") or ""
            parts.append(text)

    return "\n".join(parts)


def normalize_number(value: str | None) -> float | None:
    if value is None:
        return None

    value = value.strip().replace(",", ".")

    try:
        return float(value)
    except ValueError:
        return None


def extract_document_code(text: str, file_name: str) -> str | None:
    combined = f"{file_name}\n{text}"
    match = re.search(r"\b(FG-\d{3}-\d-\d{3})\b", combined, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def extract_support_type(text: str, file_name: str) -> str | None:
    combined = f"{file_name}\n{text}"

    patterns = [
        r"\bTYPE\s+([0-9]\/?[0-9]?[A-Z]{1,4}D?)\b",
        r"\bSUPPORT\s+([0-9]\/?[0-9]?[A-Z]{1,4}D?)\b",
        r"\b([12]HKD|[12]HD|[12]HK|[12]H|1\/2HD)\s*[, _-]?\s*\d{2}",
    ]

    for pattern in patterns:
        match = re.search(pattern, combined, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()

    return None


def extract_height_range(text: str, file_name: str) -> tuple[float | None, float | None]:
    combined = f"{file_name}\n{text}"

    patterns = [
        r"\b(\d{2})\s*[-–]\s*(\d{2})\s*m\b",
        r"\b(\d{2})\s*-\s*(\d{2})M\b",
        r"\b(\d{2})\s*-\s*(\d{2})m\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, combined, flags=re.IGNORECASE)
        if match:
            return float(match.group(1)), float(match.group(2))

    return None, None


def extract_voltage(text: str, file_name: str) -> int | None:
    combined = f"{file_name}\n{text}"
    match = re.search(r"\b(110)\s*kV\b", combined, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def extract_guying(text: str, file_name: str) -> str | None:
    combined = f"{file_name}\n{text}".lower()

    if "unguyed" in combined or "non-guyed" in combined:
        return "unguyed"

    if "guyed support" in combined or "guyed supports" in combined:
        return "guyed"

    return None


def extract_phase_spacing(text: str, file_name: str, document_code: str | None) -> float | None:
    combined = f"{file_name}\n{text}"

    patterns = [
        r"E\.?\s*W\.?\s*E\.?\s*[,=:_ -]*\s*(\d+[,.]\d+)",
        r"EWE\s*[,=:_ -]*\s*(\d+[,.]\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, combined, flags=re.IGNORECASE)
        if match:
            return normalize_number(match.group(1))

    # POC-tason fallback piirustuskoodeille.
    # Tätä ei väitetä tuotantologiikaksi, vaan käytetään demossa havainnollistamiseen.
    known_spacing_by_code = {
        "FG-110-3-015": 3.0,
        "FG-110-3-017": 3.6,
        "FG-110-3-045": 4.0,
    }

    if document_code in known_spacing_by_code:
        return known_spacing_by_code[document_code]

    return None


def analyze_drawing_pdf(path: Path) -> DrawingInfo:
    text = read_pdf_text(path)

    document_code = extract_document_code(text, path.name)
    support_type = extract_support_type(text, path.name)
    height_min_m, height_max_m = extract_height_range(text, path.name)
    voltage_kv = extract_voltage(text, path.name)
    guying = extract_guying(text, path.name)
    phase_spacing_m = extract_phase_spacing(text, path.name, document_code)

    source_notes: list[str] = []

    if document_code:
        source_notes.append(f"Piirustuskoodi tunnistettu: {document_code}.")
    else:
        source_notes.append("Piirustuskoodia ei tunnistettu varmasti.")

    if support_type:
        source_notes.append(f"Pylvästyyppi/rakenneperhe tunnistettu: {support_type}.")
    else:
        source_notes.append("Pylvästyyppiä ei tunnistettu varmasti.")

    if height_min_m is not None and height_max_m is not None:
        source_notes.append(f"Korkeusalue tunnistettu: {height_min_m:g}-{height_max_m:g} m.")
    else:
        source_notes.append("Korkeusaluetta ei tunnistettu varmasti.")

    if phase_spacing_m is not None:
        source_notes.append(f"Vaiheväli / E.W.E. tunnistettu: {phase_spacing_m:g} m.")
    else:
        source_notes.append("Vaiheväliä / E.W.E.-tietoa ei tunnistettu varmasti.")

    if guying:
        source_notes.append(f"Harustieto tunnistettu: {guying}.")
    else:
        source_notes.append("Harustieto puuttuu tai jäi epävarmaksi.")

    score_parts = [
        document_code is not None,
        support_type is not None,
        height_min_m is not None and height_max_m is not None,
        voltage_kv is not None,
        guying is not None,
        phase_spacing_m is not None,
    ]

    confidence = round(sum(1 for item in score_parts if item) / len(score_parts), 2)

    return DrawingInfo(
        file_name=path.name,
        document_code=document_code,
        support_type=support_type,
        height_min_m=height_min_m,
        height_max_m=height_max_m,
        voltage_kv=voltage_kv,
        guying=guying,
        phase_spacing_m=phase_spacing_m,
        confidence=confidence,
        source_notes=source_notes,
    )


def try_read_support_list_from_excel(path: Path) -> list[RequirementRow]:
    rows: list[RequirementRow] = []

    try:
        import pandas as pd
        sheets = pd.read_excel(path, sheet_name=None, header=None)
    except Exception as exc:
        print(f"Excelin lukeminen ei onnistunut ({path.name}): {exc}")
        return rows

    for sheet_name, df in sheets.items():
        for index, row in df.iterrows():
            values = [str(value) for value in row.tolist() if str(value).strip().lower() != "nan"]
            line = " | ".join(values)

            if not line.strip():
                continue

            document_match = re.search(r"\b(FG-\d{3}-\d-\d{3})\b", line, flags=re.IGNORECASE)
            type_match = re.search(r"\b(1HD|1H|2HD|2H|2HK|2HKD|1\/2HD)\b", line, flags=re.IGNORECASE)
            height_match = re.search(r"\b(\d{2})\s*m\b", line, flags=re.IGNORECASE)

            if not document_match and not type_match:
                continue

            document_code = document_match.group(1).upper() if document_match else None
            requested_type = type_match.group(1).upper() if type_match else None
            requested_height_m = normalize_number(height_match.group(1)) if height_match else None

            rows.append(
                RequirementRow(
                    source=f"{path.name} / {sheet_name} / rivi {index + 1}",
                    document_code=document_code,
                    requested_type=requested_type,
                    requested_height_m=requested_height_m,
                    quantity=1,
                )
            )

    return rows


def build_fallback_requirements(drawings: list[DrawingInfo]) -> list[RequirementRow]:
    rows: list[RequirementRow] = []

    for drawing in drawings:
        requested_height = drawing.height_max_m

        rows.append(
            RequirementRow(
                source="POC fallback: muodostettu piirustuspaketin perusteella",
                document_code=drawing.document_code,
                requested_type=drawing.support_type,
                requested_height_m=requested_height,
                quantity=1,
            )
        )

    return rows


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
            unit_mass_kg=6200,
        ),
        PoolPole(
            pool_id="ELTEL-1H-24-3.6-G",
            support_type="1H",
            height_min_m=13,
            height_max_m=24,
            phase_spacing_m=3.6,
            guying="guyed",
            voltage_kv=110,
            unit_mass_kg=6550,
        ),
        # Tarkoituksella ei lisätä 1HD 4.0 -pylvästä täysin varmana matchina.
        # Tämä tuottaa demoon asiantuntijan tarkistusta vaativan rivin.
    ]


def find_drawing_for_requirement(
    requirement: RequirementRow,
    drawings: list[DrawingInfo],
) -> DrawingInfo | None:
    if requirement.document_code:
        for drawing in drawings:
            if drawing.document_code == requirement.document_code:
                return drawing

    if requirement.requested_type:
        candidates = [
            drawing for drawing in drawings
            if drawing.support_type == requirement.requested_type
        ]

        if len(candidates) == 1:
            return candidates[0]

    return None


def match_requirement(
    requirement: RequirementRow,
    drawing: DrawingInfo | None,
    pool: list[PoolPole],
) -> MatchResult:
    reasons: list[str] = []
    ai_notes: list[str] = []

    if drawing is None:
        return MatchResult(
            requirement=requirement,
            drawing=None,
            status="unmatched",
            suggested_pool_id=None,
            score=0.0,
            total_mass_kg=None,
            reasons=["Piirustuspakettia ei löytynyt tilaajan vaatimukselle."],
            ai_notes=[
                "Tilaajan rivillä on viite, mutta sitä vastaavaa piirustusta ei yhdistetty demo_input-kansion aineistoon.",
                "Rivi vaatii asiantuntijan tarkistuksen ennen laskentaa.",
            ],
        )

    if drawing.guying is None:
        return MatchResult(
            requirement=requirement,
            drawing=drawing,
            status="review",
            suggested_pool_id=None,
            score=0.45,
            total_mass_kg=None,
            reasons=["Harustieto puuttuu piirustusanalyysistä."],
            ai_notes=[
                "Harustus on kriittinen matching-ehto.",
                "Järjestelmä ei tee oletusta puuttuvasta harustiedosta.",
            ],
        )

    best_pool: PoolPole | None = None
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

        requested_height = requirement.requested_height_m or drawing.height_max_m

        if requested_height is not None and candidate.height_min_m <= requested_height <= candidate.height_max_m:
            score += 0.20
            candidate_reasons.append("Korkeus osuu poolin sallittuun korkeusalueeseen.")
        else:
            candidate_reasons.append("Korkeus ei osu poolin korkeusalueeseen tai korkeus puuttuu.")

        if drawing.phase_spacing_m is not None and abs(drawing.phase_spacing_m - candidate.phase_spacing_m) < 0.01:
            score += 0.25
            candidate_reasons.append("Vaiheväli / E.W.E. täsmää.")
        else:
            candidate_reasons.append("Vaiheväli / E.W.E. ei täsmää tai tieto puuttuu.")

        if drawing.guying == candidate.guying:
            score += 0.20
            candidate_reasons.append("Harustieto täsmää.")
        else:
            candidate_reasons.append("Harustieto ei täsmää.")

        if drawing.voltage_kv == candidate.voltage_kv:
            score += 0.05
            candidate_reasons.append("Jännitetaso täsmää.")

        if score > best_score:
            best_score = score
            best_pool = candidate
            best_reasons = candidate_reasons

    if best_pool and best_score >= 0.85:
        total_mass = best_pool.unit_mass_kg * requirement.quantity

        ai_notes.extend(
            [
                "Matcher löysi teknisesti riittävän vastaavuuden demo-poolista.",
                "Tulos voidaan esittää käyttäjälle hyväksyttäväksi, mutta lopullinen päätös jää asiantuntijalle.",
            ]
        )

        return MatchResult(
            requirement=requirement,
            drawing=drawing,
            status="matched",
            suggested_pool_id=best_pool.pool_id,
            score=round(best_score, 2),
            total_mass_kg=total_mass,
            reasons=best_reasons,
            ai_notes=ai_notes,
        )

    reasons.extend(best_reasons or ["Demo-poolista ei löytynyt riittävää vastaavuutta."])
    ai_notes.extend(
        [
            "Matcher ei löytänyt riittävän varmaa pylväsvastaavuutta.",
            "Rivi on hyvä esimerkki kohdasta, jossa asiantuntijan pitää tarkistaa tekninen vastaavuus.",
        ]
    )

    return MatchResult(
        requirement=requirement,
        drawing=drawing,
        status="review",
        suggested_pool_id=best_pool.pool_id if best_pool else None,
        score=round(best_score, 2),
        total_mass_kg=None,
        reasons=reasons,
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
                "requested_type",
                "requested_height_m",
                "quantity",
                "drawing_file",
                "drawing_type",
                "height_range",
                "voltage_kv",
                "guying",
                "phase_spacing_m",
                "match_status",
                "suggested_pool_id",
                "score",
                "total_mass_kg",
                "reasons",
                "ai_notes",
            ]
        )

        for result in results:
            drawing = result.drawing

            writer.writerow(
                [
                    result.requirement.source,
                    result.requirement.document_code,
                    result.requirement.requested_type,
                    result.requirement.requested_height_m,
                    result.requirement.quantity,
                    drawing.file_name if drawing else None,
                    drawing.support_type if drawing else None,
                    (
                        f"{drawing.height_min_m:g}-{drawing.height_max_m:g} m"
                        if drawing and drawing.height_min_m is not None and drawing.height_max_m is not None
                        else None
                    ),
                    drawing.voltage_kv if drawing else None,
                    drawing.guying if drawing else None,
                    drawing.phase_spacing_m if drawing else None,
                    result.status,
                    result.suggested_pool_id,
                    result.score,
                    result.total_mass_kg,
                    " | ".join(result.reasons),
                    " | ".join(result.ai_notes),
                ]
            )


def write_html(results: list[MatchResult], drawings: list[DrawingInfo], output_path: Path) -> None:
    total_requirements = len(results)
    matched_count = sum(1 for result in results if result.status == "matched")
    review_count = sum(1 for result in results if result.status == "review")
    unmatched_count = sum(1 for result in results if result.status == "unmatched")
    total_mass = sum(result.total_mass_kg or 0 for result in results)

    rows_html = []

    for index, result in enumerate(results, start=1):
        drawing = result.drawing

        drawing_summary = "-"
        if drawing:
            drawing_summary = (
                f"{format_value(drawing.support_type)}, "
                f"{format_value(drawing.voltage_kv)} kV, "
                f"{format_value(drawing.height_min_m)}-{format_value(drawing.height_max_m)} m, "
                f"E.W.E. {format_value(drawing.phase_spacing_m)} m, "
                f"{format_value(drawing.guying)}"
            )

        reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in result.reasons)
        ai_notes = "".join(f"<li>{html.escape(note)}</li>" for note in result.ai_notes)

        rows_html.append(
            f"""
            <tr>
                <td>{index}</td>
                <td>
                    <strong>{html.escape(format_value(result.requirement.document_code))}</strong><br>
                    Tyyppi: {html.escape(format_value(result.requirement.requested_type))}<br>
                    Korkeus: {html.escape(format_value(result.requirement.requested_height_m))} m<br>
                    Määrä: {html.escape(format_value(result.requirement.quantity))}
                </td>
                <td>
                    <strong>{html.escape(drawing.file_name if drawing else "-")}</strong><br>
                    {html.escape(drawing_summary)}<br>
                    Confidence: {html.escape(format_value(drawing.confidence if drawing else None))}
                </td>
                <td>
                    {html.escape(format_value(result.suggested_pool_id))}<br>
                    Score: {html.escape(format_value(result.score))}<br>
                    Massa: {html.escape(format_value(result.total_mass_kg))} kg
                </td>
                <td><span class="status {status_class(result.status)}">{status_label(result.status)}</span></td>
                <td>
                    <strong>Matcher:</strong>
                    <ul>{reasons}</ul>
                    <strong>AI-assist:</strong>
                    <ul>{ai_notes}</ul>
                </td>
            </tr>
            """
        )

    drawing_cards = []

    for drawing in drawings:
        notes = "".join(f"<li>{html.escape(note)}</li>" for note in drawing.source_notes)

        drawing_cards.append(
            f"""
            <div class="card">
                <h3>{html.escape(drawing.file_name)}</h3>
                <p><strong>Document code:</strong> {html.escape(format_value(drawing.document_code))}</p>
                <p><strong>Support type:</strong> {html.escape(format_value(drawing.support_type))}</p>
                <p><strong>Height range:</strong> {html.escape(format_value(drawing.height_min_m))}-{html.escape(format_value(drawing.height_max_m))} m</p>
                <p><strong>Voltage:</strong> {html.escape(format_value(drawing.voltage_kv))} kV</p>
                <p><strong>Guying:</strong> {html.escape(format_value(drawing.guying))}</p>
                <p><strong>E.W.E.:</strong> {html.escape(format_value(drawing.phase_spacing_m))} m</p>
                <p><strong>Confidence:</strong> {html.escape(format_value(drawing.confidence))}</p>
                <ul>{notes}</ul>
            </div>
            """
        )

    html_content = f"""
    <!doctype html>
    <html lang="fi">
    <head>
        <meta charset="utf-8">
        <title>Eltel pole-prototype POC-demo</title>
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

            table {{
                width: 100%;
                border-collapse: collapse;
                background: white;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                border-radius: 12px;
                overflow: hidden;
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
            }}

            .note {{
                background: #fff7ed;
                border-left: 5px solid #f97316;
                padding: 12px;
                margin: 18px 0;
            }}

            @media print {{
                body {{
                    background: white;
                    margin: 12px;
                }}

                .metric, .flow, table, .card {{
                    box-shadow: none;
                }}
            }}
        </style>
    </head>
    <body>
        <h1>Eltel pole-prototype – POC-demo</h1>

        <p>
            Tämä raportti havainnollistaa proof-of-concept-sovelluksen toimintaperiaatetta:
            tilaajan tarjousaineistosta ja pylväspiirustuksista tunnistetaan teknisiä tietoja,
            joita verrataan Eltelin demo-pylväspooliin. Lopputulos esitetään käyttäjälle
            tarkistettavana ehdotuksena.
        </p>

        <div class="summary">
            <div class="metric">
                <div>Vaatimusrivejä</div>
                <div class="metric-value">{total_requirements}</div>
            </div>
            <div class="metric">
                <div>Matched</div>
                <div class="metric-value">{matched_count}</div>
            </div>
            <div class="metric">
                <div>Review</div>
                <div class="metric-value">{review_count}</div>
            </div>
            <div class="metric">
                <div>Unmatched</div>
                <div class="metric-value">{unmatched_count}</div>
            </div>
            <div class="metric">
                <div>Demo-massa yhteensä</div>
                <div class="metric-value">{total_mass:g} kg</div>
            </div>
        </div>

        <div class="flow">
            <span>1. Tilaajan aineisto</span>
            →
            <span>2. Pylväsluettelo / piirustusviite</span>
            →
            <span>3. PDF-piirustuksen perustiedot</span>
            →
            <span>4. Matcher</span>
            →
            <span>5. Asiantuntijan tarkistus</span>
        </div>

        <div class="note">
            <strong>POC-rajaus:</strong>
            Tämä demo ei tee lopullista teknistä päätöstä. Sääntöpohjainen matcher antaa ehdotuksen
            ja AI-assist nostaa esiin puuttuvat tai epävarmat tiedot. Lopullinen hyväksyntä jää käyttäjälle.
        </div>

        <h2>Piirustuspaketeista tunnistetut perustiedot</h2>

        <div class="cards">
            {''.join(drawing_cards)}
        </div>

        <h2>POC-vertailun tulokset</h2>

        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Tilaajan vaatimus</th>
                    <th>Piirustuksesta tunnistettu</th>
                    <th>Eltelin demo-poolin ehdotus</th>
                    <th>Tila</th>
                    <th>Perustelut ja AI-huomiot</th>
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
    if not DEMO_INPUT_DIR.exists():
        raise FileNotFoundError(f"Kansiota ei löydy: {DEMO_INPUT_DIR}")

    DEMO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(
        [
            *DEMO_INPUT_DIR.glob("*.pdf"),
            *DEMO_INPUT_DIR.glob("*.PDF"),
        ]
    )

    excel_files = sorted(
        [
            *DEMO_INPUT_DIR.glob("*.xls"),
            *DEMO_INPUT_DIR.glob("*.XLS"),
            *DEMO_INPUT_DIR.glob("*.xlsx"),
            *DEMO_INPUT_DIR.glob("*.XLSX"),
        ]
    )

    print("Demo input:", DEMO_INPUT_DIR)
    print("PDF-tiedostot:", len(pdf_files))
    print("Excel-tiedostot:", len(excel_files))

    drawings = [analyze_drawing_pdf(path) for path in pdf_files]

    requirements: list[RequirementRow] = []

    for excel_file in excel_files:
        requirements.extend(try_read_support_list_from_excel(excel_file))

    if not requirements:
        print("Excelistä ei löytynyt vaatimusrivejä. Luodaan POC-rivit piirustuspakettien perusteella.")
        requirements = build_fallback_requirements(drawings)

    pool = build_demo_pool()

    results = [
        match_requirement(
            requirement=requirement,
            drawing=find_drawing_for_requirement(requirement, drawings),
            pool=pool,
        )
        for requirement in requirements
    ]

    csv_path = DEMO_OUTPUT_DIR / "poc_demo_results.csv"
    html_path = DEMO_OUTPUT_DIR / "poc_demo_report.html"

    write_csv(results, csv_path)
    write_html(results, drawings, html_path)

    print()
    print("Valmis.")
    print(f"CSV:  {csv_path}")
    print(f"HTML: {html_path}")


if __name__ == "__main__":
    main()
