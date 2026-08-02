"""Suy luận LayoutLMv3, giữ nhãn checkpoint và ánh xạ về OCR word."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from PIL import Image

from .encoding import encode_page, serializable_token_mappings
from .schema import LABELS


def schema_compatibility(id2label: dict[Any, str]) -> bool:
    return set(id2label.values()) == set(LABELS)


def infer_page(
    model: Any,
    processor: Any,
    image: Image.Image,
    words: list[dict[str, Any]],
    device: Any,
    max_length: int = 512,
    stride: int = 128,
) -> tuple[dict[str, Any], float]:
    import torch

    chunks = encode_page(processor, image, words, max_length=max_length, stride=stride)
    probability_sums: dict[int, Any] = {}
    probability_counts: defaultdict[int, int] = defaultdict(int)
    started = time.perf_counter()
    with torch.inference_mode():
        for chunk in chunks:
            inputs = {
                key: tensor.unsqueeze(0).to(device)
                for key, tensor in chunk["model_inputs"].items()
            }
            logits = model(**inputs).logits[0]
            text_token_count = len(chunk["token_mappings"])
            probabilities = torch.softmax(logits[:text_token_count], dim=-1).cpu()
            for mapping in chunk["token_mappings"]:
                word_index = mapping["word_index"]
                if word_index is None or not mapping["is_first_subtoken"]:
                    continue
                vector = probabilities[mapping["token_index"]]
                if word_index not in probability_sums:
                    probability_sums[word_index] = vector.clone()
                else:
                    probability_sums[word_index] += vector
                probability_counts[word_index] += 1
    elapsed = time.perf_counter() - started

    id2label = {int(key): value for key, value in model.config.id2label.items()}
    compatible = schema_compatibility(id2label)
    word_predictions: list[dict[str, Any]] = []
    for word_index, word in enumerate(words):
        if word_index not in probability_sums:
            continue
        average = probability_sums[word_index] / probability_counts[word_index]
        confidence, label_id = average.max(dim=-1)
        model_label = id2label[int(label_id)]
        word_predictions.append(
            {
                "word_id": word["word_id"],
                "word_index": word_index,
                "block_id": word["block_id"],
                "text": word["text"],
                "bbox_pixel": word["bbox_pixel"],
                "bbox_1000": word["bbox_1000"],
                "model_label": model_label,
                "target_schema_label": model_label if compatible else None,
                "confidence": round(float(confidence), 6),
                "source_chunk_count": probability_counts[word_index],
            }
        )

    block_predictions = aggregate_blocks(word_predictions)
    return (
        {
            "schema_compatible": compatible,
            "checkpoint_labels": id2label,
            "word_predictions": word_predictions,
            "block_predictions": block_predictions,
            "token_mappings": serializable_token_mappings(chunks),
        },
        elapsed,
    )


def aggregate_blocks(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for word in words:
        grouped[word["block_id"]].append(word)
    output: list[dict[str, Any]] = []
    for block_id, rows in grouped.items():
        scores: defaultdict[str, float] = defaultdict(float)
        for row in rows:
            scores[row["model_label"]] += float(row["confidence"])
        model_label = max(scores, key=scores.get)
        compatible_labels = {row["target_schema_label"] for row in rows}
        output.append(
            {
                "block_id": block_id,
                "text": " ".join(row["text"] for row in rows),
                "word_ids": [row["word_id"] for row in rows],
                "model_label": model_label,
                "target_schema_label": model_label
                if compatible_labels == {model_label}
                else None,
                "bbox_pixel": [
                    min(row["bbox_pixel"][0] for row in rows),
                    min(row["bbox_pixel"][1] for row in rows),
                    max(row["bbox_pixel"][2] for row in rows),
                    max(row["bbox_pixel"][3] for row in rows),
                ],
            }
        )
    return output
