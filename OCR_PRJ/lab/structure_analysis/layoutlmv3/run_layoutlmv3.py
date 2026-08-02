"""Điểm chạy kiểm kê, tạo mẫu gán nhãn, suy luận và đánh giá."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image

from .data import (
    PageInput,
    annotation_template,
    load_annotations,
    load_page_with_existing_ocr,
    page_inputs,
)
from .entities import bio_entities
from .metrics import classification_metrics, unavailable_metrics
from .modeling import infer_page
from .schema import LABELS
from .visualization import draw_predictions


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = EXPERIMENT_ROOT / "output" / "layoutlmv3_token_classification"
ANNOTATION_SOURCE = Path(__file__).resolve().parent / "annotations"
DEFAULT_IMAGE_ROOT = REPOSITORY_ROOT / "data" / "image"
DEFAULT_CHECKPOINT = "nnul/layoutlmv3-finetuned-funsd"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dataset_audit(image_root: Path, annotation_dir: Path) -> dict[str, Any]:
    eligible, rows = page_inputs(image_root, minimum_page=3)
    annotations, annotation_rows = load_annotations(annotation_dir)
    return {
        "image_root": str(image_root),
        "total_images": len(rows),
        "eligible_page_3_plus": len(eligible),
        "images": rows,
        "annotation_root": str(annotation_dir),
        "usable_completed_annotations": len(annotations),
        "annotations": annotation_rows,
        "usable_labeled_dataset_exists": bool(annotations),
        "conclusion": (
            "Có dữ liệu trang 3+ và annotation hoàn chỉnh."
            if eligible and annotations
            else "Chưa có đủ dữ liệu trang 3+ và annotation hoàn chỉnh để fine-tune/đánh giá."
        ),
    }


def write_empty_outputs(audit: dict[str, Any], mode: str, reason: str) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    visualization_root = OUTPUT_ROOT / "visualization"
    visualization_root.mkdir(parents=True, exist_ok=True)
    for stale_visualization in visualization_root.glob("*.png"):
        stale_visualization.unlink()
    write_json(
        OUTPUT_ROOT / "predictions.json",
        {
            "status": "not_run",
            "mode": mode,
            "reason": reason,
            "target_schema": list(LABELS),
            "pages": [],
        },
    )
    write_json(
        OUTPUT_ROOT / "entities.json",
        {
            "status": "not_run",
            "reason": reason,
            "warning": "Phân loại token không xác định quan hệ tham số–giá trị.",
            "pages": [],
        },
    )
    write_json(
        OUTPUT_ROOT / "metrics.json",
        unavailable_metrics(
            reason,
            inference_time_seconds=0.0,
            peak_vram_bytes=None,
            device=None,
            processed_pages=0,
        ),
    )
    write_json(OUTPUT_ROOT / "dataset_audit.json", audit)


def choose_pages(image_root: Path, allow_page1_smoke_test: bool) -> list[PageInput]:
    eligible, rows = page_inputs(image_root, minimum_page=3)
    if eligible or not allow_page1_smoke_test:
        return eligible
    smoke_rows = [row for row in rows if row["inferred_page_number"] == 1]
    if not smoke_rows:
        return []
    row = smoke_rows[0]
    path = Path(row["image"])
    return [PageInput(path, 1, path.stem)]


def prepare_annotation_queue(args: argparse.Namespace, audit: dict[str, Any]) -> int:
    pages = choose_pages(Path(args.image_root), args.allow_page1_smoke_test)
    if not pages:
        reason = "Không có ảnh trang 3 trở đi để tạo mẫu gán nhãn."
        write_empty_outputs(audit, "prepare", reason)
        print(reason)
        return 0
    queue = OUTPUT_ROOT / "annotation_queue"
    for page in pages[: args.max_pages or None]:
        raw_ocr, words = load_page_with_existing_ocr(
            page, REPOSITORY_ROOT, force_ocr=args.force_ocr
        )
        template = annotation_template(page, raw_ocr, words)
        if page.page_number < 3:
            template["scope_warning"] = "Chỉ là smoke test trang 1; không dùng để huấn luyện."
        write_json(queue / f"{page.document_id}.json", template)
    reason = "Đã tạo mẫu gán nhãn với label=null; chưa có ground truth."
    write_empty_outputs(audit, "prepare", reason)
    print(reason)
    return 0


def _load_runtime(checkpoint: str, device_arg: str) -> tuple[Any, Any, Any]:
    try:
        import torch
        from transformers import AutoModelForTokenClassification, AutoProcessor
    except ImportError as exc:
        raise RuntimeError(
            "Thiếu thư viện LayoutLMv3. Cài requirements-layoutlmv3.txt trước khi suy luận."
        ) from exc
    if device_arg == "auto":
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device_name = device_arg
    device = torch.device(device_name)
    processor = AutoProcessor.from_pretrained(checkpoint, apply_ocr=False)
    model = AutoModelForTokenClassification.from_pretrained(checkpoint).to(device)
    model.eval()
    return model, processor, device


def _gold_for_page(page_id: str, annotations: list[dict[str, Any]]) -> dict[str, str] | None:
    for annotation in annotations:
        if annotation["document_id"] == page_id:
            return {word["word_id"]: word["label"] for word in annotation["words"]}
    return None


def run_inference(args: argparse.Namespace, audit: dict[str, Any]) -> int:
    annotations, _ = load_annotations(Path(args.annotations_dir))
    if args.mode == "evaluate":
        test_annotations = [row for row in annotations if row["split"] == "test"]
        pages = [
            PageInput(Path(row["image_path"]), int(row["page_number"]), row["document_id"])
            for row in test_annotations
        ]
    else:
        test_annotations = []
        pages = choose_pages(Path(args.image_root), args.allow_page1_smoke_test)
    if not pages:
        reason = (
            "Không có annotation split=test hợp lệ để đánh giá."
            if args.mode == "evaluate"
            else "Không có ảnh trang 3 trở đi; không chạy mô hình và không tạo dự đoán giả."
        )
        write_empty_outputs(audit, args.mode, reason)
        print(reason)
        return 0
    pages = pages[: args.max_pages or None]
    visualization_root = OUTPUT_ROOT / "visualization"
    visualization_root.mkdir(parents=True, exist_ok=True)
    for stale_visualization in visualization_root.glob("*.png"):
        stale_visualization.unlink()
    model, processor, device = _load_runtime(args.checkpoint, args.device)

    try:
        import torch

        if device.type == "cuda":
            torch.cuda.reset_peak_memory_stats(device)
    except ImportError:
        torch = None

    prediction_pages: list[dict[str, Any]] = []
    entity_pages: list[dict[str, Any]] = []
    all_gold: list[str] = []
    all_predicted: list[str] = []
    total_inference_time = 0.0
    wall_started = time.perf_counter()

    for page in pages:
        annotated = next(
            (row for row in test_annotations if row["document_id"] == page.document_id),
            None,
        )
        if annotated is not None:
            words = annotated["words"]
            raw_ocr = {"ocr_source": "annotation_snapshot"}
        else:
            raw_ocr, words = load_page_with_existing_ocr(
                page, REPOSITORY_ROOT, force_ocr=args.force_ocr
            )
        with Image.open(page.image_path) as opened:
            result, inference_time = infer_page(
                model,
                processor,
                opened.convert("RGB"),
                words,
                device,
                max_length=args.max_length,
                stride=args.stride,
            )
        total_inference_time += inference_time
        page_payload = {
            "document_id": page.document_id,
            "page_number": page.page_number,
            "image_path": str(page.image_path),
            "ocr_source": raw_ocr.get("ocr_source"),
            "scope": "page_3_plus" if page.page_number >= 3 else "page_1_smoke_test_only",
            "inference_time_seconds": round(inference_time, 6),
            **result,
        }
        prediction_pages.append(page_payload)

        label_key = "target_schema_label" if result["schema_compatible"] else "model_label"
        entities = bio_entities(result["word_predictions"], label_key)
        entity_pages.append(
            {
                "document_id": page.document_id,
                "page_number": page.page_number,
                "label_schema": label_key,
                "relationship_warning": (
                    "Các thực thể chưa biểu diễn PARAM_VALUE thuộc PARAM_NAME nào."
                ),
                "entities": entities,
            }
        )
        draw_predictions(
            page.image_path,
            result["block_predictions"],
            OUTPUT_ROOT / "visualization" / f"{page.document_id}.png",
        )
        gold_map = _gold_for_page(page.document_id, annotations)
        if gold_map is not None and result["schema_compatible"]:
            for prediction in result["word_predictions"]:
                if prediction["word_id"] in gold_map:
                    all_gold.append(gold_map[prediction["word_id"]])
                    all_predicted.append(prediction["target_schema_label"])

    peak_vram = None
    if torch is not None and device.type == "cuda":
        peak_vram = int(torch.cuda.max_memory_allocated(device))
    schema_compatible = all(page["schema_compatible"] for page in prediction_pages)
    write_json(
        OUTPUT_ROOT / "predictions.json",
        {
            "status": "completed",
            "mode": args.mode,
            "checkpoint": args.checkpoint,
            "target_schema": list(LABELS),
            "schema_compatible": schema_compatible,
            "warning": None
            if schema_compatible
            else (
                "Nhãn pretrained không khớp schema mục tiêu; target_schema_label được để null."
            ),
            "pages": prediction_pages,
        },
    )
    write_json(
        OUTPUT_ROOT / "entities.json",
        {
            "status": "completed",
            "relationship_warning": (
                "Token classification không giải quyết quan hệ một-nhiều giữa tham số và giá trị."
            ),
            "pages": entity_pages,
        },
    )
    runtime = {
        "inference_time_seconds": round(total_inference_time, 6),
        "wall_time_seconds": round(time.perf_counter() - wall_started, 6),
        "peak_vram_bytes": peak_vram,
        "device": str(device),
        "processed_pages": len(pages),
        "python": platform.python_version(),
    }
    if all_gold:
        metrics = classification_metrics(all_gold, all_predicted)
        metrics.update({"ground_truth_available": True, "runtime": runtime})
    else:
        metrics = unavailable_metrics(
            "Không có ground truth khớp word_id, hoặc checkpoint không dùng schema mục tiêu.",
            **runtime,
        )
    write_json(OUTPUT_ROOT / "metrics.json", metrics)
    write_json(OUTPUT_ROOT / "dataset_audit.json", audit)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("audit", "prepare", "inference", "evaluate"), default="audit"
    )
    parser.add_argument("--image-root", default=str(DEFAULT_IMAGE_ROOT))
    parser.add_argument("--annotations-dir", default=str(ANNOTATION_SOURCE))
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--stride", type=int, default=128)
    parser.add_argument("--force-ocr", action="store_true")
    parser.add_argument(
        "--allow-page1-smoke-test",
        action="store_true",
        help="Chỉ kiểm tra kỹ thuật; kết quả trang 1 không phải đánh giá mục tiêu.",
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    image_root = Path(args.image_root).resolve()
    annotation_dir = Path(args.annotations_dir).resolve()
    audit = dataset_audit(image_root, annotation_dir)
    if args.mode == "audit":
        reason = "Chưa có dữ liệu trang 3+ và annotation BIO dùng được."
        if audit["eligible_page_3_plus"]:
            reason = "Đã kiểm kê; chưa yêu cầu chạy suy luận."
        write_empty_outputs(audit, "audit", reason)
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return 0
    if args.mode == "prepare":
        return prepare_annotation_queue(args, audit)
    return run_inference(args, audit)


if __name__ == "__main__":
    sys.exit(main())
