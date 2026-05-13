from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
DEMO_INPUT_DIR = BACKEND_DIR / "data" / "demo_input"
DEMO_OUTPUT_DIR = BACKEND_DIR / "data" / "demo_output"
DI_OUTPUT_DIR = DEMO_OUTPUT_DIR / "document_intelligence"


def load_environment() -> None:
    possible_env_files = [
        PROJECT_ROOT / ".env",
        BACKEND_DIR / ".env",
    ]

    for env_file in possible_env_files:
        if env_file.exists():
            load_dotenv(env_file)


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Ympäristömuuttuja puuttuu: {name}")

    return value


def analyze_with_document_intelligence(file_path: Path) -> Any:
    try:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential
    except ImportError as exc:
        raise RuntimeError(
            "Azure Document Intelligence -kirjasto puuttuu. "
            "Asenna se komennolla: pip install azure-ai-documentintelligence azure-core"
        ) from exc

    endpoint = get_required_env("AZURE_DI_ENDPOINT")
    key = get_required_env("AZURE_DI_KEY")

    client = DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(key),
    )

    with file_path.open("rb") as file:
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            body=file,
            content_type="application/pdf",
        )

    return poller.result()


def result_to_plain_text(result: Any) -> str:
    lines: list[str] = []

    pages = result.pages or []

    for page in pages:
        lines.append(f"=== PAGE {page.page_number} ===")

        if page.lines:
            for line in page.lines:
                lines.append(line.content)

        lines.append("")

    return "\n".join(lines)


def result_tables_to_text(result: Any) -> str:
    lines: list[str] = []

    tables = result.tables or []

    for table_index, table in enumerate(tables, start=1):
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


def result_to_json_safe(result: Any) -> dict:
    if hasattr(result, "as_dict"):
        return result.as_dict()

    if hasattr(result, "to_dict"):
        return result.to_dict()

    return json.loads(json.dumps(result, default=str))


def main() -> None:
    load_environment()

    use_azure_di = os.getenv("USE_AZURE_DI", "false").lower() == "true"

    if not use_azure_di:
        raise RuntimeError("USE_AZURE_DI ei ole true. Lisää .env-tiedostoon: USE_AZURE_DI=true")

    if not DEMO_INPUT_DIR.exists():
        raise FileNotFoundError(f"Demo input -kansiota ei löydy: {DEMO_INPUT_DIR}")

    DI_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(
        [
            *DEMO_INPUT_DIR.glob("*.pdf"),
            *DEMO_INPUT_DIR.glob("*.PDF"),
        ]
    )

    if not pdf_files:
        raise FileNotFoundError(f"Kansiosta ei löytynyt PDF-tiedostoja: {DEMO_INPUT_DIR}")

    print(f"PDF-tiedostoja löytyi: {len(pdf_files)}")
    print(f"Tulokset tallennetaan: {DI_OUTPUT_DIR}")
    print()

    for pdf_file in pdf_files:
        print(f"Analysoidaan Azure DI:llä: {pdf_file.name}")

        result = analyze_with_document_intelligence(pdf_file)

        base_name = pdf_file.stem

        json_path = DI_OUTPUT_DIR / f"{base_name}.di.json"
        text_path = DI_OUTPUT_DIR / f"{base_name}.di.txt"
        tables_path = DI_OUTPUT_DIR / f"{base_name}.di.tables.txt"

        json_data = result_to_json_safe(result)
        plain_text = result_to_plain_text(result)
        tables_text = result_tables_to_text(result)

        json_path.write_text(
            json.dumps(json_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        text_path.write_text(plain_text, encoding="utf-8")
        tables_path.write_text(tables_text, encoding="utf-8")

        page_count = len(result.pages or [])
        table_count = len(result.tables or [])

        print(f"  Sivut: {page_count}")
        print(f"  Taulukot: {table_count}")
        print(f"  JSON: {json_path}")
        print(f"  Teksti: {text_path}")
        print(f"  Taulukot: {tables_path}")
        print()

    print("Valmis.")


if __name__ == "__main__":
    main()
