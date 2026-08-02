"""Bridge recognised OCR regions to the verified geometric layout engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Iterable, Mapping

from ..table_grid import detect_table_grid
from .reconstruction import reconstruct_page


@dataclass(frozen=True)
class PageLayoutResult:
    document_id: str
    page_number: int
    layout: dict[str, Any]
    groups: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    records: list[dict[str, Any]]
    summary: dict[str, Any]
    elapsed_ms: float

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": "2.0", "method": "per_page_geometry_layout_reconstruction",
                "document_id": self.document_id, "page_number": self.page_number,
                "layout": self.layout, "groups": self.groups, "rows": self.rows,
                "records": self.records, "summary": self.summary, "elapsed_ms": self.elapsed_ms,
                "warning": "Candidate layout inferred from OCR geometry; it is not ground truth."}


class Page3PlusLayoutAnalysisService:
    """Analyse recognised regions without relying on untrained semantic labels."""

    def analyse_page(self, image_path: Path, recognised_regions: Iterable[Any], *, document_id: str, page_number: int) -> PageLayoutResult:
        started = time.perf_counter()
        page = {"document_id": document_id, "page_number": page_number, "image_path": str(image_path),
                "block_predictions": [self._block(index, region) for index, region in enumerate(recognised_regions) if self._text(region)]}
        payload = reconstruct_page(page, detect_table_grid(image_path))
        return PageLayoutResult(document_id, page_number, payload["layout"], payload["groups"], payload["rows"],
                                payload["records"], payload["summary"], round((time.perf_counter() - started) * 1000, 2))

    @staticmethod
    def _field(region: Any, name: str, default: Any = None) -> Any:
        return region.get(name, default) if isinstance(region, Mapping) else getattr(region, name, default)

    @classmethod
    def _text(cls, region: Any) -> str:
        return " ".join(str(cls._field(region, "text", "")).split())

    @classmethod
    def _block(cls, index: int, region: Any) -> dict[str, Any]:
        polygon = cls._field(region, "polygon")
        if not isinstance(polygon, list) or len(polygon) < 3:
            raise ValueError("Each recognised region must supply a polygon with at least three points.")
        points = [(float(point[0]), float(point[1])) for point in polygon]
        xs, ys = zip(*points)
        return {"block_id": f"ocr_{cls._field(region, 'index', index)}", "text": cls._text(region),
                "bbox_pixel": [min(xs), min(ys), max(xs), max(ys)]}


# Kept for callers that used the production API before pages were separated.
DocumentLayoutAnalysisService = Page3PlusLayoutAnalysisService
