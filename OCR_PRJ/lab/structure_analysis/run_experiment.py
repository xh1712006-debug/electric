"""Run the heuristic document layout-graph baseline on OCR page blocks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any

import cv2

from heuristics import detect_table_candidates, infer_semantic_roles, reconstruct_records
from layout_graph import assign_reading_rows, build_graph, normalize_blocks
from ocr_input import OCRProvider, infer_page_number
from visualization import image_line_evidence, write_visualization


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "image"
DEFAULT_RECOGNITION = PROJECT_ROOT / "lab" / "recognition" / "output" / "vietocr_vgg_transformer" / "results"
DEFAULT_DETECTIONS = PROJECT_ROOT / "output" / "image_detection_preprocessing_comparison" / "pp_ocr_detector" / "adaptive_threshold" / "detections"
OUTPUT_ROOT = Path(__file__).with_name("output") / "heuristic_layout_graph"
IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--recognition-dir", type=Path, default=DEFAULT_RECOGNITION)
    parser.add_argument("--detections-dir", type=Path, default=DEFAULT_DETECTIONS)
    parser.add_argument("--images", nargs="+", help="Optional image names relative to input-dir.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--include-page-2", action="store_true", help="Page 2 is skipped unless explicitly enabled.")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    return parser.parse_args()


def find_images(input_dir: Path, names: list[str] | None, limit: int | None) -> list[Path]:
    if names:
        images = [input_dir / name for name in names]
        missing = [str(path) for path in images if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"Input image(s) not found: {', '.join(missing)}")
    else:
        images = sorted(path for path in input_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)
    return images[:limit] if limit is not None else images


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def process_page(image_path: Path, raw_ocr: dict[str, Any], started: float) -> dict[str, Any]:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"OpenCV could not read {image_path}")
    height, width = image.shape[:2]
    blocks = normalize_blocks(raw_ocr["blocks"], width, height, raw_ocr["page_number"])
    rows = assign_reading_rows(blocks)
    infer_semantic_roles(blocks, rows)
    graph = build_graph(blocks, rows)
    records = reconstruct_records(blocks, rows)
    lines = image_line_evidence(image)
    tables = detect_table_candidates(rows, blocks, lines)
    output_dir = OUTPUT_ROOT / image_path.stem / f"page_{raw_ocr['page_number']:03d}"
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    write_json(output_dir / "raw_ocr.json", raw_ocr)
    write_json(output_dir / "normalized_blocks.json", {
        "source_image": str(image_path),
        "image_size": {"width": width, "height": height},
        "coordinate_system": "normalized_[0,1]",
        "blocks": blocks,
    })
    write_json(output_dir / "graph.json", {
        "source_image": str(image_path),
        "page_number": raw_ocr["page_number"],
        **graph,
    })
    write_json(output_dir / "reconstructed_structure.json", {
        "source_image": str(image_path),
        "page_number": raw_ocr["page_number"],
        "records": records,
        "possible_tables": tables,
        "image_line_evidence": lines,
        "ground_truth_available": False,
        "correctness_claim": "none; heuristic hypotheses require labeled evaluation",
    })
    write_visualization(image_path, blocks, records, output_dir / "visualization.png")

    assigned = {block_id for record in records for block_id in record["block_ids"]}
    return {
        "source_image": str(image_path),
        "page_number": raw_ocr["page_number"],
        "page_number_source": raw_ocr["page_number_source"],
        "output_directory": str(output_dir),
        "ocr_blocks": len(blocks),
        "reconstructed_records": len(records),
        "multi_line_records": sum(bool(record["is_multiline"]) for record in records),
        "multi_value_records": sum(bool(record["is_multi_value"]) for record in records),
        "unassigned_blocks": len(blocks) - len(assigned),
        "possible_tables": len(tables),
        "processing_time_ms": elapsed_ms,
    }


def main() -> int:
    args = parse_args()
    images = find_images(args.input_dir, args.images, args.limit)
    provider = OCRProvider(args.recognition_dir, args.detections_dir, use_gpu=args.device == "cuda")
    page_summaries: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for image_path in images:
        try:
            page_started = time.perf_counter()
            filename_page, filename_page_source = infer_page_number(image_path)
            if filename_page == 2 and filename_page_source == "filename" and not args.include_page_2:
                skipped.append({"source_image": str(image_path), "reason": "page_2_ignored_before_ocr"})
                continue
            raw = provider.read_page(image_path, args.input_dir)
            if raw["page_number"] == 2 and not args.include_page_2:
                skipped.append({"source_image": str(image_path), "reason": "page_2_ignored"})
                continue
            summary = process_page(image_path, raw, page_started)
            page_summaries.append(summary)
            print(f"{image_path.name}: {summary['ocr_blocks']} blocks -> {summary['reconstructed_records']} records")
        except Exception as exc:
            errors.append({"source_image": str(image_path), "error": " ".join(str(exc).split())[:1000]})
            print(f"{image_path.name}: ERROR {errors[-1]['error']}", file=sys.stderr)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "heuristic_layout_graph",
        "ground_truth_available": False,
        "processed_pages": len(page_summaries),
        "number_of_ocr_blocks": sum(page["ocr_blocks"] for page in page_summaries),
        "number_of_reconstructed_records": sum(page["reconstructed_records"] for page in page_summaries),
        "number_of_multi_line_records": sum(page["multi_line_records"] for page in page_summaries),
        "number_of_unassigned_blocks": sum(page["unassigned_blocks"] for page in page_summaries),
        "processing_time_ms": round(sum(page["processing_time_ms"] for page in page_summaries), 2),
        "pages": page_summaries,
        "skipped_pages": skipped,
        "errors": errors,
    }
    write_json(OUTPUT_ROOT / "summary.json", summary)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
