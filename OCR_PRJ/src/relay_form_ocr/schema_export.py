"""Deterministically export the public request and result JSON Schemas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .schemas import OcrRequest, OcrResult, SCHEMA_VERSION


DEFAULT_SCHEMA_DIR = Path("contracts/local_api/v1/schemas")


def _schema(model, *, schema_id: str) -> dict:
    payload = model.model_json_schema(mode="validation")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": schema_id,
        **payload,
    }


def schema_payloads() -> dict[str, dict]:
    return {
        "ocr_request.schema.json": _schema(
            OcrRequest, schema_id="https://ocr-prj.local/schema/v1/ocr-request.json"
        ),
        "ocr_result.schema.json": _schema(
            OcrResult, schema_id="https://ocr-prj.local/schema/v1/ocr-result.json"
        ),
    }


def export_json_schemas(output_dir: Path = DEFAULT_SCHEMA_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, payload in schema_payloads().items():
        target = output_dir / filename
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(target)
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Xuất JSON Schema v1 cho local OCR API")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_SCHEMA_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    written = export_json_schemas(args.output_dir)
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "files": [str(path) for path in written],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
