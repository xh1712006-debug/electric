"""Batch page-1 extraction with one output directory per relay-form code."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from src.detection import DocumentTextDetectionService
from src.recognition import VietnameseRecognitionService

from .run_experiment import DEFAULT_OUTPUT, analyse_cached_page, analyse_live_page


def document_code(image_path: Path) -> str:
    return re.sub(r"-page-\d+$", "", image_path.stem, flags=re.IGNORECASE)


def source_images(image_root: Path) -> list[Path]:
    """Use canonical rendered page names; omit annotations and duplicate aliases."""

    return sorted(path for path in image_root.glob("*-page-001.png") if "(annotate)" not in path.stem.lower())


def main() -> int:
    parser = argparse.ArgumentParser(description="Run page-1 extraction for every canonical page-001 image")
    parser.add_argument("--image-root", type=Path, default=Path("data/image/page1"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--reuse-ocr", action="store_true", help="Rerun layout from each existing output/<code>/ocr_blocks.json")
    args = parser.parse_args()
    images = source_images(args.image_root)
    if not images:
        raise ValueError(f"No canonical *-page-001.png files under {args.image_root}")
    detector = None if args.reuse_ocr else DocumentTextDetectionService(use_gpu=args.gpu)
    recognizer = None if args.reuse_ocr else VietnameseRecognitionService(use_gpu=args.gpu)
    pages = []
    for image in images:
        code = document_code(image)
        document_output = args.output / code
        if args.reuse_ocr:
            ocr_blocks = document_output / "ocr_blocks.json"
            if not ocr_blocks.exists():
                raise ValueError(f"Missing cached OCR blocks: {ocr_blocks}")
            result = analyse_cached_page(image, ocr_blocks, document_output, code)
        else:
            assert detector is not None and recognizer is not None
            result = analyse_live_page(image, document_output, code, detector, recognizer)
        pages.append({"document_id": code, "image": str(image), "summary": result["summary"], "warnings": result["warnings"]})
        print(json.dumps(pages[-1], ensure_ascii=False))
    summary = {"pages": len(pages), "output_root": str(args.output), "documents": pages}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
