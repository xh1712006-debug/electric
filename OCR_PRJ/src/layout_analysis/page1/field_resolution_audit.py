"""Audit additive Page-1 field resolution against cached real OCR payloads."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from ..table_grid import detect_table_grid
from .extractor import extract_page1


def _text(field: Any) -> Any:
    if isinstance(field, Mapping):
        return field.get("text")
    if isinstance(field, list):
        return [item.get("text") if isinstance(item, Mapping) else item for item in field]
    return field


def compare_field_payloads(
    before_fields: Mapping[str, Any],
    after_fields: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify backward-compatible supplements separately from regressions."""

    before_names = tuple(before_fields)
    after_names = tuple(after_fields)
    changed_existing: dict[str, dict[str, Any]] = {}
    supplemental: dict[str, Any] = {}
    preserved = 0
    for field_name, before in before_fields.items():
        before_text = _text(before)
        after_text = _text(after_fields.get(field_name))
        if before_text is None and after_text is not None:
            supplemental[field_name] = after_text
        elif before_text is not None and before_text != after_text:
            changed_existing[field_name] = {"before": before_text, "after": after_text}
        elif before_text is not None:
            preserved += 1
    return {
        "field_names_compatible": before_names == after_names,
        "before_field_names": list(before_names),
        "after_field_names": list(after_names),
        "preserved_populated_fields": preserved,
        "supplemental_fields": supplemental,
        "changed_existing_fields": changed_existing,
        "compatible": before_names == after_names and not changed_existing,
    }


def audit_cached_pages(
    image_root: Path,
    cache_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    images = sorted(
        path for path in image_root.glob("*-page-001.png")
        if "(annotate)" not in path.stem.casefold()
    )
    if not images:
        raise ValueError(f"Không tìm thấy ảnh Page 1 chuẩn trong {image_root}")
    documents: list[dict[str, Any]] = []
    variants: Counter[str] = Counter()
    for image in images:
        document_id = re.sub(r"-page-\d+$", "", image.stem, flags=re.IGNORECASE)
        document_cache = cache_root / document_id
        layout_path = document_cache / "page1_layout.json"
        ocr_path = document_cache / "ocr_blocks.json"
        if not layout_path.is_file() or not ocr_path.is_file():
            raise ValueError(f"Thiếu cache thật cho {document_id}: {document_cache}")
        before = json.loads(layout_path.read_text(encoding="utf-8"))
        blocks = json.loads(ocr_path.read_text(encoding="utf-8"))
        joined_text = "\n".join(str(block.get("text", "")) for block in blocks)
        for label in (
            "Số:",
            "Mục đích ban hành phiếu",
            "Nguyên nhân thay đổi chỉnh định",
            "Phiên bản rơ-le",
        ):
            if label.casefold() in joined_text.casefold():
                variants[label] += 1
        after = extract_page1(
            {
                "document_id": document_id,
                "page_number": 1,
                "image_path": str(image),
                "block_predictions": blocks,
            },
            detect_table_grid(image),
        )
        comparison = compare_field_payloads(before.get("fields", {}), after["fields"])
        status_counts = Counter(
            str(item.get("status"))
            for item in after["field_resolution"].values()
            if isinstance(item, Mapping)
        )
        documents.append({
            "document_id": document_id,
            "image": str(image),
            **comparison,
            "field_resolution_count": len(after["field_resolution"]),
            "resolution_status_counts": dict(sorted(status_counts.items())),
            "warnings_before": before.get("warnings", []),
            "warnings_after": after.get("warnings", []),
        })
    incompatible = [item["document_id"] for item in documents if not item["compatible"]]
    supplemental_count = sum(len(item["supplemental_fields"]) for item in documents)
    report = {
        "schema_version": "1.0",
        "audit_type": "page1_cached_real_ocr_before_after",
        "image_root": str(image_root),
        "cache_root": str(cache_root),
        "documents_audited": len(documents),
        "compatible_documents": len(documents) - len(incompatible),
        "incompatible_documents": incompatible,
        "supplemental_field_count": supplemental_count,
        "confirmed_variant_documents": dict(sorted(variants.items())),
        "documents": documents,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit field resolution trên OCR Page 1 thật đã cache")
    parser.add_argument("--image-root", type=Path, default=Path("data/image/page1"))
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path("lab/structure_analysis_2/page1/output"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/page1_field_resolution/real_data_audit.json"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = audit_cached_pages(args.image_root, args.cache_root, args.output)
    print(json.dumps({
        "output": str(args.output),
        "documents_audited": report["documents_audited"],
        "compatible_documents": report["compatible_documents"],
        "supplemental_field_count": report["supplemental_field_count"],
    }, ensure_ascii=True))
    return 0 if not report["incompatible_documents"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
