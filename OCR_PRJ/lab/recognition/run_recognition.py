"""Recognise original-image crops defined by adaptive-threshold detector polygons."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any

from crop import crop_polygon
from recognizers import build_recognizer


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "image"
DEFAULT_DETECTIONS = (
    PROJECT_ROOT
    / "output"
    / "image_detection_preprocessing_comparison"
    / "pp_ocr_detector"
    / "adaptive_threshold"
    / "detections"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "lab" / "recognition" / "output"
DEFAULT_CONFIG = Path(__file__).with_name("models.json")
IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--detections-dir", type=Path, default=DEFAULT_DETECTIONS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--models", nargs="+", default=["vietocr_vgg_transformer", "svtr_v2", "parseq"])
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--limit", type=int, help="Only process the first N images.")
    parser.add_argument("--max-regions", type=int, help="Only recognise the first N regions per image.")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def find_images(input_dir: Path, limit: int | None) -> list[Path]:
    images = sorted(path for path in input_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)
    return images[:limit] if limit is not None else images


def detection_path(detections_dir: Path, input_dir: Path, image_path: Path) -> Path:
    return detections_dir / image_path.relative_to(input_dir).with_suffix(".json")


def load_detection_payload(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Adaptive-threshold detections are missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("preprocess") != "adaptive_threshold":
        raise ValueError(f"Detection payload must use adaptive_threshold: {path}")
    if not isinstance(payload.get("detections"), list):
        raise ValueError(f"Detection payload has no detections array: {path}")
    return payload


def load_original(path: Path) -> Any:
    import cv2

    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Could not read original image: {path}")
    return image


def write_crop(path: Path, crop: Any) -> None:
    import cv2

    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), crop):
        raise RuntimeError(f"Could not write crop: {path}")


def write_recognition_overlay(path: Path, original: Any, recognitions: list[dict[str, Any]]) -> None:
    """Write the original page with detector polygons and recognised Unicode text."""
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    canvas = original.copy()
    for item in recognitions:
        points = np.asarray(item["polygon"], dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(canvas, [points], isClosed=True, color=(0, 190, 0), thickness=2, lineType=cv2.LINE_AA)

    image = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_size = max(14, min(24, image.width // 100))
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    for item in recognitions:
        polygon = item["polygon"]
        x = max(0, int(min(point[0] for point in polygon)))
        y = max(0, int(min(point[1] for point in polygon)))
        score = item.get("recognition_score")
        suffix = f" ({score:.2f})" if isinstance(score, (int, float)) else ""
        label = f"{item['index']}: {item['text']}{suffix}"
        left, top, right, bottom = draw.textbbox((x, y), label, font=font)
        label_height = bottom - top + 4
        label_y = y - label_height if y >= label_height else y
        draw.rectangle((x, label_y, min(image.width, x + right - left + 6), label_y + label_height), fill=(0, 0, 0, 190))
        draw.text((x + 3, label_y + 1), label, font=font, fill=(255, 235, 0, 255))

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(image, overlay).convert("RGB").save(path)


def run_model(model_id: str, spec: dict[str, Any], images: list[Path], args: argparse.Namespace) -> dict[str, Any]:
    recognizer = build_recognizer(spec, use_gpu=args.device == "cuda")
    model_root = args.output_dir / model_id
    run: dict[str, Any] = {"model": model_id, "label": spec.get("label", model_id), "status": "completed", "images": []}
    for image_path in images:
        relative = image_path.relative_to(args.input_dir)
        output_json = model_root / "results" / relative.with_suffix(".json")
        annotated_path = model_root / "annotated" / relative
        if output_json.exists() and not args.overwrite:
            run["images"].append({"image": str(relative), "status": "skipped-existing"})
            continue
        started = time.perf_counter()
        try:
            detector_payload = load_detection_payload(detection_path(args.detections_dir, args.input_dir, image_path))
            original = load_original(image_path)
            regions = detector_payload["detections"][: args.max_regions]
            recognised: list[dict[str, Any]] = []
            for index, detection in enumerate(regions):
                crop = crop_polygon(original, detection["polygon"])
                crop_path = model_root / "crops" / relative.parent / relative.stem / f"{index:04d}.png"
                write_crop(crop_path, crop)
                result = recognizer.recognise(crop)
                recognised.append({
                    "index": index,
                    "polygon": detection["polygon"],
                    "detection_score": detection.get("score"),
                    "text": result.text,
                    "recognition_score": result.score,
                    "crop": str(crop_path.relative_to(model_root)),
                })
            write_recognition_overlay(annotated_path, original, recognised)
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(json.dumps({
                "source_image": str(relative),
                "detection_source": str(detection_path(args.detections_dir, args.input_dir, image_path)),
                "crop_source": "original_image",
                "detector_preprocess": detector_payload.get("preprocess"),
                "recognizer": model_id,
                "annotated_image": str(annotated_path.relative_to(model_root)),
                "recognitions": recognised,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            run["images"].append({"image": str(relative), "status": "ok", "regions": len(recognised)})
            print(f"[{model_id}] {relative}: {len(recognised)} regions")
        except Exception as exc:
            run["status"] = "failed"
            run["images"].append({"image": str(relative), "status": "error", "error": " ".join(str(exc).split())[:700]})
            break
    return run


def main() -> int:
    args = parse_args()
    config = json.loads(args.model_config.read_text(encoding="utf-8"))
    unknown = sorted(set(args.models) - set(config["models"]))
    if unknown:
        raise SystemExit(f"Unknown model(s): {', '.join(unknown)}")
    images = find_images(args.input_dir, args.limit)
    if not images:
        raise SystemExit(f"No images in {args.input_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    runs = [run_model(model_id, config["models"][model_id], images, args) for model_id in args.models]
    (args.output_dir / "run_summary.json").write_text(json.dumps({
        "started_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(args.input_dir),
        "detections_dir": str(args.detections_dir),
        "crop_source": "original_image",
        "runs": runs,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if any(run["status"] == "failed" for run in runs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
