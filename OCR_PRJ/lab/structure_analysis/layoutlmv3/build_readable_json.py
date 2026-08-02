"""Tạo JSON bản ghi dễ đọc từ output LayoutLMv3 hiện có, không chạy lại OCR."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from .record_grouping import reconstruct_readable_page


OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "output" / "layoutlmv3_token_classification"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    predictions_path = OUTPUT_ROOT / "predictions.json"
    if not predictions_path.is_file():
        raise SystemExit(f"Không tìm thấy {predictions_path}")
    predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
    pages = [reconstruct_readable_page(page) for page in predictions.get("pages", [])]
    per_page_directory = OUTPUT_ROOT / "readable_pages"
    per_page_directory.mkdir(parents=True, exist_ok=True)
    for page in pages:
        page_path = per_page_directory / f"{page['document_id']}.json"
        page_path.write_text(json.dumps(page, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = {
        "schema_version": "1.0",
        "source": str(predictions_path),
        "method": "generic_geometry_record_grouping",
        "warning": (
            "Đây là JSON dễ đọc để review. Quan hệ record được suy luận bằng hình học OCR, "
            "không phải ground truth và không dùng nhãn FUNSD làm schema relay."
        ),
        "pages": pages,
        "summary": {
            "pages": len(pages),
            "candidate_records": sum(page["summary"]["candidate_records"] for page in pages),
            "candidate_sections": sum(page["summary"]["candidate_sections"] for page in pages),
            "unassigned_rows": sum(page["summary"]["unassigned_rows"] for page in pages),
        },
        "per_page_directory": str(per_page_directory),
    }
    destination = OUTPUT_ROOT / "readable_records.json"
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Đã ghi {destination}: {payload['summary']['candidate_records']} bản ghi ứng viên")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
