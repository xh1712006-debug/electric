"""Generate review images for red-stamp suppression in the production detector."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.image_io import read_image, write_image

from .preprocessing import load_detection_input
from .service import DocumentTextDetectionService


def preview_page(image_path: Path, output_directory: Path, service: DocumentTextDetectionService) -> None:
    import cv2
    import numpy as np

    original = read_image(image_path, cv2.IMREAD_COLOR)
    if original is None:
        raise ValueError(f"Không đọc được ảnh: {image_path}")
    prepared, stamp_mask, metadata = load_detection_input(image_path)
    result = service.detect_page(image_path)
    overlay = original.copy()
    red_layer = np.zeros_like(overlay)
    red_layer[:, :] = (0, 0, 255)
    selected = stamp_mask > 0
    blended = cv2.addWeighted(overlay, 0.45, red_layer, 0.55, 0)
    overlay[selected] = blended[selected]
    for detection in result.detections:
        points = np.asarray(detection.polygon, dtype=np.int32)
        cv2.polylines(overlay, [points], True, (0, 180, 0), 2)
    destination = output_directory / image_path.stem
    destination.mkdir(parents=True, exist_ok=True)
    write_image(destination / "original_with_stamp_mask_and_detections.png", overlay)
    write_image(destination / "detector_input_without_red_stamp.png", prepared)
    write_image(destination / "red_stamp_mask.png", stamp_mask)
    (destination / "detection.json").write_text(
        json.dumps({"preprocessing": metadata, "result": result.as_dict()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Tạo ảnh review cho xử lý con dấu đỏ trước text detection")
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("output") / "detection_red_stamp_preview")
    parser.add_argument("--gpu", action="store_true")
    args = parser.parse_args()
    service = DocumentTextDetectionService(use_gpu=args.gpu)
    for image_path in args.images:
        preview_page(image_path, args.output, service)
    print(json.dumps({"output": str(args.output), "images": len(args.images)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
