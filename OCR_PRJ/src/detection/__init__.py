"""Production text-detection components for the asynchronous OCR pipeline."""

from .pp_ocr import Detection, PPTextDetector
from .service import DetectionResult, DocumentTextDetectionService, filter_stamp_detections, stamp_overlap_ratio

__all__ = [
    "Detection",
    "DetectionResult",
    "DocumentTextDetectionService",
    "filter_stamp_detections",
    "PPTextDetector",
    "stamp_overlap_ratio",
]
