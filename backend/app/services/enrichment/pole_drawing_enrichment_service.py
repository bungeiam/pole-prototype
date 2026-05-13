from __future__ import annotations

from app.services.drawings.drawing_catalog_service import DrawingCatalogItem


class PoleDrawingEnrichmentService:
    """
    Enriches support-list rows with package-specific drawing catalog data.

    The enrichment is conservative: if the drawing match is ambiguous, critical
    technical fields such as guying and phase spacing are not guessed.
    """

    @classmethod
    def enrich_raw_rows(
        cls,
        raw_rows: list[dict],
        drawing_catalog: list[DrawingCatalogItem],
    ) -> list[dict]:
        enriched: list[dict] = []

        for raw_row in raw_rows:
            data = dict(raw_row.get("data", {}))
            match = cls._find_drawing_match(data, drawing_catalog)

            data["drawing_status"] = match["status"]
            data["drawing_match_reason"] = match["reason"]
            data["drawing_candidates"] = [item.to_dict() for item in match["candidates"]]

            review_reasons = list(data.get("_review_reasons", []))
            review_reasons.append(match["reason"])

            if match["status"] == "matched" and match["selected"]:
                drawing = match["selected"]

                data["matched_drawing_file"] = drawing.source_file
                data["matched_drawing_code"] = drawing.document_code
                data["drawing_confidence"] = drawing.confidence
                data["drawing_notes"] = drawing.notes

                data["drawing_support_type"] = drawing.support_type
                data["drawing_height_min_m"] = drawing.height_min_m
                data["drawing_height_max_m"] = drawing.height_max_m
                data["voltage_kv"] = drawing.voltage_kv
                data["max_kg_per_height"] = drawing.max_kg_per_height
                data["max_height_mass_row"] = drawing.max_height_mass_row
                data["part_rows_count"] = drawing.part_rows_count
                data["height_table_found"] = drawing.height_table_found

                if not data.get("guying") and drawing.guying:
                    data["guying"] = drawing.guying
                    review_reasons.append("Harustieto rikastettiin valitusta piirustuksesta.")

                if not data.get("span_m") and drawing.phase_spacing_m is not None:
                    data["span_m"] = drawing.phase_spacing_m
                    review_reasons.append("Vaiheväli / E.W.E. rikastettiin valitusta piirustuksesta.")

            elif match["status"] == "ambiguous":
                review_reasons.append(
                    "Piirustusvastine on epävarma, joten kriittisiä tietoja ei täydennetty automaattisesti."
                )

            elif match["status"] == "missing":
                review_reasons.append("Piirustusvastinetta ei löytynyt ladatuista PDF-tiedostoista.")

            data["_review_reasons"] = review_reasons

            enriched.append(
                {
                    "source_sheet": raw_row.get("source_sheet"),
                    "source_row_number": raw_row.get("source_row_number"),
                    "data": data,
                }
            )

        return enriched

    @classmethod
    def _find_drawing_match(
        cls,
        data: dict,
        drawing_catalog: list[DrawingCatalogItem],
    ) -> dict:
        drawing_no = cls._normalize_code(data.get("support_drawing_no"))
        document_code = cls._normalize_code(data.get("support_document_code"))
        pole_type = cls._normalize_text(data.get("pole_type"))
        height = cls._to_float(data.get("support_height_m"))

        exact_candidates: list[DrawingCatalogItem] = []

        for drawing in drawing_catalog:
            drawing_code = cls._normalize_code(drawing.document_code)

            if drawing_no and drawing_code and drawing_no == drawing_code:
                exact_candidates.append(drawing)
                continue

            if document_code and drawing_code and document_code == drawing_code:
                exact_candidates.append(drawing)

        unique_exact = cls._unique_items(exact_candidates)

        if len(unique_exact) == 1:
            selected = unique_exact[0]
            return {
                "status": "matched",
                "selected": selected,
                "candidates": unique_exact,
                "reason": f"Piirustusvastine löytyi yksiselitteisesti koodilla {selected.document_code}.",
            }

        if len(unique_exact) > 1:
            return {
                "status": "ambiguous",
                "selected": None,
                "candidates": unique_exact,
                "reason": "Piirustuskoodeilla löytyi useita mahdollisia piirustuksia.",
            }

        type_height_candidates = []

        for drawing in drawing_catalog:
            drawing_type = cls._normalize_text(drawing.support_type)

            if pole_type and drawing_type and pole_type == drawing_type:
                if cls._height_fits(height, drawing):
                    type_height_candidates.append(drawing)

        unique_type_height = cls._unique_items(type_height_candidates)

        if len(unique_type_height) == 1:
            selected = unique_type_height[0]
            return {
                "status": "matched",
                "selected": selected,
                "candidates": unique_type_height,
                "reason": "Piirustusvastine löytyi pylvästyypin ja korkeusalueen perusteella.",
            }

        if len(unique_type_height) > 1:
            return {
                "status": "ambiguous",
                "selected": None,
                "candidates": unique_type_height,
                "reason": "Pylvästyypille ja korkeudelle löytyi useita mahdollisia piirustuksia.",
            }

        type_candidates = []

        for drawing in drawing_catalog:
            drawing_type = cls._normalize_text(drawing.support_type)

            if pole_type and drawing_type and pole_type == drawing_type:
                type_candidates.append(drawing)

        unique_type = cls._unique_items(type_candidates)

        if unique_type:
            return {
                "status": "ambiguous",
                "selected": None,
                "candidates": unique_type,
                "reason": (
                    "Pylvästyypille löytyi piirustuksia, mutta korkeus tai muu ehto "
                    "ei riitä varmaan yhdistämiseen."
                ),
            }

        return {
            "status": "missing",
            "selected": None,
            "candidates": [],
            "reason": "Sopivaa piirustusvastinetta ei löytynyt ladatuista PDF-piirustuksista.",
        }

    @staticmethod
    def _normalize_code(value) -> str | None:
        if value is None:
            return None

        text = str(value).strip().upper()
        return text or None

    @staticmethod
    def _normalize_text(value) -> str | None:
        if value is None:
            return None

        text = str(value).strip().upper().replace(" ", "")
        return text or None

    @staticmethod
    def _to_float(value) -> float | None:
        if value is None or value == "":
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _height_fits(height: float | None, drawing: DrawingCatalogItem) -> bool:
        if height is None:
            return False

        if drawing.height_min_m is None or drawing.height_max_m is None:
            return False

        return drawing.height_min_m <= height <= drawing.height_max_m

    @staticmethod
    def _unique_items(items: list[DrawingCatalogItem]) -> list[DrawingCatalogItem]:
        result: list[DrawingCatalogItem] = []
        seen: set[str] = set()

        for item in items:
            key = item.document_code or item.source_file

            if key in seen:
                continue

            seen.add(key)
            result.append(item)

        return result