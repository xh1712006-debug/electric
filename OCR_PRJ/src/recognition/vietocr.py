"""VietOCR VGG Transformer adapter for Vietnamese text lines."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Recognition:
    text: str
    score: float


class VietOCRRecognizer:
    """Load the VietOCR VGG Transformer checkpoint once per worker process."""

    model_version = "vietocr_vgg_transformer"

    def __init__(self, use_gpu: bool = False) -> None:
        try:
            from vietocr.tool.config import Cfg
            from vietocr.tool.predictor import Predictor
        except ImportError as exc:
            raise RuntimeError("VietOCR is not installed. Install src/recognition/requirements.txt") from exc

        # load_config_from_name fetches YAML from vocr.vn on every process
        # start. Keep the selected upstream config in production source so the
        # app can start offline once the model weights have been downloaded.
        config = Cfg.load_config_from_file(Path(__file__).with_name("vgg_transformer.yml"))
        config["device"] = "cuda" if use_gpu else "cpu"
        # The selected checkpoint already has trained backbone weights.
        config["cnn"]["pretrained"] = False
        try:
            self._predictor = Predictor(config)
        except Exception as exc:
            raise RuntimeError(f"Could not initialise VietOCR: {exc}") from exc

    def recognise(self, crop: Any) -> Recognition:
        """Recognise a BGR, horizontally oriented text crop."""
        import cv2
        from PIL import Image

        image = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        try:
            text, score = self._predictor.predict(image, return_prob=True)
        except Exception as exc:
            raise RuntimeError(f"VietOCR recognition failed: {exc}") from exc
        return Recognition(text=str(text), score=float(score))
