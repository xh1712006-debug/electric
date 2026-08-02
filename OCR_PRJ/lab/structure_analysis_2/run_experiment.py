"""Chạy lab thứ hai từ predictions.json đã có của lab cũ."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .cell_ocr import CellOCRService, cells_requiring_reocr
from .layout_reconstruction import reconstruct_document
from .table_grid import detect_table_grid


ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT.parent / "structure_analysis" / "output" / "layoutlmv3_token_classification" / "predictions.json"
DEFAULT_OUTPUT = ROOT / "output"
CSV_FIELDS = [
    "document_id", "page_number", "layout_family", "group_id", "record_key",
    "parameter_code", "parameter_name", "value", "range", "unit",
    "description", "source_rows",
]


def _text(record: dict, field: str) -> str:
    value = record.get(field)
    return value.get("text", "") if value else ""


def _document_key(document_id: str) -> str:
    """Gom các trang của cùng phiếu về một tên file ổn định."""

    return re.sub(r"-page-\d+$", "", document_id, flags=re.IGNORECASE)


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", value).strip(" .")
    return cleaned or "document"


def _record_rows(pages: Iterable[dict]) -> Iterable[dict[str, str | int]]:
    for page in pages:
        for record in page["records"]:
            yield {
                "document_id": page["document_id"],
                "page_number": page["page_number"],
                "layout_family": page["layout"]["family"],
                "group_id": record.get("group_id") or "",
                "record_key": _text(record, "record_key"),
                "parameter_code": _text(record, "parameter_code"),
                "parameter_name": _text(record, "parameter_name"),
                "value": _text(record, "value"),
                "range": _text(record, "range"),
                "unit": _text(record, "unit"),
                "description": _text(record, "description"),
                "source_rows": "|".join(record["source_row_ids"]),
            }


def _write_csv(path: Path, rows: list[dict[str, str | int]]) -> Path:
    """Ghi CSV UTF-8 BOM; dùng tên có timestamp nếu file đang mở trong Excel."""

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = path.open("w", encoding="utf-8-sig", newline="")
    except PermissionError:
        fallback = path.with_name(f"{path.stem}_{datetime.now():%Y%m%d_%H%M%S}{path.suffix}")
        handle = fallback.open("w", encoding="utf-8-sig", newline="")
        print(f"{path.name} is locked; writing the new result to {fallback}")
        path = fallback
    with handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_csv_outputs(payload: dict, output: Path) -> tuple[Path, list[Path]]:
    """Xuất cả CSV tổng hợp và một CSV cho mỗi phiếu."""

    combined_rows = list(_record_rows(payload["pages"]))
    combined_path = _write_csv(output / "records.csv", combined_rows)
    grouped_pages: dict[str, list[dict]] = defaultdict(list)
    for page in payload["pages"]:
        grouped_pages[_document_key(str(page["document_id"]))].append(page)
    document_directory = output / "records_by_document"
    document_paths = [
        _write_csv(
            document_directory / f"{_safe_filename(document_key)}.csv",
            list(_record_rows(sorted(pages, key=lambda page: page["page_number"]))),
        )
        for document_key, pages in sorted(grouped_pages.items())
    ]
    return combined_path, document_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Tái tạo layout từ OCR cache của lab cũ")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cell-ocr", choices=("auto", "off"), default="auto", help="OCR lại ô có block cắt biên")
    parser.add_argument("--gpu", action="store_true", help="Dùng GPU cho detector/recognizer OCR ô")
    args = parser.parse_args()
    predictions = json.loads(args.source.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    grid_directory = args.output / "table_grids"
    grids = {
        page["document_id"]: detect_table_grid(page["image_path"], grid_directory / f"{page['document_id']}.png")
        for page in predictions.get("pages", [])
    }
    cell_ocr_by_page = {}
    plans_by_page = {
        page["document_id"]: cells_requiring_reocr(page, grids[page["document_id"]])
        for page in predictions.get("pages", [])
    }
    total_plans = sum(len(plans) for plans in plans_by_page.values())
    if args.cell_ocr == "auto" and total_plans:
        service = CellOCRService(use_gpu=args.gpu)
        for page in predictions.get("pages", []):
            plans = plans_by_page[page["document_id"]]
            if plans:
                cell_ocr_by_page[page["document_id"]] = service.run(page["image_path"], plans)
    payload = reconstruct_document(predictions, grids, cell_ocr_by_page)
    payload["cell_ocr"] = {
        "mode": args.cell_ocr,
        "planned_cells": total_plans,
        "recognised_cells": sum(len(values) for values in cell_ocr_by_page.values()),
    }
    (args.output / "cell_ocr_overrides.json").write_text(
        json.dumps(cell_ocr_by_page, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output / "reconstructed_layouts.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    per_page = args.output / "pages"
    per_page.mkdir(exist_ok=True)
    for page in payload["pages"]:
        (per_page / f"{page['document_id']}.json").write_text(json.dumps(page, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path, document_csv_paths = write_csv_outputs(payload, args.output)
    print(json.dumps({
        **payload["summary"], **payload["cell_ocr"], "csv": str(csv_path),
        "document_csv_directory": str(args.output / "records_by_document"),
        "document_csv_files": len(document_csv_paths),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
