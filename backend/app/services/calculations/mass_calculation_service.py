from app.models.calculation import MassCalculationResult
from app.models.match import PoleMatch, PolePoolItem
from app.models.pole import DetectedPoleRow


class MassCalculationService:
    @staticmethod
    def calculate(
        rows: list[DetectedPoleRow],
        matches: list[PoleMatch],
        pool_items: list[PolePoolItem],
    ) -> list[MassCalculationResult]:
        pool_by_id = {item.pool_id: item for item in pool_items}
        rows_by_id = {row.row_id: row for row in rows}

        results: list[MassCalculationResult] = []

        for match in matches:
            row = rows_by_id[match.row_id]
            if not match.suggested_pool_id or match.suggested_pool_id not in pool_by_id:
                results.append(
                    MassCalculationResult(
                        row_id=row.row_id,
                        quantity=row.quantity,
                        status="incomplete",
                    )
                )
                continue

            item = pool_by_id[match.suggested_pool_id]
            total_mass = item.unit_mass_kg * row.quantity

            results.append(
                MassCalculationResult(
                    row_id=row.row_id,
                    pool_id=item.pool_id,
                    quantity=row.quantity,
                    unit_mass_kg=item.unit_mass_kg,
                    total_mass_kg=total_mass,
                    status="calculated",
                )
            )

        return results