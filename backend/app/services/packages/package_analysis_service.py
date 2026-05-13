from __future__ import annotations

from typing import Any

from app.services.drawings.drawing_catalog_service import DrawingCatalogService
from app.services.enrichment.pole_drawing_enrichment_service import PoleDrawingEnrichmentService
from app.services.file_parsers.support_list_reader import SupportListReaderService
from app.services.packages.package_service import PackageService


class PackageAnalysisService:
    @classmethod
    def build_enriched_raw_rows(cls, package_id: str) -> tuple[list[dict], list[dict[str, Any]]]:
        package = PackageService.get(package_id)

        if not package:
            raise ValueError("Tarjouspakettia ei löytynyt.")

        support_path = package["support_list"]["stored_path"]
        drawing_paths = [item["stored_path"] for item in package.get("drawings", [])]

        raw_rows = SupportListReaderService.read(support_path)
        drawing_catalog = DrawingCatalogService.build_catalog(drawing_paths)

        enriched_rows = PoleDrawingEnrichmentService.enrich_raw_rows(
            raw_rows=raw_rows,
            drawing_catalog=drawing_catalog,
        )

        package["drawing_catalog"] = [item.to_dict() for item in drawing_catalog]
        package["detected_support_rows"] = len(enriched_rows)
        PackageService.save(package)

        return enriched_rows, package["drawing_catalog"]