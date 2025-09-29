"""In-memory storage for catalog data with reload support."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.models.catalog import CatalogData
from app.services.excel_loader import ExcelLoadReport, CatalogValidationError, load_catalog


@dataclass
class CatalogStorage:
    path: Path
    data: Optional[CatalogData] = None
    last_report: Optional[ExcelLoadReport] = None

    def load(self) -> CatalogData:
        catalog, report = load_catalog(self.path)
        self.data = catalog
        self.last_report = report
        return catalog

    def get(self) -> CatalogData:
        if not self.data:
            return self.load()
        return self.data
