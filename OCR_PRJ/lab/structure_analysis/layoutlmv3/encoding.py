"""Mã hóa LayoutLMv3 và giữ ánh xạ từ OCR tới model token."""

from __future__ import annotations

from typing import Any

from PIL import Image

from .schema import LABEL_TO_ID


MODEL_INPUT_KEYS = {
    "input_ids",
    "attention_mask",
    "bbox",
    "pixel_values",
    "token_type_ids",
}


def encode_page(
    processor: Any,
    image: Image.Image,
    words: list[dict[str, Any]],
    labels: list[str] | None = None,
    max_length: int = 512,
    stride: int = 128,
) -> list[dict[str, Any]]:
    """Tạo các cửa sổ token và ánh xạ ngược từng token về OCR word/block.

    Chỉ model token đầu tiên của mỗi OCR word nhận nhãn khi huấn luyện; các
    subtoken sau dùng -100 để không làm các từ bị tách nhỏ có trọng số lớn hơn.
    """

    if labels is not None and len(labels) != len(words):
        raise ValueError("Số nhãn phải bằng số OCR word")
    texts = [word["text"] for word in words]
    boxes = [word["bbox_1000"] for word in words]
    encoded = processor(
        images=image.convert("RGB"),
        text=texts,
        boxes=boxes,
        truncation=True,
        padding="max_length",
        max_length=max_length,
        stride=stride,
        return_overflowing_tokens=True,
        return_offsets_mapping=True,
        return_tensors="pt",
    )
    chunk_count = int(encoded["input_ids"].shape[0])
    pixel_values = encoded.get("pixel_values")
    if isinstance(pixel_values, list):
        if len(pixel_values) == 1 and chunk_count > 1:
            encoded["pixel_values"] = pixel_values * chunk_count
        elif len(pixel_values) != chunk_count:
            raise ValueError("Số tensor ảnh không khớp số cửa sổ token")
    elif pixel_values is not None and pixel_values.shape[0] == 1 and chunk_count > 1:
        encoded["pixel_values"] = pixel_values.repeat(chunk_count, 1, 1, 1)

    chunks: list[dict[str, Any]] = []
    for chunk_index in range(chunk_count):
        word_ids = encoded.word_ids(batch_index=chunk_index)
        input_ids = encoded["input_ids"][chunk_index]
        model_tokens = processor.tokenizer.convert_ids_to_tokens(input_ids.tolist())
        mappings: list[dict[str, Any]] = []
        aligned_labels: list[int] = []
        previous_word_id: int | None = None
        for token_index, (word_id, token) in enumerate(zip(word_ids, model_tokens)):
            first_subtoken = word_id is not None and word_id != previous_word_id
            mapping: dict[str, Any] = {
                "token_index": token_index,
                "model_token": token,
                "word_index": word_id,
                "is_first_subtoken": first_subtoken,
            }
            if word_id is not None:
                word = words[word_id]
                mapping.update(
                    {
                        "word_id": word["word_id"],
                        "block_id": word["block_id"],
                        "word_text": word["text"],
                        "bbox_1000": word["bbox_1000"],
                    }
                )
            mappings.append(mapping)
            if labels is not None and word_id is not None and first_subtoken:
                aligned_labels.append(LABEL_TO_ID[labels[word_id]])
            else:
                aligned_labels.append(-100)
            previous_word_id = word_id

        model_inputs = {
            key: encoded[key][chunk_index]
            for key in MODEL_INPUT_KEYS
            if key in encoded
        }
        if labels is not None:
            import torch

            model_inputs["labels"] = torch.tensor(aligned_labels, dtype=torch.long)
        chunks.append(
            {
                "chunk_index": chunk_index,
                "model_inputs": model_inputs,
                "token_mappings": mappings,
            }
        )
    return chunks


def serializable_token_mappings(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_index": chunk["chunk_index"],
            "tokens": chunk["token_mappings"],
        }
        for chunk in chunks
    ]
