"""Run page-1 OCR/layout analysis from a multi-page PDF with debug artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.detection import DocumentTextDetectionService
from src.image_io import read_image, write_image
from src.pdf_form_splitter.pdf_io import render_pdf
from src.recognition import VietnameseRecognitionService

from ..table_grid import detect_table_grid
from .extractor import extract_page1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _blocks(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks = []
    for fallback_index, region in enumerate(regions):
        polygon = [[float(point[0]), float(point[1])] for point in region["polygon"]]
        xs, ys = zip(*polygon)
        blocks.append({
            "block_id": f"ocr_{region.get('index', fallback_index)}",
            "text": str(region.get("text", "")).strip(),
            "polygon": polygon,
            "bbox_pixel": [min(xs), min(ys), max(xs), max(ys)],
            "detection_score": region.get("detection_score"),
            "recognition_score": region.get("recognition_score"),
        })
    return [block for block in blocks if block["text"]]


def _field_items(value: Any) -> list[dict[str, Any]]:
    values = value if isinstance(value, list) else [value]
    return [item for item in values if isinstance(item, dict)]


def write_review_overlay(
    image_path: Path,
    output_path: Path,
    result: dict[str, Any],
    source_blocks: list[dict[str, Any]],
) -> Path:
    """Draw extracted field ownership and detected table regions."""

    import cv2

    image = read_image(image_path, cv2.IMREAD_COLOR)
    source_lookup = {str(block["block_id"]): block for block in source_blocks}
    for field_name, value in result.get("fields", {}).items():
        for item in _field_items(value):
            boxes = item.get("source_bboxes") or [
                source_lookup[str(block_id)]["bbox_pixel"]
                for block_id in item.get("source_block_ids", [])
                if str(block_id) in source_lookup
            ]
            if not boxes:
                continue
            x1 = int(min(float(box[0]) for box in boxes))
            y1 = int(min(float(box[1]) for box in boxes))
            x2 = int(max(float(box[2]) for box in boxes))
            y2 = int(max(float(box[3]) for box in boxes))
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 180, 0), 2)
            cv2.putText(
                image,
                field_name,
                (x1, max(18, y1 - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 110, 0),
                1,
                cv2.LINE_AA,
            )
    for region in result.get("table_grid", {}).get("regions", []):
        x1, y1, x2, y2 = [int(value) for value in region["bbox"]]
        cv2.rectangle(image, (x1, y1), (x2, y2), (255, 0, 0), 2)
    return write_image(output_path, image)


def analyse_pdf_page1(
    input_pdf: Path | str,
    output_dir: Path | str,
    *,
    dpi: int = 200,
    use_gpu: bool = False,
    reuse_ocr: bool = False,
    detector: Any | None = None,
    recognizer: Any | None = None,
) -> dict[str, Any]:
    """Render a PDF and analyse its first page with auditable artifacts."""

    source = Path(input_pdf).resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise FileNotFoundError(source)
    if dpi <= 0:
        raise ValueError("dpi must be greater than zero")
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rendered = render_pdf(source, output / "rendered", dpi=dpi)
    if not rendered:
        raise ValueError(f"PDF has no pages: {source}")

    source_hash = _sha256(source)
    manifest_path = output / "debug_manifest.json"
    blocks_path = output / "ocr_blocks.json"
    ocr_mode = "live"
    if reuse_ocr:
        if not blocks_path.is_file() or not manifest_path.is_file():
            raise ValueError(f"Missing matching debug cache under: {output}")
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        identity = previous.get("source", {})
        if (
            identity.get("input_pdf") != str(source)
            or identity.get("sha256") != source_hash
            or identity.get("page_count") != len(rendered)
        ):
            raise ValueError("Debug OCR cache does not match the source PDF")
        blocks = json.loads(blocks_path.read_text(encoding="utf-8"))
        ocr_mode = "cached"
    else:
        detector = detector or DocumentTextDetectionService(use_gpu=use_gpu)
        recognizer = recognizer or VietnameseRecognitionService(use_gpu=use_gpu)
        detection = detector.detect_page(rendered[0])
        recognition = recognizer.recognise_page(rendered[0], detection.detections)
        recognition_payload = recognition.as_dict()
        blocks = _blocks(recognition_payload["regions"])
        (output / "detection.json").write_text(
            json.dumps(detection.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (output / "recognition.json").write_text(
            json.dumps(recognition_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        blocks_path.write_text(json.dumps(blocks, ensure_ascii=False, indent=2), encoding="utf-8")

    grid = detect_table_grid(rendered[0], output / "table_grid.png")
    (output / "table_grid.json").write_text(
        json.dumps(grid, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    page = {
        "document_id": source.stem,
        "page_number": 1,
        "image_path": str(rendered[0]),
        "block_predictions": blocks,
    }
    result = extract_page1(page, grid)
    result["ocr"] = {"mode": ocr_mode}
    (output / "page1_layout.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_review_overlay(rendered[0], output / "review_overlay.png", result, blocks)

    manifest = {
        "schema_version": "1.0",
        "source": {
            "input_pdf": str(source),
            "sha256": source_hash,
            "page_count": len(rendered),
        },
        "render": {"dpi": dpi, "pages": [str(path) for path in rendered]},
        "analysis": {
            "analysed_pages": [1],
            "other_pages": list(range(2, len(rendered) + 1)),
            "other_pages_status": "not_applicable_to_page1_analyser",
            "ocr_mode": ocr_mode,
            "table_grid_available": bool(grid.get("available")),
            "warnings": result.get("warnings", []),
            "summary": result.get("summary", {}),
        },
        "artifacts": {
            "detection": str(output / "detection.json"),
            "recognition": str(output / "recognition.json"),
            "page1_layout": str(output / "page1_layout.json"),
            "ocr_blocks": str(blocks_path),
            "table_grid_json": str(output / "table_grid.json"),
            "table_grid_image": str(output / "table_grid.png"),
            "review_overlay": str(output / "review_overlay.png"),
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
