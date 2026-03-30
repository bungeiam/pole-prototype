from collections import defaultdict

from app.models.summary import DocumentSummary, ReviewItem, SummaryRow
from app.repositories.in_memory_store import (
    CALCULATIONS_BY_DOCUMENT,
    CORRECTIONS_BY_ROW,
    MATCHES_BY_DOCUMENT,
    POLES_BY_DOCUMENT,
)
from app.repositories.pole_pool_repository import PolePoolRepository


class SummaryService:
    @staticmethod
    def build(document_id: str, document_status: str) -> DocumentSummary:
        poles = POLES_BY_DOCUMENT.get(document_id, [])
        matches = MATCHES_BY_DOCUMENT.get(document_id, [])
        calculations = CALCULATIONS_BY_DOCUMENT.get(document_id, [])

        pool_items = PolePoolRepository().load_all()
        pool_by_id = {item.pool_id: item for item in pool_items}

        match_by_row_id = {match.row_id: match for match in matches}
        calculation_by_row_id = {calc.row_id: calc for calc in calculations}

        matched_rows = sum(1 for item in matches if item.status == "matched")
        ambiguous_rows = sum(1 for item in matches if item.status == "ambiguous")
        unmatched_rows = sum(1 for item in matches if item.status == "unmatched")

        calculated_rows = sum(1 for item in calculations if item.status == "calculated")
        incomplete_rows = sum(1 for item in calculations if item.status == "incomplete")

        total_quantity = sum(row.quantity for row in poles)
        total_mass = round(
            sum((item.total_mass_kg or 0) for item in calculations if item.status == "calculated"),
            2,
        )

        grouped: dict[str, dict] = defaultdict(
            lambda: {
                "pool_id": None,
                "pole_type": None,
                "quantity": 0,
                "unit_mass_kg": None,
                "total_mass_kg": 0.0,
            }
        )

        for calc in calculations:
            if calc.status != "calculated" or not calc.pool_id:
                continue

            group = grouped[calc.pool_id]
            group["pool_id"] = calc.pool_id
            group["quantity"] += calc.quantity
            group["unit_mass_kg"] = calc.unit_mass_kg
            group["total_mass_kg"] += calc.total_mass_kg or 0.0

            if calc.pool_id in pool_by_id:
                group["pole_type"] = pool_by_id[calc.pool_id].pole_type

        rows_by_pool = [
            SummaryRow(
                pool_id=value["pool_id"],
                pole_type=value["pole_type"],
                quantity=value["quantity"],
                unit_mass_kg=value["unit_mass_kg"],
                total_mass_kg=round(value["total_mass_kg"], 2),
            )
            for value in grouped.values()
        ]

        review_items: list[ReviewItem] = []

        for row in poles:
            reasons: list[str] = []
            seen_reasons: set[str] = set()

            def add_reason(reason: str | None) -> None:
                if not reason:
                    return
                cleaned = reason.strip()
                if not cleaned or cleaned in seen_reasons:
                    return
                seen_reasons.add(cleaned)
                reasons.append(cleaned)

            match = match_by_row_id.get(row.row_id)
            calculation = calculation_by_row_id.get(row.row_id)
            correction = CORRECTIONS_BY_ROW.get(row.row_id)

            raw_reasons = row.raw_data.get("_review_reasons", []) if isinstance(row.raw_data, dict) else []
            if row.review_status != "ok":
                if isinstance(raw_reasons, list) and raw_reasons:
                    for reason in raw_reasons:
                        add_reason(str(reason))
                else:
                    add_reason("Rivi vaatii tarkistuksen")

            manual_selection_exists = bool(correction and correction.selected_pool_id)

            if match and match.status in {"ambiguous", "unmatched"} and not manual_selection_exists:
                add_reason(match.reason)

            if calculation and calculation.status == "incomplete":
                add_reason("Riviä ei laskettu automaattisesti, koska vastaavuus ei ole varma tai hyväksytty")

            if reasons:
                effective_review_status = "review"

                review_items.append(
                    ReviewItem(
                        row_id=row.row_id,
                        source_row_number=row.source_row_number,
                        pole_code=row.pole_code,
                        pole_type=row.pole_type,
                        review_status=effective_review_status,
                        match_status=match.status if match else None,
                        calculation_status=calculation.status if calculation else None,
                        suggested_pool_id=match.suggested_pool_id if match else None,
                        selected_pool_id=correction.selected_pool_id if correction else None,
                        reasons=reasons,
                    )
                )

        return DocumentSummary(
            document_id=document_id,
            document_status=document_status,
            total_detected_rows=len(poles),
            total_matches=len(matches),
            matched_rows=matched_rows,
            ambiguous_rows=ambiguous_rows,
            unmatched_rows=unmatched_rows,
            calculated_rows=calculated_rows,
            incomplete_rows=incomplete_rows,
            total_quantity=total_quantity,
            total_mass_kg=total_mass,
            rows_by_pool=rows_by_pool,
            review_items=review_items,
        )