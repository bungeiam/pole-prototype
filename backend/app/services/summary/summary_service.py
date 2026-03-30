from collections import defaultdict
from app.models.summary import DocumentSummary, SummaryRow, ReviewItem
from app.repositories.in_memory_store import (
    POLES_BY_DOCUMENT,
    MATCHES_BY_DOCUMENT,
    CALCULATIONS_BY_DOCUMENT,
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

        matched_rows = sum(1 for item in matches if item.status == "matched")
        ambiguous_rows = sum(1 for item in matches if item.status == "ambiguous")
        unmatched_rows = sum(1 for item in matches if item.status == "unmatched")

        calculated_rows = sum(1 for item in calculations if item.status == "calculated")
        incomplete_rows = sum(1 for item in calculations if item.status == "incomplete")

        total_quantity = sum(row.quantity for row in poles)
        total_mass = round(sum((item.total_mass_kg or 0) for item in calculations), 2)

        grouped: dict[str, dict] = defaultdict(lambda: {
            "pool_id": None,
            "pole_type": None,
            "quantity": 0,
            "unit_mass_kg": None,
            "total_mass_kg": 0.0,
        })

        for calc in calculations:
            key = calc.pool_id or "UNMATCHED"
            group = grouped[key]

            group["pool_id"] = calc.pool_id
            group["quantity"] += calc.quantity
            group["unit_mass_kg"] = calc.unit_mass_kg
            group["total_mass_kg"] += calc.total_mass_kg or 0.0

            if calc.pool_id and calc.pool_id in pool_by_id:
                group["pole_type"] = pool_by_id[calc.pool_id].pole_type
            else:
                group["pole_type"] = "UNMATCHED"

        rows_by_pool = [
            SummaryRow(
                pool_id=value["pool_id"],
                pole_type=value["pole_type"],
                quantity=value["quantity"],
                unit_mass_kg=value["unit_mass_kg"],
                total_mass_kg=round(value["total_mass_kg"], 2) if value["total_mass_kg"] else None,
            )
            for value in grouped.values()
        ]

        review_items: list[ReviewItem] = []

        for row in poles:
            reasons = row.raw_data.get("_review_reasons", []) if isinstance(row.raw_data, dict) else []
            if row.review_status != "ok":
                reason_text = ", ".join(reasons) if reasons else "Rivi vaatii tarkistuksen"
                review_items.append(
                    ReviewItem(
                        row_id=row.row_id,
                        source_row_number=row.source_row_number,
                        pole_code=row.pole_code,
                        pole_type=row.pole_type,
                        review_status=row.review_status,
                        reason=reason_text,
                    )
                )

        for match in matches:
            if match.status in {"ambiguous", "unmatched"}:
                related_row = next((r for r in poles if r.row_id == match.row_id), None)
                if related_row:
                    review_items.append(
                        ReviewItem(
                            row_id=related_row.row_id,
                            source_row_number=related_row.source_row_number,
                            pole_code=related_row.pole_code,
                            pole_type=related_row.pole_type,
                            review_status="review",
                            reason=match.reason,
                        )
                    )

        unique_review_items = []
        seen = set()
        for item in review_items:
            key = (item.row_id, item.reason)
            if key not in seen:
                seen.add(key)
                unique_review_items.append(item)

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
            review_items=unique_review_items,
        )