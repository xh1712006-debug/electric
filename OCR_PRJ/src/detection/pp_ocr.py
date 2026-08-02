"""PP-OCRv5 text-detector adapter with a stable application contract."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any


@dataclass(frozen=True)
class Detection:
    """A detected text region in source-image pixel coordinates."""

    polygon: list[list[float]]
    score: float | None


class PPTextDetector:
    """Run the verified PP-OCRv5 Mobile text detector on a prepared page."""

    engine_version = "PP-OCRv5_mobile_det"

    def __init__(self, use_gpu: bool = False, model_name: str = engine_version) -> None:
        try:
            if not use_gpu:
                # Prevent the Windows CPU oneDNN fused-convolution failure seen
                # during detector verification; this does not alter model output.
                os.environ.setdefault("FLAGS_use_mkldnn", "0")
            os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")
            from paddleocr import TextDetection
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR is not installed. Install src/detection/requirements.txt first."
            ) from exc

        try:
            self._detector = TextDetection(
                model_name=model_name,
                device="gpu:0" if use_gpu else "cpu",
                enable_mkldnn=False,
            )
        except Exception as exc:
            raise RuntimeError(f"Could not initialise PP-OCR detector: {exc}") from exc

    def detect(self, image: Any) -> list[Detection]:
        """Detect regions from a BGR NumPy image without running recognition."""
        try:
            prediction = next(iter(self._detector.predict(image, batch_size=1)))
        except Exception as exc:
            raise RuntimeError(f"PP-OCR detection failed: {exc}") from exc

        payload = self._payload(prediction)
        polygons = payload.get("dt_polys", [])
        scores = payload.get("dt_scores", [])
        return [
            Detection(
                polygon=[[float(x), float(y)] for x, y in polygon],
                score=float(scores[index]) if index < len(scores) else None,
            )
            for index, polygon in enumerate(polygons)
        ]

    @staticmethod
    def _payload(prediction: Any) -> dict[str, Any]:
        payload = getattr(prediction, "json", prediction)
        if callable(payload):
            payload = payload()
        if not isinstance(payload, dict) and hasattr(prediction, "to_dict"):
            payload = prediction.to_dict()
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected PP-OCR result type: {type(prediction).__name__}")
        payload = payload.get("res", payload)
        if not isinstance(payload, dict):
            raise RuntimeError("PP-OCR result has no detection payload.")
        return payload
