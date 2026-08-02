"""Ghép chuỗi BIO thành thực thể; không suy luận quan hệ record."""

from __future__ import annotations

from typing import Any


def _union_bbox(boxes: list[list[float]]) -> list[float]:
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def bio_entities(
    predictions: list[dict[str, Any]], label_key: str
) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def finish() -> None:
        nonlocal current
        if current is None:
            return
        current["text"] = " ".join(current.pop("text_parts"))
        current["bbox_pixel"] = _union_bbox(current.pop("boxes"))
        current["confidence"] = round(
            sum(current.pop("confidences")) / len(current["word_ids"]), 6
        )
        current["entity_id"] = f"e{len(entities):05d}"
        entities.append(current)
        current = None

    for prediction in sorted(predictions, key=lambda row: row["word_index"]):
        label = prediction.get(label_key)
        if not label or label == "O" or "-" not in label:
            finish()
            continue
        prefix, entity_type = label.split("-", 1)
        continues = prefix == "I" and current and current["entity_type"] == entity_type
        if not continues:
            finish()
            current = {
                "entity_type": entity_type,
                "label_schema": label_key,
                "word_ids": [],
                "block_ids": [],
                "text_parts": [],
                "boxes": [],
                "confidences": [],
            }
        assert current is not None
        current["word_ids"].append(prediction["word_id"])
        if prediction["block_id"] not in current["block_ids"]:
            current["block_ids"].append(prediction["block_id"])
        current["text_parts"].append(prediction["text"])
        current["boxes"].append(prediction["bbox_pixel"])
        current["confidences"].append(float(prediction.get("confidence") or 0.0))
    finish()
    return entities
