"""CLI for PDF-based page-1 layout debugging."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pdf_debug import analyse_pdf_page1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a multi-page PDF and produce page-1 OCR/layout debug artifacts"
    )
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--reuse-ocr", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = args.output or Path("output") / "page1_pdf_debug" / args.input_pdf.stem
    manifest = analyse_pdf_page1(
        args.input_pdf,
        output,
        dpi=args.dpi,
        use_gpu=args.gpu,
        reuse_ocr=args.reuse_ocr,
    )
    print(json.dumps(manifest["analysis"], ensure_ascii=False))
    return 0
