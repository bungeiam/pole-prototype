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
    def _item_phase_spacing_m(item: PolePoolItem) -> float | None:
        values = [
            v for v in [
                item.phase_spacing_left_mm,
                item.phase_spacing_right_mm
            ] if v is not None
        ]

        if values:
            return max(values) / 1000.0

        if item.phase_spacing_text:
            text = item.phase_spacing_text.replace(",", ".")
            numbers = []
            for part in text.replace("/", " ").split():
                try:
                    numbers.append(float(part))
                except ValueError:
                    continue

            if numbers:
                return max(numbers) / 1000.0 if max(numbers) > 100 else max(numbers)

        return None

    @staticmethod
    def _phase_spacing_score(row: DetectedPoleRow, item: PolePoolItem) -> tuple[float, bool]:
        row_spacing = row.span_m
        item_spacing = PoleMatcherService._item_phase_spacing_m(item)

        if row_spacing is None or item_spacing is None:
            return 0.0, False

        diff = abs(item_spacing - row_spacing)

        if diff == 0:
            return 20.0, True
        if diff <= 0.15:
            return 16.0, True
        if diff <= 0.30:
            return 12.0, True
        if diff <= 0.50:
            return 6.0, False

        return 0.0, False

    # 🔥 MUUTETTU: harustus on nyt pakollinen ehto
    @staticmethod
    def _check_guying(row: DetectedPoleRow, item: PolePoolItem) -> tuple[bool, bool]:
        row_guying = PoleMatcherService._normalize(row.guying)
        item_guying = PoleMatcherService._normalize(item.guying)

        if not row_guying:
            return True, False  # sallitaan mutta merkitään puuttuvaksi

        if row_guying == item_guying:
            return True, True

        return False, False  # hylätään

    @staticmethod
    def _score_candidate(row, item, type_required):
        score = 0.0

        row_type = PoleMatcherService._normalize(row.pole_type)
        item_type = PoleMatcherService._normalize(item.pole_type)

        # 🔒 Tyyppi pakollinen jos annettu
        if row_type and item_type == row_type:
            score += 45.0
        elif type_required:
            return 0.0, False, False, False, False

        # 🔒 Harustus pakollinen jos annettu
        guying_ok, guying_match = PoleMatcherService._check_guying(row, item)
        if not guying_ok:
            return 0.0, False, False, False, False

        height_score, height_ok = PoleMatcherService._height_score(row, item)
        spacing_score, spacing_ok = PoleMatcherService._phase_spacing_score(row, item)

        score += height_score + spacing_score

        # Harustus antaa pisteet vain jos täsmää
        if guying_match:
            score += 10.0

        return score, height_ok, spacing_ok, guying_match, row.guying is not None

    @staticmethod
    def _build_alternatives(scored):
        ranked = sorted(scored, key=lambda x: x[1], reverse=True)
        return [item.pool_id for item, score in ranked if score > 0][:3]

    @staticmethod
    def match_rows(rows, pool_items):
        results = []

        for row in rows:
            normalized_type = PoleMatcherService._normalize(row.pole_type)
            type_required = normalized_type is not None

            typed_candidates = [
                item for item in pool_items
                if PoleMatcherService._normalize(item.pole_type) == normalized_type
            ] if type_required else []

            scored_all = [
                (item, PoleMatcherService._score_candidate(row, item, False)[0])
                for item in pool_items
            ]

            if type_required and not typed_candidates:
                results.append(
                    PoleMatch(
                        row_id=row.row_id,
                        suggested_pool_id=None,
                        score=0.0,
                        reason=f"Tyyppiä '{row.pole_type}' ei löydy poolista",
                        alternatives=PoleMatcherService._build_alternatives(scored_all),
                        status="unmatched",
                    )
                )
                continue

            candidates = typed_candidates if type_required else pool_items

            best = None
            best_score = -1
            best_height = False
            best_spacing = False
            best_guying_match = False
            has_guying_info = False
            scored = []

            for item in candidates:
                score, h_ok, s_ok, g_match, g_present = PoleMatcherService._score_candidate(row, item, type_required)
                scored.append((item, score))

                if score > best_score:
                    best = item
                    best_score = score
                    best_height = h_ok
                    best_spacing = s_ok
                    best_guying_match = g_match
                    has_guying_info = g_present

            alternatives = PoleMatcherService._build_alternatives(scored)

            if best is None or best_score <= 0:
                results.append(
                    PoleMatch(
                        row_id=row.row_id,
                        suggested_pool_id=None,
                        score=0.0,
                        reason="Ei riittävää vastaavuutta",
                        alternatives=alternatives,
                        status="unmatched",
                    )
                )
                continue

            # 🔒 UUSI: harustus puuttuu → ei saa olla matched
            if not has_guying_info:
                results.append(
                    PoleMatch(
                        row_id=row.row_id,
                        suggested_pool_id=best.pool_id,
                        score=float(best_score),
                        reason="Harustieto puuttuu – vaatii manuaalisen tarkistuksen",
                        alternatives=alternatives,
                        status="ambiguous",
                    )
                )
                continue

            # 🔒 turvallinen hyväksyntä
            if best_score >= 80 and best_height and best_spacing and best_guying_match:
                status = "matched"
                reason = "Hyvä vastaavuus"
            elif best_score >= 55:
                status = "ambiguous"
                reason = "Osittainen vastaavuus"
            else:
                status = "unmatched"
                reason = "Heikko vastaavuus"

            results.append(
                PoleMatch(
                    row_id=row.row_id,
                    suggested_pool_id=best.pool_id if status != "unmatched" else None,
                    score=float(best_score),
                    reason=reason,
                    alternatives=alternatives,
                    status=status,
                )
            )

        return results