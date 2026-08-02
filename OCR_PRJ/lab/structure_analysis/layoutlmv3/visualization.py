"""Vẽ nhãn dự đoán trên ảnh gốc."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def _color(label: str) -> tuple[int, int, int]:
    digest = hashlib.md5(label.encode("utf-8"), usedforsecurity=False).digest()
    return tuple(70 + channel % 150 for channel in digest[:3])


def draw_predictions(
    image_path: Path,
    block_predictions: list[dict[str, Any]],
    destination: Path,
) -> None:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for prediction in block_predictions:
        bbox = tuple(int(round(value)) for value in prediction["bbox_pixel"])
        label = prediction.get("target_schema_label") or prediction.get("model_label") or "O"
        color = _color(label)
        draw.rectangle(bbox, outline=color, width=3)
        caption = f"{label} | {prediction['block_id']}"
        text_bbox = draw.textbbox((bbox[0], bbox[1]), caption, font=font)
        draw.rectangle(text_bbox, fill=color)
        draw.text((bbox[0], bbox[1]), caption, fill="black", font=font)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
