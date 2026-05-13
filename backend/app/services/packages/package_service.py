from __future__ import annotations

import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.repositories.in_memory_store import PACKAGES


class PackageService:
    PACKAGE_DIR = Path("storage/packages")
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def create_package(
        cls,
        support_list: UploadFile,
        drawings: list[UploadFile],
    ) -> dict[str, Any]:
        package_id = str(uuid.uuid4())

        package_dir = cls.PACKAGE_DIR / package_id
        input_dir = package_dir / "input"
        drawings_dir = input_dir / "drawings"

        drawings_dir.mkdir(parents=True, exist_ok=True)

        support_suffix = Path(support_list.filename or "support_list.xlsx").suffix.lower()
        support_path = input_dir / f"support_list{support_suffix}"

        with support_path.open("wb") as buffer:
            shutil.copyfileobj(support_list.file, buffer)

        drawing_items: list[dict[str, Any]] = []

        for index, drawing in enumerate(drawings, start=1):
            if not drawing.filename:
                continue

            suffix = Path(drawing.filename).suffix.lower()
            if suffix != ".pdf":
                continue

            safe_original_name = cls._safe_filename(drawing.filename)
            safe_filename = f"{index:03d}_{safe_original_name}"
            drawing_path = drawings_dir / safe_filename

            with drawing_path.open("wb") as buffer:
                shutil.copyfileobj(drawing.file, buffer)

            drawing_items.append(
                {
                    "original_filename": drawing.filename,
                    "stored_path": str(drawing_path),
                    "file_type": "pdf",
                }
            )

        package = {
            "package_id": package_id,
            "status": "uploaded",
            "upload_time": datetime.utcnow().isoformat(),
            "support_list": {
                "original_filename": support_list.filename,
                "stored_path": str(support_path),
                "file_type": support_suffix.replace(".", ""),
            },
            "drawings": drawing_items,
            "package_dir": str(package_dir),
        }

        PACKAGES[package_id] = package
        return package

    @staticmethod
    def get(package_id: str) -> dict[str, Any] | None:
        return PACKAGES.get(package_id)

    @staticmethod
    def list_all() -> list[dict[str, Any]]:
        return list(PACKAGES.values())

    @staticmethod
    def save(package: dict[str, Any]) -> dict[str, Any]:
        PACKAGES[package["package_id"]] = package
        return package

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = Path(filename).name
        name = re.sub(r"[^A-Za-z0-9_.\-åäöÅÄÖ]+", "_", name)
        return name