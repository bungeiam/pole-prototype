from app.models.pole import DetectedPoleRow
from app.models.match import PoleMatch, PolePoolItem


class PoleMatcherService:
    @staticmethod
    def match_rows(rows: list[DetectedPoleRow], pool_items: list[PolePoolItem]) -> list[PoleMatch]:
        results: list[PoleMatch] = []

        for row in rows:
            best_item = None
            best_score = -1.0
            alternatives: list[tuple[str, float]] = []

            for item in pool_items:
                score = 0.0

                if row.pole_type and item.pole_type.lower() == row.pole_type.lower():
                    score += 60

                if row.support_height_m is not None:
                    diff = abs(item.support_height_m - row.support_height_m)
                    if diff == 0:
                        score += 30
                    elif diff <= 2:
                        score += 20
                    elif diff <= 4:
                        score += 10

                if row.span_m is not None and item.max_span_m is not None:
                    if row.span_m <= item.max_span_m:
                        score += 10

                if row.guying and item.guying and row.guying.lower() == item.guying.lower():
                    score += 10

                alternatives.append((item.pool_id, score))

                if score > best_score:
                    best_score = score
                    best_item = item

            alternatives_sorted = [pool_id for pool_id, _ in sorted(alternatives, key=lambda x: x[1], reverse=True)[:3]]

            if best_item is None or best_score < 40:
                results.append(
                    PoleMatch(
                        row_id=row.row_id,
                        suggested_pool_id=None,
                        score=float(max(best_score, 0)),
                        reason="Ei riittävän hyvää vastaavuutta",
                        alternatives=alternatives_sorted,
                        status="unmatched",
                    )
                )
            elif best_score < 75:
                results.append(
                    PoleMatch(
                        row_id=row.row_id,
                        suggested_pool_id=best_item.pool_id,
                        score=float(best_score),
                        reason="Osittainen vastaavuus, tarkistus suositeltava",
                        alternatives=alternatives_sorted,
                        status="ambiguous",
                    )
                )
            else:
                results.append(
                    PoleMatch(
                        row_id=row.row_id,
                        suggested_pool_id=best_item.pool_id,
                        score=float(best_score),
                        reason="Hyvä vastaavuus",
                        alternatives=alternatives_sorted,
                        status="matched",
                    )
                )

        return results