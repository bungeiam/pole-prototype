from app.models.match import PoleMatch, PolePoolItem
from app.models.pole import DetectedPoleRow


class PoleMatcherService:
    @staticmethod
    def _normalize(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    @staticmethod
    def _height_score(row: DetectedPoleRow, item: PolePoolItem) -> tuple[float, bool]:
        if row.support_height_m is None:
            return 0.0, False

        diff = abs(item.support_height_m - row.support_height_m)

        if diff == 0:
            return 30.0, True
        if diff <= 1:
            return 24.0, True
        if diff <= 2:
            return 18.0, True
        if diff <= 4:
            return 8.0, False

        return 0.0, False

    @staticmethod
    def _phase_spacing_score(row: DetectedPoleRow, item: PolePoolItem) -> tuple[float, bool]:
        if row.span_m is None:
            return 0.0, False

        candidate_values_m: list[float] = []

        if item.phase_spacing_left_mm is not None:
            candidate_values_m.append(item.phase_spacing_left_mm / 1000.0)

        if item.phase_spacing_right_mm is not None:
            candidate_values_m.append(item.phase_spacing_right_mm / 1000.0)

        if not candidate_values_m:
            return 0.0, False

        best_diff = min(abs(value - row.span_m) for value in candidate_values_m)

        if best_diff == 0:
            return 15.0, True
        if best_diff <= 0.05:
            return 13.0, True
        if best_diff <= 0.10:
            return 10.0, True
        if best_diff <= 0.25:
            return 6.0, False

        return 0.0, False

    @staticmethod
    def _guying_score(row: DetectedPoleRow, item: PolePoolItem) -> tuple[float, bool]:
        row_guying = PoleMatcherService._normalize(row.guying)
        item_guying = PoleMatcherService._normalize(item.guying)

        if not row_guying:
            return 0.0, False

        if row_guying == item_guying:
            return 10.0, True

        return 0.0, False

    @staticmethod
    def _score_candidate(
        row: DetectedPoleRow,
        item: PolePoolItem,
        type_required: bool,
    ) -> tuple[float, bool, bool, bool]:
        score = 0.0
        height_close = False
        phase_spacing_ok = False
        guying_ok = False

        row_type = PoleMatcherService._normalize(row.pole_type)
        item_type = PoleMatcherService._normalize(item.pole_type)

        if row_type and item_type == row_type:
            score += 45.0
        elif type_required:
            return 0.0, False, False, False

        height_points, height_close = PoleMatcherService._height_score(row, item)
        phase_spacing_points, phase_spacing_ok = PoleMatcherService._phase_spacing_score(row, item)
        guying_points, guying_ok = PoleMatcherService._guying_score(row, item)

        score += height_points
        score += phase_spacing_points
        score += guying_points

        return score, height_close, phase_spacing_ok, guying_ok

    @staticmethod
    def _build_alternatives(
        scored_items: list[tuple[PolePoolItem, float]]
    ) -> list[str]:
        ranked = sorted(scored_items, key=lambda x: x[1], reverse=True)
        return [item.pool_id for item, score in ranked if score > 0][:3]

    @staticmethod
    def match_rows(rows: list[DetectedPoleRow], pool_items: list[PolePoolItem]) -> list[PoleMatch]:
        results: list[PoleMatch] = []

        for row in rows:
            normalized_type = PoleMatcherService._normalize(row.pole_type)
            type_required = normalized_type is not None

            typed_candidates = [
                item
                for item in pool_items
                if PoleMatcherService._normalize(item.pole_type) == normalized_type
            ] if type_required else []

            scored_all: list[tuple[PolePoolItem, float]] = []

            for item in pool_items:
                soft_score, _, _, _ = PoleMatcherService._score_candidate(
                    row=row,
                    item=item,
                    type_required=False,
                )
                scored_all.append((item, soft_score))

            if type_required and not typed_candidates:
                results.append(
                    PoleMatch(
                        row_id=row.row_id,
                        suggested_pool_id=None,
                        score=0.0,
                        reason=f"Pylvästyyppiä '{row.pole_type}' ei löydy pylväspoolista",
                        alternatives=PoleMatcherService._build_alternatives(scored_all),
                        status="unmatched",
                    )
                )
                continue

            candidates = typed_candidates if type_required else pool_items

            best_item: PolePoolItem | None = None
            best_score = -1.0
            best_height_close = False
            best_phase_spacing_ok = False
            best_guying_ok = False

            scored_candidates: list[tuple[PolePoolItem, float]] = []

            for item in candidates:
                score, height_close, phase_spacing_ok, guying_ok = PoleMatcherService._score_candidate(
                    row=row,
                    item=item,
                    type_required=type_required,
                )
                scored_candidates.append((item, score))

                if score > best_score:
                    best_score = score
                    best_item = item
                    best_height_close = height_close
                    best_phase_spacing_ok = phase_spacing_ok
                    best_guying_ok = guying_ok

            alternatives = PoleMatcherService._build_alternatives(scored_candidates)

            if best_item is None or best_score <= 0:
                results.append(
                    PoleMatch(
                        row_id=row.row_id,
                        suggested_pool_id=None,
                        score=0.0,
                        reason="Ei riittävän hyvää vastaavuutta",
                        alternatives=alternatives,
                        status="unmatched",
                    )
                )
                continue

            if not type_required:
                if best_score >= 35 and best_height_close:
                    results.append(
                        PoleMatch(
                            row_id=row.row_id,
                            suggested_pool_id=best_item.pool_id,
                            score=float(best_score),
                            reason="Pylvästyyppi puuttuu, ehdotus perustuu muihin tietoihin",
                            alternatives=alternatives,
                            status="ambiguous",
                        )
                    )
                else:
                    results.append(
                        PoleMatch(
                            row_id=row.row_id,
                            suggested_pool_id=None,
                            score=float(best_score),
                            reason="Pylvästyyppi puuttuu eikä turvallista automaattista vastaavuutta voitu muodostaa",
                            alternatives=alternatives,
                            status="unmatched",
                        )
                    )
                continue

            has_required_fit = best_height_close and (
                row.span_m is None or best_phase_spacing_ok
            ) and (
                row.guying is None or best_guying_ok
            )

            if best_score >= 80 and has_required_fit:
                results.append(
                    PoleMatch(
                        row_id=row.row_id,
                        suggested_pool_id=best_item.pool_id,
                        score=float(best_score),
                        reason="Hyvä vastaavuus",
                        alternatives=alternatives,
                        status="matched",
                    )
                )
            elif best_score >= 55:
                results.append(
                    PoleMatch(
                        row_id=row.row_id,
                        suggested_pool_id=best_item.pool_id,
                        score=float(best_score),
                        reason="Pylvästyyppi täsmää, mutta muut tiedot eivät riitä varmaan automaattiseen hyväksyntään",
                        alternatives=alternatives,
                        status="ambiguous",
                    )
                )
            else:
                results.append(
                    PoleMatch(
                        row_id=row.row_id,
                        suggested_pool_id=None,
                        score=float(best_score),
                        reason="Pylvästyyppi täsmää, mutta vastaavuus on liian heikko automaattiseen matchaukseen",
                        alternatives=alternatives,
                        status="unmatched",
                    )
                )

        return results