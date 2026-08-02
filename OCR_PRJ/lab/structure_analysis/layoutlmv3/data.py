"""Đọc OCR hiện có và chuyển block OCR thành từ có tọa độ ổn định."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from lab.structure_analysis.ocr_input import (
    OCRProvider,
    infer_page_number,
)

from .schema import LABEL_TO_ID, validate_bio_sequence


WORD_PATTERN = re.compile(r"\S+", re.UNICODE)
SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


@dataclass(frozen=True)
class PageInput:
    image_path: Path
    page_number: int
    document_id: str


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def polygon_to_rect(polygon: Iterable[Iterable[float]]) -> list[float]:
    points = [list(point) for point in polygon]
    if not points:
        return [0.0, 0.0, 0.0, 0.0]
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def normalize_bbox_1000(
    bbox: Iterable[float], image_width: int, image_height: int
) -> list[int]:
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Kích thước ảnh phải lớn hơn 0")
    x0, y0, x1, y1 = [float(value) for value in bbox]
    normalized = [
        round(_clamp(x0 / image_width, 0.0, 1.0) * 1000),
        round(_clamp(y0 / image_height, 0.0, 1.0) * 1000),
        round(_clamp(x1 / image_width, 0.0, 1.0) * 1000),
        round(_clamp(y1 / image_height, 0.0, 1.0) * 1000),
    ]
    normalized[2] = max(normalized[0], normalized[2])
    normalized[3] = max(normalized[1], normalized[3])
    return normalized


def _word_bbox(block_bbox: list[float], start: int, end: int, text_length: int) -> list[float]:
    """Chia gần đúng bbox block theo vị trí ký tự, không thay đổi OCR gốc."""

    x0, y0, x1, y1 = block_bbox
    denominator = max(1, text_length)
    width = max(0.0, x1 - x0)
    return [
        x0 + width * start / denominator,
        y0,
        x0 + width * end / denominator,
        y1,
    ]


def blocks_to_words(raw_ocr: dict[str, Any]) -> list[dict[str, Any]]:
    """Tạo ánh xạ block → từ; ID ổn định theo thứ tự OCR đầu vào."""

    image_width = int(raw_ocr["image_width"])
    image_height = int(raw_ocr["image_height"])
    words: list[dict[str, Any]] = []
    for block_index, block in enumerate(raw_ocr.get("blocks", [])):
        text = str(block.get("text", ""))
        if not text.strip():
            continue
        block_id = str(block.get("block_id") or block.get("id") or f"b{block_index:04d}")
        polygon = block.get("polygon") or []
        block_bbox = polygon_to_rect(polygon)
        for match in WORD_PATTERN.finditer(text):
            bbox = _word_bbox(block_bbox, match.start(), match.end(), len(text))
            word_index = len(words)
            words.append(
                {
                    "word_id": f"w{word_index:05d}",
                    "word_index": word_index,
                    "block_id": block_id,
                    "block_index": block_index,
                    "text": match.group(0),
                    "block_text": text,
                    "bbox_pixel": [round(value, 3) for value in bbox],
                    "bbox_1000": normalize_bbox_1000(
                        bbox, image_width, image_height
                    ),
                    "block_bbox_pixel": [round(value, 3) for value in block_bbox],
                    "detection_confidence": block.get("detection_confidence"),
                    "recognition_confidence": block.get("recognition_confidence"),
                }
            )
    return words


def page_inputs(image_root: Path, minimum_page: int = 3) -> tuple[list[PageInput], list[dict[str, Any]]]:
    image_root = image_root.resolve()
    all_images = sorted(
        path
        for path in image_root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGES
    )
    audit_rows: list[dict[str, Any]] = []
    eligible: list[PageInput] = []
    for path in all_images:
        page_number, page_number_source = infer_page_number(path)
        document_id = path.stem
        row = {
            "image": str(path),
            "document_id": document_id,
            "inferred_page_number": page_number,
            "page_number_source": page_number_source,
            "eligible": page_number >= minimum_page,
        }
        audit_rows.append(row)
        if row["eligible"]:
            eligible.append(PageInput(path, page_number, document_id))
    return eligible, audit_rows


def load_page_with_existing_ocr(
    page: PageInput, repository_root: Path, force_ocr: bool = False
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    recognition_dir = (
        repository_root
        / "lab"
        / "recognition"
        / "output"
        / "vietocr_vgg_transformer"
        / "results"
    )
    detection_dir = (
        repository_root
        / "output"
        / "image_detection_preprocessing_comparison"
        / "pp_ocr_detector"
        / "adaptive_threshold"
        / "detections"
    )
    if force_ocr:
        recognition_dir = repository_root / "__force_live_ocr__"
        detection_dir = repository_root / "__force_live_detection__"
    provider = OCRProvider(recognition_dir, detection_dir, use_gpu=False)
    input_root = repository_root / "data" / "image"
    raw_ocr = provider.read_page(page.image_path, input_root)
    width, height = image_size(page.image_path)
    raw_ocr["image_width"] = width
    raw_ocr["image_height"] = height
    raw_ocr["ocr_source"] = raw_ocr.get("recognition_source")
    return raw_ocr, blocks_to_words(raw_ocr)


def annotation_template(
    page: PageInput, raw_ocr: dict[str, Any], words: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "status": "draft",
        "document_id": page.document_id,
        "image_path": str(page.image_path),
        "page_number": page.page_number,
        "split": None,
        "image_size": {
            "width": raw_ocr["image_width"],
            "height": raw_ocr["image_height"],
        },
        "ocr_source": raw_ocr.get("ocr_source"),
        "words": [
            {
                "word_id": word["word_id"],
                "block_id": word["block_id"],
                "text": word["text"],
                "bbox_pixel": word["bbox_pixel"],
                "bbox_1000": word["bbox_1000"],
                "label": None,
            }
            for word in words
        ],
        "annotation_notes": [],
    }


def validate_completed_annotation(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("status") != "completed":
        errors.append("status phải là 'completed'")
    if int(payload.get("page_number", 0)) < 3:
        errors.append("Chỉ chấp nhận annotation từ trang 3 trở đi")
    if payload.get("split") not in {"train", "validation", "test"}:
        errors.append("split phải là train, validation hoặc test")
    words = payload.get("words")
    if not isinstance(words, list) or not words:
        errors.append("words phải là danh sách không rỗng")
        return errors
    labels: list[str] = []
    seen_ids: set[str] = set()
    for index, word in enumerate(words):
        word_id = word.get("word_id")
        if not word_id or word_id in seen_ids:
            errors.append(f"Từ {index}: word_id thiếu hoặc trùng")
        seen_ids.add(word_id)
        label = word.get("label")
        if label not in LABEL_TO_ID:
            errors.append(f"Từ {index}: label {label!r} không hợp lệ")
        else:
            labels.append(label)
        bbox = word.get("bbox_1000")
        if not (
            isinstance(bbox, list)
            and len(bbox) == 4
            and all(isinstance(value, int) and 0 <= value <= 1000 for value in bbox)
        ):
            errors.append(f"Từ {index}: bbox_1000 không hợp lệ")
    if len(labels) == len(words):
        errors.extend(validate_bio_sequence(labels))
    return errors


def load_annotations(annotation_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    completed: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    if not annotation_dir.exists():
        return completed, audit
    for path in sorted(annotation_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            errors = validate_completed_annotation(payload)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            payload = None
            errors = [str(exc)]
        audit.append(
            {
                "path": str(path),
                "usable": not errors,
                "errors": errors,
            }
        )
        if payload is not None and not errors:
            payload["_annotation_path"] = str(path)
            completed.append(payload)
    return completed, audit


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size
