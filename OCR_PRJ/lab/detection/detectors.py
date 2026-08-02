"""Detector adapters with a common polygon-only result contract.

Heavy OCR dependencies are imported only when the matching adapter is created.
This keeps the command-line validation and unit tests usable before the models
have been installed or downloaded.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Iterable


class DetectorUnavailableError(RuntimeError):
    """Raised when a detector dependency or its model files are unavailable."""


class DetectorNotConfiguredError(RuntimeError):
    """The experiment is valid but its manually supplied checkpoint is absent."""


class DetectorExecutionError(RuntimeError):
    """A model-level inference failure; retrying every input would be pointless."""


@dataclass(frozen=True)
class Detection:
    """One detected text region, represented as a clockwise polygon."""

    polygon: list[list[float]]
    score: float | None = None


def _is_point(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) >= 2 and all(
        isinstance(coordinate, (int, float)) for coordinate in value[:2]
    )


def _as_polygon(value: Any) -> list[list[float]] | None:
    """Return a polygon when *value* looks like a sequence of 2D points."""
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    if all(_is_point(point) for point in value):
        return [[float(point[0]), float(point[1])] for point in value]
    return None


def polygons_from_nested(value: Any) -> list[list[list[float]]]:
    """Extract polygons from PaddleOCR's differently shaped legacy results."""
    polygon = _as_polygon(value)
    if polygon is not None:
        return [polygon]
    if not isinstance(value, (list, tuple)):
        return []

    polygons: list[list[list[float]]] = []
    for item in value:
        polygons.extend(polygons_from_nested(item))
    return polygons


class BaseDetector:
    def detect(self, image_path: Path) -> list[Detection]:
        raise NotImplementedError


class PaddleDetector(BaseDetector):
    """PaddleOCR 3.x detector wrapper for DB/DB++/PSE/PP-OCR models."""

    def __init__(
        self,
        model_dir: Path | None,
        model_name: str | None,
        use_gpu: bool,
        training_checkpoint_dir: Path | None = None,
    ) -> None:
        if model_dir is not None and not model_dir.is_dir():
            checkpoint_hint = ""
            if training_checkpoint_dir is not None and training_checkpoint_dir.is_dir():
                checkpoint_hint = (
                    f" Training checkpoints were found in {training_checkpoint_dir}, but they must be exported "
                    f"to Paddle inference files in {model_dir} first."
                )
            raise DetectorNotConfiguredError(
                f"Paddle inference model is missing: {model_dir}. "
                f"Set model_dir in models.json to an exported Paddle inference directory.{checkpoint_hint}"
            )
        try:
            # PaddlePaddle 3.x on Windows can fail in oneDNN fused_conv2d for
            # PaddleOCR's legacy detector. Disable the optional acceleration on
            # CPU before importing PaddleOCR and pass the equivalent API option.
            if not use_gpu:
                os.environ.setdefault("FLAGS_use_mkldnn", "0")
            # PaddleOCR 3 downloads official detector weights from BOS when a
            # local model_dir is not supplied. It is more reachable than the
            # default Hugging Face mirror in many corporate Windows networks.
            os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")
            from paddleocr import TextDetection
        except ImportError as exc:
            raise DetectorUnavailableError(
                "PaddleOCR 3.x is not installed. Run: python -m pip install -r lab/detection/requirements.txt"
            ) from exc

        options: dict[str, Any] = {
            "device": "gpu:0" if use_gpu else "cpu",
            "enable_mkldnn": False,
        }
        if model_name:
            options["model_name"] = model_name
        if model_dir is not None:
            options["model_dir"] = str(model_dir)
        try:
            self._detector = TextDetection(**options)
        except Exception as exc:  # Paddle emits several backend-specific exceptions.
            raise DetectorUnavailableError(f"Unable to initialise Paddle detector: {exc}") from exc

    def detect(self, image_path: Path) -> list[Detection]:
        try:
            prediction = next(iter(self._detector.predict(str(image_path), batch_size=1)))
        except Exception as exc:
            raise DetectorExecutionError(f"PaddleOCR failed for {image_path.name}: {exc}") from exc
        payload = paddle_prediction_payload(prediction)
        polygons = payload.get("dt_polys", [])
        scores = payload.get("dt_scores", [])
        return [
            Detection(polygon=[[float(x), float(y)] for x, y in polygon], score=float(scores[index]) if index < len(scores) else None)
            for index, polygon in enumerate(polygons)
        ]


def paddle_prediction_payload(prediction: Any) -> dict[str, Any]:
    """Normalise PaddleOCR 3.x TextDetection result objects to their payload."""
    payload = getattr(prediction, "json", prediction)
    if callable(payload):
        payload = payload()
    if not isinstance(payload, dict) and hasattr(prediction, "to_dict"):
        payload = prediction.to_dict()
    if not isinstance(payload, dict):
        raise DetectorExecutionError(f"Unexpected PaddleOCR result type: {type(prediction).__name__}")
    payload = payload.get("res", payload)
    if not isinstance(payload, dict):
        raise DetectorExecutionError("PaddleOCR result has no detection payload.")
    return payload


class CraftDetector(BaseDetector):
    """EasyOCR exposes a pretrained CRAFT detector without running recognition."""

    def __init__(self, use_gpu: bool) -> None:
        try:
            import easyocr
        except ImportError as exc:
            raise DetectorUnavailableError(
                "EasyOCR is not installed. Run: python -m pip install -r lab/detection/requirements.txt"
            ) from exc
        try:
            self._reader = easyocr.Reader(["en", "vi"], gpu=use_gpu, recognizer=False, verbose=False)
        except Exception as exc:
            raise DetectorUnavailableError(f"Unable to initialise CRAFT: {exc}") from exc

    def detect(self, image_path: Path) -> list[Detection]:
        try:
            horizontal_groups, free_groups = self._reader.detect(str(image_path))
        except Exception as exc:
            raise RuntimeError(f"CRAFT failed for {image_path.name}: {exc}") from exc

        horizontal = horizontal_groups[0] if horizontal_groups and isinstance(horizontal_groups[0], list) else horizontal_groups
        free = free_groups[0] if free_groups and isinstance(free_groups[0], list) else free_groups
        detections: list[Detection] = []
        for box in horizontal or []:
            if len(box) < 4:
                continue
            x_min, x_max, y_min, y_max = (float(value) for value in box[:4])
            detections.append(Detection([[x_min, y_min], [x_max, y_min], [x_max, y_max], [x_min, y_max]]))
        for polygon in free or []:
            converted = _as_polygon(polygon)
            if converted is not None:
                detections.append(Detection(converted))
        return detections


def build_detector(spec: dict[str, Any], project_root: Path, use_gpu: bool) -> BaseDetector:
    """Build one detector from a models.json entry."""
    backend = spec.get("backend")
    if backend == "paddle":
        configured_path = spec.get("model_dir")
        model_dir = project_root / configured_path if configured_path else None
        checkpoint_path = spec.get("training_checkpoint_dir")
        training_checkpoint_dir = project_root / checkpoint_path if checkpoint_path else None
        return PaddleDetector(
            model_dir=model_dir,
            model_name=spec.get("paddle_model_name"),
            use_gpu=use_gpu,
            training_checkpoint_dir=training_checkpoint_dir,
        )
    if backend == "easyocr_craft":
        return CraftDetector(use_gpu=use_gpu)
    raise ValueError(f"Unsupported detector backend: {backend!r}")


def supported_model_names(config: dict[str, Any]) -> Iterable[str]:
    return config["models"].keys()
