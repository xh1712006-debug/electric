"""Run production OCR plus experimental page-1 layout extraction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.detection import DocumentTextDetectionService
from src.layout_analysis.page1 import extract_page1
from src.layout_analysis.table_grid import detect_table_grid
from src.recognition import VietnameseRecognitionService


ROOT = Path(__file__).resolve().parent
DEFAULT_IMAGE = Path("data/image/page1/7SJ622_1-page-001.png")
DEFAULT_OUTPUT = ROOT / "output"


def _blocks(regions: list[dict]) -> list[dict]:
    blocks = []
    for region in regions:
        polygon = region["polygon"]
        xs, ys = [float(point[0]) for point in polygon], [float(point[1]) for point in polygon]
        blocks.append({
            "block_id": f"ocr_{region['index']}", "text": region["text"], "polygon": polygon,
            "bbox_pixel": [min(xs), min(ys), max(xs), max(ys)],
            "detection_score": region.get("detection_score"), "recognition_score": region.get("recognition_score"),
        })
    return blocks


def _overlay(image_path: Path, output_path: Path, result: dict) -> None:
    import cv2

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Cannot read {image_path}")
    block_lookup = {str(block["block_id"]): block for block in [*result["unassigned_blocks"]]}
    for value in result["fields"].values():
        values = value if isinstance(value, list) else [value]
        for item in values:
            if item is None:
                continue
            for block_id in item.get("source_block_ids", []):
                block_lookup.setdefault(str(block_id), None)
    source_blocks = result.pop("_source_blocks")
    source_lookup = {str(block["block_id"]): block for block in source_blocks}
    for name, value in result["fields"].items():
        values = value if isinstance(value, list) else [value]
        for item in values:
            if item is None:
                continue
            boxes = item.get("source_bboxes") or [source_lookup[block_id]["bbox_pixel"] for block_id in item.get("source_block_ids", []) if block_id in source_lookup]
            if not boxes:
                continue
            x1, y1 = int(min(box[0] for box in boxes)), int(min(box[1] for box in boxes))
            x2, y2 = int(max(box[2] for box in boxes)), int(max(box[3] for box in boxes))
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 200, 0), 2)
            cv2.putText(image, name, (x1, max(15, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 120, 0), 1, cv2.LINE_AA)
    for region in result["table_grid"].get("regions", []):
        rx1, ry1, rx2, ry2 = [int(value) for value in region["bbox"]]
        cv2.rectangle(image, (rx1, ry1), (rx2, ry2), (255, 0, 0), 2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), image)


def analyse_live_page(
    image_path: Path,
    output: Path,
    document_id: str,
    detector: DocumentTextDetectionService,
    recognizer: VietnameseRecognitionService,
) -> dict:
    """Run one page while allowing batch callers to reuse loaded OCR models."""

    output.mkdir(parents=True, exist_ok=True)
    detections = detector.detect_page(image_path)
    recognition = recognizer.recognise_page(image_path, detections.detections)
    blocks = _blocks(recognition.as_dict()["regions"])
    grid = detect_table_grid(image_path, output / "table_grid.png")
    page = {"document_id": document_id, "page_number": 1, "image_path": str(image_path), "block_predictions": blocks}
    result = extract_page1(page, grid)
    result["ocr"] = {"mode": "live", "detection": detections.as_dict(), "recognizer_version": recognition.recognizer_version, "recognition_elapsed_ms": recognition.elapsed_ms}
    (output / "ocr_blocks.json").write_text(json.dumps(blocks, ensure_ascii=False, indent=2), encoding="utf-8")
    result["_source_blocks"] = blocks
    _overlay(image_path, output / "review_overlay.png", result)
    (output / "page1_layout.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def analyse_cached_page(image_path: Path, ocr_blocks_path: Path, output: Path, document_id: str) -> dict:
    """Rerun only geometry/layout while preserving the auditable OCR cache."""

    output.mkdir(parents=True, exist_ok=True)
    blocks = json.loads(ocr_blocks_path.read_text(encoding="utf-8"))
    (output / "ocr_blocks.json").write_text(json.dumps(blocks, ensure_ascii=False, indent=2), encoding="utf-8")
    grid = detect_table_grid(image_path, output / "table_grid.png")
    page = {"document_id": document_id, "page_number": 1, "image_path": str(image_path), "block_predictions": blocks}
    result = extract_page1(page, grid)
    result["ocr"] = {"mode": "cached", "source": str(ocr_blocks_path)}
    result["_source_blocks"] = blocks
    _overlay(image_path, output / "review_overlay.png", result)
    (output / "page1_layout.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Page-1 template-aware layout analysis")
    parser.add_argument("image", nargs="?", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--document-id")
    parser.add_argument("--ocr-blocks", type=Path, help="Reuse auditable OCR blocks and rerun layout only")
    parser.add_argument("--gpu", action="store_true")
    args = parser.parse_args()
    if args.ocr_blocks:
        result = analyse_cached_page(args.image, args.ocr_blocks, args.output, args.document_id or args.image.stem)
    else:
        detector = DocumentTextDetectionService(use_gpu=args.gpu)
        recognizer = VietnameseRecognitionService(use_gpu=args.gpu)
        result = analyse_live_page(args.image, args.output, args.document_id or args.image.stem, detector, recognizer)
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
