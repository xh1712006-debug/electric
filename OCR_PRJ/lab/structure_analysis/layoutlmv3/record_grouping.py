"""Gom OCR block thành bản ghi dễ đọc bằng quan hệ hình học tổng quát.

Mô-đun này không dùng nhãn FUNSD làm sự thật ngữ nghĩa. Các nhãn model chỉ
được lưu làm bằng chứng phụ vì checkpoint hiện tại chưa được fine-tune cho
phiếu relay.
"""

from __future__ import annotations

import re
from statistics import median
from typing import Any


CODE_PREFIX = re.compile(
    r"^(?P<code>(?:[A-Za-z]{0,4}[- ]?)?\d{3,4}(?:\.\d{1,4})?[A-Za-z]?)\b\s*(?P<rest>.*)$"
)


def _overlap_1d(first_start: float, first_end: float, second_start: float, second_end: float) -> float:
    intersection = max(0.0, min(first_end, second_end) - max(first_start, second_start))
    denominator = max(1.0, min(first_end - first_start, second_end - second_start))
    return intersection / denominator


def _block_rows(blocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
    """Nhóm block OCR thành dòng theo chồng lấn theo trục dọc."""

    if not blocks:
        return [], 1.0
    median_height = median(max(1.0, row["bbox_pixel"][3] - row["bbox_pixel"][1]) for row in blocks)
    rows: list[dict[str, Any]] = []
    for block in sorted(blocks, key=lambda row: ((row["bbox_pixel"][1] + row["bbox_pixel"][3]) / 2, row["bbox_pixel"][0])):
        x1, y1, x2, y2 = block["bbox_pixel"]
        center_y = (y1 + y2) / 2
        candidate: dict[str, Any] | None = None
        candidate_distance = float("inf")
        for row in rows:
            overlap = _overlap_1d(y1, y2, row["bbox"][1], row["bbox"][3])
            distance = abs(center_y - row["center_y"])
            if (overlap >= 0.35 or distance <= median_height * 0.65) and distance < candidate_distance:
                candidate, candidate_distance = row, distance
        if candidate is None:
            candidate = {"row_id": "", "blocks": [], "bbox": [x1, y1, x2, y2], "center_y": center_y}
            rows.append(candidate)
        candidate["blocks"].append(block)
        candidate["bbox"] = [
            min(candidate["bbox"][0], x1), min(candidate["bbox"][1], y1),
            max(candidate["bbox"][2], x2), max(candidate["bbox"][3], y2),
        ]
        candidate["center_y"] = (candidate["bbox"][1] + candidate["bbox"][3]) / 2
    rows.sort(key=lambda row: row["center_y"])
    for index, row in enumerate(rows):
        row["row_id"] = f"row_{index:04d}"
        row["blocks"].sort(key=lambda block: block["bbox_pixel"][0])
    return rows, median_height


def _code_from_first_block(block: dict[str, Any]) -> tuple[str | None, str]:
    match = CODE_PREFIX.match(block["text"].strip())
    if not match:
        return None, ""
    return match.group("code"), match.group("rest").strip()


def _anchors(rows: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    """Tìm cột mã và cột giá trị từ các dòng có mã, không dùng tọa độ cố định."""

    code_positions: list[float] = []
    value_positions: list[float] = []
    for row in rows:
        blocks = row["blocks"]
        if not blocks:
            continue
        code, _ = _code_from_first_block(blocks[0])
        if code is None:
            continue
        code_positions.append(blocks[0]["bbox_pixel"][0])
        if len(blocks) >= 2:
            value_positions.append(blocks[-1]["bbox_pixel"][0])
    return (
        median(code_positions) if code_positions else None,
        median(value_positions) if value_positions else None,
    )


def _field(blocks: list[dict[str, Any]], text: str) -> dict[str, Any] | None:
    if not blocks and not text:
        return None
    bbox = [
        min(block["bbox_pixel"][0] for block in blocks),
        min(block["bbox_pixel"][1] for block in blocks),
        max(block["bbox_pixel"][2] for block in blocks),
        max(block["bbox_pixel"][3] for block in blocks),
    ] if blocks else None
    return {
        "text": text,
        "source_block_ids": [block["block_id"] for block in blocks],
        "bbox_pixel": bbox,
        "model_labels": sorted({block.get("model_label", "unknown") for block in blocks}),
    }


def _record_confidence(code: dict[str, Any] | None, name: dict[str, Any] | None, values: list[dict[str, Any]], geometric_value_alignment: bool) -> tuple[float, list[str]]:
    evidence: list[str] = []
    score = 0.2
    if code:
        score += 0.26
        evidence.append("mã có dạng tổng quát ở đầu dòng")
    if name:
        score += 0.22
        evidence.append("tên nằm sau mã trong cùng dòng")
    if values:
        score += 0.22
        evidence.append("có vùng giá trị")
    if geometric_value_alignment:
        score += 0.12
        evidence.append("giá trị thẳng cột với các dòng khác")
    # Đây là độ mạnh của bằng chứng hình học, không phải xác suất đúng khi chưa
    # có ground truth; không biểu diễn quá tự tin.
    return round(min(0.85, score), 3), evidence


def reconstruct_readable_page(page: dict[str, Any]) -> dict[str, Any]:
    """Tạo JSON bản ghi dễ đọc; tất cả quan hệ là giả thuyết hình học."""

    blocks = [
        {
            "block_id": row["block_id"],
            "text": " ".join(str(row.get("text", "")).split()),
            "bbox_pixel": [float(value) for value in row["bbox_pixel"]],
            "model_label": row.get("model_label"),
        }
        for row in page.get("block_predictions", [])
        if str(row.get("text", "")).strip()
    ]
    rows, median_height = _block_rows(blocks)
    code_anchor, value_anchor = _anchors(rows)
    code_tolerance = max(35.0, median_height * 2.5)
    value_tolerance = max(45.0, median_height * 3.0)

    sections: list[dict[str, Any]] = []
    loose_records: list[dict[str, Any]] = []
    unassigned: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None
    previous_record: dict[str, Any] | None = None
    previous_row_bottom: float | None = None
    used_block_ids: set[str] = set()

    def add_record(record: dict[str, Any]) -> None:
        nonlocal previous_record
        if current_section is None:
            loose_records.append(record)
        else:
            current_section["records"].append(record)
        previous_record = record

    for index, row in enumerate(rows):
        row_blocks = row["blocks"]
        first = row_blocks[0]
        code_text, embedded_name = _code_from_first_block(first)
        is_code_column = code_text is not None and (
            code_anchor is None or abs(first["bbox_pixel"][0] - code_anchor) <= code_tolerance
        )
        same_row_value_blocks = [
            block for block in row_blocks[1:]
            if value_anchor is not None and block["bbox_pixel"][0] >= value_anchor - value_tolerance
        ]

        if is_code_column:
            code_blocks = [first]
            after_code = row_blocks[1:]
            name_blocks = [block for block in after_code if block not in same_row_value_blocks]
            value_blocks = same_row_value_blocks
            name_parts = [embedded_name] if embedded_name else []
            name_parts.extend(block["text"] for block in name_blocks)
            code = _field(code_blocks, code_text)
            name = _field(name_blocks or code_blocks if embedded_name else name_blocks, " ".join(part for part in name_parts if part))
            values = []
            if value_blocks:
                values.append(_field(value_blocks, " ".join(block["text"] for block in value_blocks)))
            confidence, evidence = _record_confidence(code, name, values, bool(value_blocks))
            record = {
                "record_id": f"record_{len(loose_records) + sum(len(section['records']) for section in sections) + 1:04d}",
                "source_row_ids": [row["row_id"]],
                "code": code,
                "name": name,
                "values": values,
                "grouping_confidence": confidence,
                "grouping_evidence": evidence,
                "relationship_status": "geometric_candidate_not_ground_truth",
            }
            used_block_ids.update(block["block_id"] for block in row_blocks)
            add_record(record)
        else:
            near_value_column = bool(
                value_anchor is not None and first["bbox_pixel"][0] >= value_anchor - value_tolerance
            )
            small_gap = previous_row_bottom is not None and row["bbox"][1] - previous_row_bottom <= median_height * 2.8
            if previous_record and near_value_column and small_gap:
                continuation = _field(row_blocks, " ".join(block["text"] for block in row_blocks))
                assert continuation is not None
                previous_record["values"].append(continuation)
                previous_record["source_row_ids"].append(row["row_id"])
                previous_record["grouping_evidence"].append("dòng tiếp theo căn theo cột giá trị")
                previous_record["grouping_confidence"] = round(min(0.89, previous_record["grouping_confidence"] + 0.04), 3)
                used_block_ids.update(block["block_id"] for block in row_blocks)
            else:
                next_row = rows[index + 1] if index + 1 < len(rows) else None
                next_has_code = bool(next_row and _code_from_first_block(next_row["blocks"][0])[0])
                row_width = row["bbox"][2] - row["bbox"][0]
                heading_candidate = next_has_code and row_width >= median_height * 5
                if heading_candidate:
                    current_section = {
                        "section_id": f"section_{len(sections) + 1:03d}",
                        "title": _field(row_blocks, " ".join(block["text"] for block in row_blocks)),
                        "records": [],
                        "status": "geometric_candidate_not_ground_truth",
                    }
                    sections.append(current_section)
                    previous_record = None
                    used_block_ids.update(block["block_id"] for block in row_blocks)
                else:
                    unassigned.append({
                        "source_row_id": row["row_id"],
                        "text": " ".join(block["text"] for block in row_blocks),
                        "source_block_ids": [block["block_id"] for block in row_blocks],
                        "reason": "không đủ bằng chứng hình học để gán vào section hoặc record",
                    })
                    previous_record = None
        previous_row_bottom = row["bbox"][3]

    # Các block không xuất hiện trong record/section/unassigned vẫn được liệt kê.
    known_ids = used_block_ids | {block_id for row in unassigned for block_id in row["source_block_ids"]}
    for block in blocks:
        if block["block_id"] not in known_ids:
            unassigned.append({
                "source_row_id": None,
                "text": block["text"],
                "source_block_ids": [block["block_id"]],
                "reason": "block chưa được gom",
            })

    record_count = len(loose_records) + sum(len(section["records"]) for section in sections)
    return {
        "document_id": page["document_id"],
        "page_number": page["page_number"],
        "source_image": page["image_path"],
        "method": {
            "name": "generic_geometry_record_grouping",
            "code_column_anchor_x": round(code_anchor, 2) if code_anchor is not None else None,
            "value_column_anchor_x": round(value_anchor, 2) if value_anchor is not None else None,
            "median_block_height_px": round(median_height, 2),
            "model_label_usage": "chỉ lưu làm bằng chứng; không dùng làm nhãn relay chuẩn",
        },
        "warning": "Quan hệ code/name/value là giả thuyết từ hình học OCR, cần xác nhận bởi người dùng hoặc ground truth.",
        "sections": sections,
        "records_without_section": loose_records,
        "unassigned_rows": unassigned,
        "summary": {
            "ocr_blocks": len(blocks),
            "rows": len(rows),
            "candidate_sections": len(sections),
            "candidate_records": record_count,
            "unassigned_rows": len(unassigned),
        },
    }
