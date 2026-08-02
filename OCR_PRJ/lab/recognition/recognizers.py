"""Recognition adapters with a small common result contract."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any


@dataclass(frozen=True)
class Recognition:
    text: str
    score: float | None


class PaddleTextRecognizer:
    """PaddleOCR 3.x text recogniser operating on a single cropped line."""

    def __init__(self, model_name: str, use_gpu: bool) -> None:
        try:
            if not use_gpu:
                os.environ.setdefault("FLAGS_use_mkldnn", "0")
            os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")
            from paddleocr import TextRecognition
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR is not installed. Run: python -m pip install -r lab/recognition/requirements.txt"
            ) from exc

        try:
            self._recognizer = TextRecognition(
                model_name=model_name,
                device="gpu:0" if use_gpu else "cpu",
                enable_mkldnn=False,
            )
        except Exception as exc:
            raise RuntimeError(f"Could not initialise {model_name}: {exc}") from exc

    def recognise(self, crop: Any) -> Recognition:
        try:
            prediction = next(iter(self._recognizer.predict(crop, batch_size=1)))
        except Exception as exc:
            raise RuntimeError(f"PaddleOCR recognition failed: {exc}") from exc
        payload = self._payload(prediction)
        return Recognition(text=str(payload.get("rec_text", "")), score=self._score(payload.get("rec_score")))

    @staticmethod
    def _payload(prediction: Any) -> dict[str, Any]:
        payload = getattr(prediction, "json", prediction)
        if callable(payload):
            payload = payload()
        if not isinstance(payload, dict) and hasattr(prediction, "to_dict"):
            payload = prediction.to_dict()
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected PaddleOCR result type: {type(prediction).__name__}")
        payload = payload.get("res", payload)
        if not isinstance(payload, dict):
            raise RuntimeError("PaddleOCR result has no recognition payload.")
        return payload

    @staticmethod
    def _score(value: Any) -> float | None:
        return float(value) if isinstance(value, (int, float)) else None


class VietOCRRecognizer:
    """Vietnamese Transformer recogniser provided by the VietOCR project."""

    def __init__(self, use_gpu: bool) -> None:
        try:
            from vietocr.tool.config import Cfg
            from vietocr.tool.predictor import Predictor
        except ImportError as exc:
            raise RuntimeError("VietOCR is not installed. Install lab/recognition/requirements.txt") from exc
        config = Cfg.load_config_from_name("vgg_transformer")
        config["device"] = "cuda" if use_gpu else "cpu"
        # The recogniser checkpoint includes the trained backbone weights.
        config["cnn"]["pretrained"] = False
        self._predictor = Predictor(config)

    def recognise(self, crop: Any) -> Recognition:
        import cv2
        from PIL import Image

        image = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        try:
            text, score = self._predictor.predict(image, return_prob=True)
        except Exception as exc:
            raise RuntimeError(f"VietOCR recognition failed: {exc}") from exc
        return Recognition(text=str(text), score=float(score))


class PARSeqRecognizer:
    """Official PARSeq Torch Hub checkpoint, used as a Latin-script baseline."""

    def __init__(self, use_gpu: bool) -> None:
        try:
            import torch
            from torchvision import transforms as transforms
        except ImportError as exc:
            raise RuntimeError("PARSeq dependencies are not installed. Install lab/recognition/requirements.txt") from exc
        self._torch = torch
        self._device = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
        try:
            self._model = torch.hub.load("baudm/parseq", "parseq", pretrained=True, trust_repo=True).eval().to(self._device)
        except Exception as exc:
            raise RuntimeError(f"Could not load official PARSeq checkpoint: {exc}") from exc
        self._transform = transforms.Compose([
            transforms.Resize((32, 128), transforms.InterpolationMode.BICUBIC),
            transforms.ToTensor(),
            transforms.Normalize(0.5, 0.5),
        ])

    def recognise(self, crop: Any) -> Recognition:
        import cv2
        from PIL import Image

        image = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        batch = self._transform(image).unsqueeze(0).to(self._device)
        try:
            with self._torch.inference_mode():
                label, confidence = self._model.tokenizer.decode(self._model(batch).softmax(-1))
        except Exception as exc:
            raise RuntimeError(f"PARSeq recognition failed: {exc}") from exc
        confidence_tensor = confidence[0]
        score = float(confidence_tensor.float().mean().item())
        return Recognition(text=str(label[0]), score=score)


def build_recognizer(spec: dict[str, Any], use_gpu: bool) -> Any:
    backend = spec.get("backend")
    if backend == "paddle":
        return PaddleTextRecognizer(model_name=spec["paddle_model_name"], use_gpu=use_gpu)
    if backend == "vietocr":
        return VietOCRRecognizer(use_gpu=use_gpu)
    if backend == "parseq":
        return PARSeqRecognizer(use_gpu=use_gpu)
    raise ValueError(f"Unsupported recognition backend: {backend!r}")
