"""Run text detectors on every image and save annotated results per model.

Examples:
  python lab/detection/run_comparison.py
  python lab/detection/run_comparison.py --models craft pp_ocr_detector --limit 5
  python lab/detection/run_comparison.py --device cuda
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from detectors import (
    DetectorExecutionError,
    DetectorNotConfiguredError,
    DetectorUnavailableError,
    build_detector,
    supported_model_names,
)
from preprocessing import PREPROCESSORS, load_and_preprocess, write_image


IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "image"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "image_from_detection"
DEFAULT_PREPROCESS_OUTPUT = PROJECT_ROOT / "output" / "image_detection_preprocessing_comparison"
DEFAULT_CONFIG = Path(__file__).with_name("models.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare text-detection models on a common image set.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, help="Output root; a preprocessing run defaults to a separate comparison folder.")
    parser.add_argument("--model-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--models", nargs="+", help="Model ids to run; defaults to every configured model.")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--limit", type=int, help="Run only the first N images (useful for a smoke test).")
    parser.add_argument(
        "--preprocess",
        nargs="+",
        choices=PREPROCESSORS,
        default=["original"],
        help="Image variants to compare. Selecting any non-original variant uses a new output tree by default.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Regenerate annotated images that already exist.")
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        config = json.load(file)
    if not isinstance(config.get("models"), dict) or not config["models"]:
        raise ValueError(f"{path} must contain a non-empty 'models' object.")
    return config


def find_images(input_dir: Path, limit: int | None) -> list[Path]:
    images = sorted(path for path in input_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)
    return images[:limit] if limit is not None else images


def draw_detections(image: Any, destination: Path, detections: list[Any], model_label: str) -> None:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("OpenCV and NumPy are required for output visualisation.") from exc

    image = image.copy()
    for index, detection in enumerate(detections, start=1):
        points = np.array(detection.polygon, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(image, [points], isClosed=True, color=(0, 220, 0), thickness=2, lineType=cv2.LINE_AA)
        anchor = tuple(points[0, 0])
        cv2.putText(image, str(index), anchor, cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1, cv2.LINE_AA)
    cv2.rectangle(image, (0, 0), (min(image.shape[1], 600), 31), (0, 0, 0), thickness=-1)
    cv2.putText(image, f"{model_label}: {len(detections)} regions", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(destination), image):
        raise RuntimeError(f"Could not write {destination}")


def serialise_detections(detections: list[Any]) -> list[dict[str, Any]]:
    return [{"polygon": detection.polygon, "score": detection.score} for detection in detections]


def concise_error(error: Exception, maximum_length: int = 700) -> str:
    """Keep summaries and terminal output useful when native libraries dump stacks."""
    text = " ".join(str(error).split())
    return text if len(text) <= maximum_length else f"{text[:maximum_length - 3]}..."


def run_model(
    model_id: str,
    spec: dict[str, Any],
    images: list[Path],
    args: argparse.Namespace,
) -> dict[str, Any]:
    label = spec.get("label", model_id)
    output_root = args.output_dir / model_id
    run: dict[str, Any] = {"model": model_id, "label": label, "status": "completed", "images": [], "error": None, "note": None}
    try:
        detector = build_detector(spec, PROJECT_ROOT, use_gpu=args.device == "cuda")
    except DetectorNotConfiguredError as exc:
        run["status"] = "not-configured"
        run["note"] = str(exc)
        print(f"[{model_id}] skipped: {run['note']}")
        return run
    except (DetectorUnavailableError, ValueError) as exc:
        run["status"] = "failed"
        run["error"] = str(exc)
        return run

    for image_path in images:
        relative_path = image_path.relative_to(args.input_dir)
        for method in args.preprocess:
            variant_root = output_root / method
            preprocessed_path = variant_root / "preprocessed" / relative_path
            annotated_path = variant_root / "annotated" / relative_path
            json_path = variant_root / "detections" / relative_path.with_suffix(".json")
            if annotated_path.exists() and json_path.exists() and not args.overwrite:
                run["images"].append({"image": str(relative_path), "preprocess": method, "status": "skipped-existing"})
                continue
            started = time.perf_counter()
            try:
                preprocessed, preprocess_metadata = load_and_preprocess(image_path, method, include_metadata=True)
                write_image(preprocessed_path, preprocessed)
                detections = detector.detect(preprocessed_path)
                draw_detections(preprocessed, annotated_path, detections, f"{label} / {method}")
                payload = {
                    "model": model_id,
                    "label": label,
                    "input": str(relative_path),
                    "preprocess": method,
                    "preprocess_metadata": preprocess_metadata,
                    "preprocessed_image": str(preprocessed_path.relative_to(args.output_dir)),
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                    "detections": serialise_detections(detections),
                }
                json_path.parent.mkdir(parents=True, exist_ok=True)
                json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                run["images"].append({"image": str(relative_path), "preprocess": method, "status": "ok", "count": len(detections), "elapsed_ms": payload["elapsed_ms"]})
                print(f"[{model_id}/{method}] {relative_path}: {len(detections)} regions in {payload['elapsed_ms']} ms")
            except DetectorExecutionError as exc:
                message = concise_error(exc)
                run["images"].append({"image": str(relative_path), "preprocess": method, "status": "error", "error": message})
                run["status"] = "failed"
                run["error"] = message
                print(f"[{model_id}] disabled after model error: {message}", file=sys.stderr)
                break
            except Exception as exc:
                message = concise_error(exc)
                run["images"].append({"image": str(relative_path), "preprocess": method, "status": "error", "error": message})
                print(f"[{model_id}/{method}] {relative_path}: ERROR {message}", file=sys.stderr)
        if run["status"] == "failed":
            break
    return run


def main() -> int:
    args = parse_args()
    if args.output_dir is None:
        args.output_dir = DEFAULT_PREPROCESS_OUTPUT if args.preprocess != ["original"] else DEFAULT_OUTPUT
    if not args.input_dir.is_dir():
        print(f"Input directory does not exist: {args.input_dir}", file=sys.stderr)
        return 2
    config = load_config(args.model_config)
    selected = args.models or list(supported_model_names(config))
    unknown = sorted(set(selected) - set(supported_model_names(config)))
    if unknown:
        print(f"Unknown model id(s): {', '.join(unknown)}. Available: {', '.join(supported_model_names(config))}", file=sys.stderr)
        return 2
    images = find_images(args.input_dir, args.limit)
    if not images:
        print(f"No supported images found in {args.input_dir}", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(args.input_dir),
        "image_count": len(images),
        "device": args.device,
        "preprocess": args.preprocess,
        "runs": [run_model(model_id, config["models"][model_id], images, args) for model_id in selected],
    }
    summary_path = args.output_dir / "run_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [run["model"] for run in summary["runs"] if run["status"] == "failed"]
    pending = [run["model"] for run in summary["runs"] if run["status"] == "not-configured"]
    print(f"Summary: {summary_path}")
    if pending:
        print(f"Checkpoint setup pending: {', '.join(pending)}")
    if failed:
        print(f"Failed model(s): {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
