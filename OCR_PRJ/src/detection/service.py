"""Application service used by the asynchronous OCR worker."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import time
from typing import Any

from .pp_ocr import Detection, PPTextDetector
from .preprocessing import load_detection_input


@dataclass(frozen=True)
class DetectionResult:
    """Data to persist with an OCR job before recognition/extraction begins."""

    detections: list[Detection]
    preprocessing: dict[str, Any]
    detector_version: str
    elapsed_ms: float
    suppressed_stamp_detections: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "detections": [asdict(detection) for detection in self.detections],
            "preprocessing": self.preprocessing,
            "detector_version": self.detector_version,
            "elapsed_ms": self.elapsed_ms,
            "suppressed_stamp_detections": self.suppressed_stamp_detections,
        }


def stamp_overlap_ratio(polygon: list[list[float]], stamp_mask: Any) -> float:
    """Tỷ lệ diện tích polygon detector giao với vùng mực đỏ đã nhận diện."""
    import cv2
    import numpy as np

    shape = stamp_mask.shape[:2]
    polygon_mask = np.zeros(shape, dtype=np.uint8)
    points = np.asarray(polygon, dtype=np.int32)
    if len(points) < 3:
        return 0.0
    cv2.fillPoly(polygon_mask, [points], 255)
    polygon_pixels = cv2.countNonZero(polygon_mask)
    if polygon_pixels == 0:
        return 0.0
    overlap = cv2.countNonZero(cv2.bitwise_and(polygon_mask, stamp_mask))
    return overlap / polygon_pixels


def filter_stamp_detections(
    detections: list[Detection],
    stamp_mask: Any,
    maximum_stamp_overlap: float = 0.65,
) -> tuple[list[Detection], int]:
    """Loại detection gần như chỉ thuộc dấu; giữ vùng giao một phần để review."""
    kept: list[Detection] = []
    suppressed = 0
    for detection in detections:
        if stamp_overlap_ratio(detection.polygon, stamp_mask) >= maximum_stamp_overlap:
            suppressed += 1
        else:
            kept.append(detection)
    return kept, suppressed


class DocumentTextDetectionService:
    """Preprocess one page and detect its text regions for downstream OCR."""

    def __init__(self, detector: PPTextDetector | None = None, use_gpu: bool = False) -> None:
        self._detector = detector or PPTextDetector(use_gpu=use_gpu)

    def detect_page(self, image_path: Path) -> DetectionResult:
        started = time.perf_counter()
        image, stamp_mask, preprocessing = load_detection_input(image_path)
        detections, suppressed = filter_stamp_detections(self._detector.detect(image), stamp_mask)
        return DetectionResult(
            detections=detections,
            preprocessing=preprocessing,
            detector_version=self._detector.engine_version,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            suppressed_stamp_detections=suppressed,
        )
