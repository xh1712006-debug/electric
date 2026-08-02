"""Chuyển bản ghi ứng viên dễ đọc thành dòng CSV để đối chiếu với trang gốc."""

from __future__ import annotations

from typing import Any


RECORD_COLUMNS = (
    "Tài liệu",
    "Trang",
    "Nhóm",
    "Mã bản ghi",
    "Mã tham số",
    "Tên tham số",
    "Giá trị",
    "Số giá trị",
    "Độ tin cậy hình học",
    "Trạng thái quan hệ",
    "Dòng OCR nguồn",
    "Block mã",
    "Block tên",
    "Block giá trị",
    "Bằng chứng gom",
)

UNASSIGNED_COLUMNS = (
    "Tài liệu",
    "Trang",
    "Dòng OCR nguồn",
    "Nội dung OCR chưa gom",
    "Block OCR",
    "Lý do",
)


def _text(field: dict[str, Any] | None) -> str:
    return str(field.get("text", "")) if field else ""


def _blocks(field: dict[str, Any] | None) -> str:
    return " | ".join(field.get("source_block_ids", [])) if field else ""


def record_rows(page: dict[str, Any]) -> list[dict[str, str]]:
    """Một dòng CSV cho mỗi bản ghi; nhiều giá trị được ngăn bằng ` | `."""

    rows: list[dict[str, str]] = []
    groups: list[tuple[str, list[dict[str, Any]]]] = [
        (section["title"]["text"], section["records"])
        for section in page.get("sections", [])
    ]
    groups.append(("", page.get("records_without_section", [])))
    for section_title, records in groups:
        for record in records:
            values = [value for value in record.get("values", []) if value]
            rows.append(
                {
                    "Tài liệu": str(page["document_id"]),
                    "Trang": str(page["page_number"]),
                    "Nhóm": section_title,
                    "Mã bản ghi": str(record["record_id"]),
                    "Mã tham số": _text(record.get("code")),
                    "Tên tham số": _text(record.get("name")),
                    "Giá trị": " | ".join(_text(value) for value in values),
                    "Số giá trị": str(len(values)),
                    "Độ tin cậy hình học": str(record.get("grouping_confidence", "")),
                    "Trạng thái quan hệ": str(record.get("relationship_status", "")),
                    "Dòng OCR nguồn": " | ".join(record.get("source_row_ids", [])),
                    "Block mã": _blocks(record.get("code")),
                    "Block tên": _blocks(record.get("name")),
                    "Block giá trị": " | ".join(
                        block_id for value in values for block_id in value.get("source_block_ids", [])
                    ),
                    "Bằng chứng gom": " | ".join(record.get("grouping_evidence", [])),
                }
            )
    return rows


def unassigned_rows(page: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "Tài liệu": str(page["document_id"]),
            "Trang": str(page["page_number"]),
            "Dòng OCR nguồn": str(row.get("source_row_id") or ""),
            "Nội dung OCR chưa gom": str(row.get("text", "")),
            "Block OCR": " | ".join(row.get("source_block_ids", [])),
            "Lý do": str(row.get("reason", "")),
        }
        for row in page.get("unassigned_rows", [])
    ]
