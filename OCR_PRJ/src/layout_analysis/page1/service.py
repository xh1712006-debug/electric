"""Production adapter from recognised regions to the page-1 extractor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Iterable, Mapping

from ..table_grid import detect_table_grid
from .extractor import extract_page1
from .relationships import RelationshipPolicy
from .rules import FieldRuleRegistry, load_field_rule_registry


@dataclass(frozen=True)
class Page1LayoutResult:
    """Structured page-1 payload plus production timing metadata."""

    payload: dict[str, Any]
    elapsed_ms: float

    def as_dict(self) -> dict[str, Any]:
        return {**self.payload, "elapsed_ms": self.elapsed_ms}


class Page1LayoutAnalysisService:
    """Analyse the fixed page-1 cover layout from recognition output."""

    def __init__(
        self,
        *,
        field_rule_overlay_path: Path | str | None = None,
        field_rule_registry: FieldRuleRegistry | None = None,
        relationship_policy: RelationshipPolicy | None = None,
    ) -> None:
        if field_rule_overlay_path is not None and field_rule_registry is not None:
            raise ValueError("Use field_rule_overlay_path or field_rule_registry, not both.")
        self._field_rule_registry = field_rule_registry or load_field_rule_registry(
            overlay_path=field_rule_overlay_path
        )
        self._relationship_policy = relationship_policy

    def analyse_page(
        self,
        image_path: Path | str,
        recognised_regions: Iterable[Any],
        *,
        document_id: str,
        page_number: int = 1,
    ) -> Page1LayoutResult:
        if page_number != 1:
            raise ValueError("Page1LayoutAnalysisService only accepts page_number=1.")
        started = time.perf_counter()
        blocks = [
            self._block(index, region)
            for index, region in enumerate(recognised_regions)
            if self._text(region)
        ]
        page = {
            "document_id": document_id,
            "page_number": 1,
            "image_path": str(image_path),
            "block_predictions": blocks,
        }
        payload = extract_page1(
            page,
            detect_table_grid(Path(image_path)),
            field_rule_registry=self._field_rule_registry,
            relationship_policy=self._relationship_policy,
        )
        return Page1LayoutResult(payload, round((time.perf_counter() - started) * 1000, 2))

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
        return {
            "block_id": f"ocr_{cls._field(region, 'index', index)}",
            "text": cls._text(region),
            "polygon": [list(point) for point in points],
            "bbox_pixel": [min(xs), min(ys), max(xs), max(ys)],
            "detection_score": cls._field(region, "detection_score"),
            "recognition_score": cls._field(region, "recognition_score"),
        }
