"""Reuse cached OCR or the selected production detector/recognizer pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


PAGE_PATTERNS = (
    re.compile(r"page[-_]?0*(\d+)", re.IGNORECASE),
    re.compile(r"_p0*(\d+)(?:$|[_-])", re.IGNORECASE),
)


def infer_page_number(image_path: Path, payload: dict[str, Any] | None = None) -> tuple[int, str]:
    """Return page number and provenance without treating document variant IDs as pages."""
    if payload and isinstance(payload.get("page_number"), int):
        return int(payload["page_number"]), "ocr_payload"
    for pattern in PAGE_PATTERNS:
        match = pattern.search(image_path.stem)
        if match:
            return int(match.group(1)), "filename"
    return 1, "default_assumption"


class OCRProvider:
    """Obtain OCR blocks while keeping production code outside the experiment."""

    def __init__(self, recognition_dir: Path, detection_dir: Path, use_gpu: bool = False) -> None:
        self.recognition_dir = recognition_dir
        self.detection_dir = detection_dir
        self.use_gpu = use_gpu
        self._detector: Any = None
        self._recognizer: Any = None

    def read_page(self, image_path: Path, input_dir: Path) -> dict[str, Any]:
        relative = image_path.relative_to(input_dir)
        recognition_path = self.recognition_dir / relative.with_suffix(".json")
        if recognition_path.is_file():
            return self._from_cached_recognition(image_path, recognition_path)

        detection_path = self.detection_dir / relative.with_suffix(".json")
        if detection_path.is_file():
            detection_payload = json.loads(detection_path.read_text(encoding="utf-8"))
            detections = detection_payload["detections"]
            detector_metadata = {
                "detector_version": detection_payload.get("model", "pp_ocr_detector"),
                "preprocessing": detection_payload.get("preprocess_metadata", {}),
                "detection_source": str(detection_path),
            }
        else:
            if self._detector is None:
                from src.detection import DocumentTextDetectionService

                self._detector = DocumentTextDetectionService(use_gpu=self.use_gpu)
            detection_result = self._detector.detect_page(image_path)
            detections = detection_result.as_dict()["detections"]
            detector_metadata = {
                "detector_version": detection_result.detector_version,
                "preprocessing": detection_result.preprocessing,
                "detection_source": "live_production_service",
            }

        if self._recognizer is None:
            from src.recognition import VietnameseRecognitionService

            self._recognizer = VietnameseRecognitionService(use_gpu=self.use_gpu)
        recognition_result = self._recognizer.recognise_page(image_path, detections)
        page_number, page_source = infer_page_number(image_path)
        return {
            "source_image": str(image_path),
            "page_number": page_number,
            "page_number_source": page_source,
            **detector_metadata,
            "recognizer_version": recognition_result.recognizer_version,
            "recognition_source": "live_production_service",
            "blocks": [
                {
                    "id": f"b{region.index:04d}",
                    "text": region.text,
                    "polygon": region.polygon,
                    "detection_confidence": region.detection_score,
                    "recognition_confidence": region.recognition_score,
                }
                for region in recognition_result.regions
            ],
        }

    @staticmethod
    def _from_cached_recognition(image_path: Path, recognition_path: Path) -> dict[str, Any]:
        payload = json.loads(recognition_path.read_text(encoding="utf-8"))
        page_number, page_source = infer_page_number(image_path, payload)
        recognitions = payload.get("recognitions", payload.get("regions", []))
        blocks = []
        for index, region in enumerate(recognitions):
            blocks.append({
                "id": f"b{int(region.get('index', index)):04d}",
                "text": str(region.get("text", "")),
                "polygon": region["polygon"],
                "detection_confidence": region.get("detection_score"),
                "recognition_confidence": region.get("recognition_score"),
            })
        return {
            "source_image": str(image_path),
            "page_number": page_number,
            "page_number_source": page_source,
            "detector_version": payload.get("detector_version", "pp_ocr_detector/adaptive_threshold"),
            "preprocessing": {"name": payload.get("detector_preprocess", "adaptive_threshold")},
            "detection_source": payload.get("detection_source"),
            "recognizer_version": payload.get("recognizer", payload.get("recognizer_version", "vietocr_vgg_transformer")),
            "recognition_source": str(recognition_path),
            "blocks": blocks,
        }
