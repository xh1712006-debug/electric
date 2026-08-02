"""Xuất CSV UTF-8 BOM để mở và review dễ dàng bằng Excel."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
from typing import Iterable

from .csv_export import RECORD_COLUMNS, UNASSIGNED_COLUMNS, record_rows, unassigned_rows


OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "output" / "layoutlmv3_token_classification"


def write_csv(path: Path, fieldnames: Iterable[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    source = OUTPUT_ROOT / "readable_records.json"
    if not source.is_file():
        raise SystemExit(
            "Chưa có readable_records.json. Hãy chạy build_readable_json trước."
        )
    payload = json.loads(source.read_text(encoding="utf-8"))
    all_records: list[dict[str, str]] = []
    all_unassigned: list[dict[str, str]] = []
    page_directory = OUTPUT_ROOT / "readable_csv_pages"
    for page in payload.get("pages", []):
        records = record_rows(page)
        unassigned = unassigned_rows(page)
        all_records.extend(records)
        all_unassigned.extend(unassigned)
        write_csv(page_directory / f"{page['document_id']}.csv", RECORD_COLUMNS, records)
    write_csv(OUTPUT_ROOT / "readable_records.csv", RECORD_COLUMNS, all_records)
    write_csv(OUTPUT_ROOT / "unassigned_rows.csv", UNASSIGNED_COLUMNS, all_unassigned)
    print(f"Đã ghi {len(all_records)} bản ghi vào {OUTPUT_ROOT / 'readable_records.csv'}")
    print(f"Đã ghi {len(all_unassigned)} dòng chưa gom vào {OUTPUT_ROOT / 'unassigned_rows.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
