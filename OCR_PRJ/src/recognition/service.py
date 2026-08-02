"""Application service that combines detector geometry with VietOCR."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import time
from typing import Any, Iterable, Mapping

from src.image_io import read_image

from .crop import crop_polygon
from .vietocr import VietOCRRecognizer


@dataclass(frozen=True)
class RecognisedRegion:
    index: int
    polygon: list[list[float]]
    detection_score: float | None
    text: str
    recognition_score: float


@dataclass(frozen=True)
class PageRecognitionResult:
    regions: list[RecognisedRegion]
    recognizer_version: str
    elapsed_ms: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "regions": [asdict(region) for region in self.regions],
            "recognizer_version": self.recognizer_version,
            "elapsed_ms": self.elapsed_ms,
        }


class VietnameseRecognitionService:
    """Recognise original-image crops defined by the selected detector output."""

    def __init__(self, recognizer: VietOCRRecognizer | None = None, use_gpu: bool = False) -> None:
        self._recognizer = recognizer or VietOCRRecognizer(use_gpu=use_gpu)

    def recognise_page(self, image_path: Path, detections: Iterable[Any]) -> PageRecognitionResult:
        """Use detector polygons as geometry, but always read pixels from the original page."""
        import cv2

        original = read_image(image_path, cv2.IMREAD_COLOR)

        started = time.perf_counter()
        regions: list[RecognisedRegion] = []
        for index, detection in enumerate(detections):
            polygon, detection_score = self._detection_fields(detection)
            recognition = self._recognizer.recognise(crop_polygon(original, polygon))
            regions.append(RecognisedRegion(
                index=index,
                polygon=polygon,
                detection_score=detection_score,
                text=recognition.text,
                recognition_score=recognition.score,
            ))
        return PageRecognitionResult(
            regions=regions,
            recognizer_version=self._recognizer.model_version,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    @staticmethod
    def _detection_fields(detection: Any) -> tuple[list[list[float]], float | None]:
        if isinstance(detection, Mapping):
            polygon = detection.get("polygon")
            score = detection.get("score", detection.get("detection_score"))
        else:
            polygon = getattr(detection, "polygon", None)
            score = getattr(detection, "score", None)
        if not isinstance(polygon, list):
            raise ValueError("Each detection must supply a polygon list.")
        converted_polygon = [[float(x), float(y)] for x, y in polygon]
        return converted_polygon, float(score) if isinstance(score, (int, float)) else None
