"""Tái tạo hàng, cột, nhóm và bản ghi từ block OCR.

Không dùng vị trí pixel cố định hay tên mẫu phiếu. Mọi cột được suy ra lại từ
block OCR của chính trang đang xử lý. Nhãn model của lab cũ không được dùng làm
sự thật ngữ nghĩa vì checkpoint thử nghiệm chưa fine-tune cho phiếu rơ-le.
"""

from __future__ import annotations

import re
from collections import Counter
from statistics import median
from typing import Any

from ..pagination import detect_page_reference


HEADER_HINTS = {
    "group/attributes": "parameter_name",
    "group / attributes": "parameter_name",
    "range": "range",
    "unit": "unit",
    "description": "description",
    "explanation": "description",
    "setting": "value",
    "value": "value",
    "value set": "value",
    "parameter": "parameter_name",
    "parameters": "parameter_name",
    "item": "parameter_name",
    "menu text": "parameter_name",
    "attribute": "parameter_name",
    "attributes": "parameter_name",
    "index": "record_key",
    "no": "record_key",
}

# Các dạng nhận diện tổng quát: số thập phân, số chứa ký tự hexa, hoặc định danh
# kỹ thuật có số/gạch dưới. Chúng chỉ là bằng chứng, không bắt buộc cho một record.
PARAMETER_CODE = re.compile(r"^(?:[A-Za-z]{0,4}\d{1,4}|\d{2,4})(?:\.[0-9A-Za-z]{1,4})+(?:[A-Za-z])?$")
TECHNICAL_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_/-]{2,}$")
INTEGER_KEY = re.compile(r"^\d{1,4}$")
PLAIN_PARAMETER_CODE = re.compile(r"^\d{3,4}[A-Za-z]?$", re.IGNORECASE)
DOCUMENT_METADATA = re.compile(r"công ty|trung tâm điều độ|số phiếu|phiếu chỉnh định", re.IGNORECASE)


def _bbox(block: dict[str, Any]) -> list[float]:
    return [float(value) for value in block["bbox_pixel"]]


def _text(block: dict[str, Any]) -> str:
    return " ".join(str(block.get("text", "")).split())


def _overlap(first: tuple[float, float], second: tuple[float, float]) -> float:
    intersect = max(0.0, min(first[1], second[1]) - max(first[0], second[0]))
    shortest = max(1.0, min(first[1] - first[0], second[1] - second[0]))
    return intersect / shortest


def build_rows(blocks: list[dict[str, Any]], column_centres: list[float] | None = None) -> tuple[list[dict[str, Any]], float]:
    """Gom dòng không lưới bằng baseline và đồng thuận đa cột.

    Bounding box cao ở một cột không được phép kéo hai baseline của các cột
    khác vào cùng dòng. Đây là fallback cho bố cục không có đường kẻ.
    """

    if not blocks:
        return [], 1.0
    heights = [max(1.0, _bbox(block)[3] - _bbox(block)[1]) for block in blocks]
    typical_height = median(heights)
    rows: list[dict[str, Any]] = []
    for block in sorted(blocks, key=lambda item: ((_bbox(item)[1] + _bbox(item)[3]) / 2, _bbox(item)[0])):
        x1, y1, x2, y2 = _bbox(block)
        centre = (y1 + y2) / 2
        column = _nearest_column((x1 + x2) / 2, column_centres) if column_centres else None
        candidates = []
        for row in rows:
            distance = abs(centre - row["centre_y"])
            if distance > typical_height * 0.48:
                continue
            same_column_centres = row.get("column_centres", {}).get(column, []) if column is not None else []
            if same_column_centres and min(abs(centre - value) for value in same_column_centres) > typical_height * 0.25:
                continue
            candidates.append(row)
        row = min(candidates, key=lambda item: abs(centre - item["centre_y"])) if candidates else None
        if row is None:
            row = {"blocks": [], "bbox": [x1, y1, x2, y2], "centre_y": centre, "column_centres": {}}
            rows.append(row)
        row["blocks"].append(block)
        if column is not None:
            row["column_centres"].setdefault(column, []).append(centre)
        row["bbox"] = [min(row["bbox"][0], x1), min(row["bbox"][1], y1), max(row["bbox"][2], x2), max(row["bbox"][3], y2)]
        row["centre_y"] = (row["bbox"][1] + row["bbox"][3]) / 2
    rows.sort(key=lambda item: item["centre_y"])
    for index, row in enumerate(rows):
        row["row_id"] = f"row_{index:04d}"
        row["blocks"].sort(key=lambda item: _bbox(item)[0])
    return rows, typical_height


def build_grid_rows(blocks: list[dict[str, Any]], region: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    """Tạo đúng một logical row cho mỗi dải giữa hai đường ngang."""

    x1, y1, x2, y2 = [float(value) for value in region["bbox"]]
    relevant = [
        block for block in blocks
        if x1 <= (_bbox(block)[0] + _bbox(block)[2]) / 2 <= x2
        and _overlap((_bbox(block)[1], _bbox(block)[3]), (y1, y2)) > 0
    ]
    rows: list[dict[str, Any]] = []
    assigned: set[str] = set()
    vertical_boundaries = [float(value) for value in region["vertical_lines"]]
    horizontal_boundaries = [float(value) for value in region["horizontal_lines"]]
    for row_index, (top, bottom) in enumerate(region["row_bands"]):
        members: list[dict[str, Any]] = []
        crossing: list[str] = []
        for block in relevant:
            bx1, by1, bx2, by2 = _bbox(block)
            overlaps = [
                max(0.0, min(by2, band_bottom) - max(by1, band_top))
                for band_top, band_bottom in region["row_bands"]
            ]
            if not overlaps or row_index != max(range(len(overlaps)), key=overlaps.__getitem__) or overlaps[row_index] <= 0:
                continue
            members.append(block)
            assigned.add(str(block["block_id"]))
            crosses_vertical = any(bx1 + 2 < boundary < bx2 - 2 for boundary in vertical_boundaries[1:-1])
            crosses_horizontal = any(by1 + 2 < boundary < by2 - 2 for boundary in horizontal_boundaries[1:-1])
            if crosses_vertical or crosses_horizontal:
                crossing.append(str(block["block_id"]))
        if not members:
            continue
        rows.append({
            "blocks": sorted(members, key=lambda item: _bbox(item)[0]),
            "bbox": [x1, float(top), x2, float(bottom)],
            "centre_y": (float(top) + float(bottom)) / 2,
            "grid_region_id": region["region_id"],
            "grid_row_index": row_index,
            "column_centres_override": [float(value) for value in region["column_centres"]],
            "column_boundaries": vertical_boundaries,
            "crossing_block_ids": crossing,
        })
    return rows, assigned


def infer_column_centres(rows: list[dict[str, Any]], typical_height: float, page_width: float) -> list[float]:
    """Ước lượng cột bằng các vị trí bắt đầu lặp lại; không dùng tọa độ tuyệt đối."""

    starts = sorted(_bbox(block)[0] for row in rows for block in row["blocks"])
    if not starts:
        return []
    gap = max(page_width * 0.045, typical_height * 3.0)
    clusters: list[list[float]] = [[starts[0]]]
    for value in starts[1:]:
        if value - median(clusters[-1]) <= gap:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    # Cột thực phải xuất hiện lặp lại; các cụm hiếm là block lệch/dòng quấn.
    minimum = max(2, round(len(rows) * 0.05))
    centres = [median(cluster) for cluster in clusters if len(cluster) >= minimum]
    return centres[:5]


def _nearest_column(x: float, centres: list[float]) -> int:
    return min(range(len(centres)), key=lambda index: abs(x - centres[index]))


def _roles_from_header(rows: list[dict[str, Any]], centres: list[float]) -> list[str]:
    default = {
        1: ["parameter_name"],
        2: ["parameter_name", "value"],
        3: ["parameter_code", "parameter_name", "value"],
        4: ["record_key", "parameter_name", "description", "value"],
    }.get(len(centres))
    if default is None:
        default = ["record_key", "parameter_name", "description", "value"] + ["extra"] * max(0, len(centres) - 4)
    for row in rows[:8]:
        # Header thường ngắn; không để từ "no" trong "nominal" hay "value"
        # trong nội dung dữ liệu dài đánh lừa việc đặt vai trò cột.
        if any(len(_text(block)) > 35 for block in row["blocks"]):
            continue
        found: dict[int, str] = {}
        # Khi có grid, block header có thể bắt đầu sát biên trái của cell rộng
        # (Description của GRL200 là ví dụ). Dùng cùng phép gán theo biên cell
        # như dữ liệu thay vì chọn centre gần nhất từ điểm bắt đầu text.
        cells, _ = _row_cells(row, centres)
        for column, cell in enumerate(cells):
            lowered = cell.lower()
            if not lowered:
                continue
            for hint, role in HEADER_HINTS.items():
                matches = hint == lowered if len(hint) <= 3 else hint == lowered or hint in lowered
                if matches:
                    found[column] = role
                    break
        # Header chỉ được ghi đè schema mặc định khi ánh xạ đủ tất cả cột và
        # không lặp vai trò. OCR như "Index Item" có thể gộp hai header vào
        # một block; dùng nó để suy diễn từng cột sẽ làm lệch cả bảng.
        if len(found) == len(centres) and len(set(found.values())) == len(centres):
            return [found.get(index, default[index]) for index in range(len(centres))]

    # Một số layout không có lưới/header (như 7SJ) tạo thành bốn cụm x vì
    # value ngắn và value dài được canh ở hai vị trí khác nhau. Chúng không
    # phải là Description và Value: mỗi dòng record chỉ dùng một trong hai
    # vị trí cuối. Khi tín hiệu này lặp lại đủ nhiều, gộp cả hai cột vật lý về
    # cùng field value thay vì áp prior Description/Value.
    if len(centres) == 4:
        record_cells = []
        for row in rows:
            cells, _ = _row_cells(row, centres)
            if cells and (INTEGER_KEY.fullmatch(cells[0]) or _is_code(cells[0])):
                record_cells.append(cells)
        mutually_exclusive_values = [
            cells for cells in record_cells
            if bool(cells[2]) != bool(cells[3])
        ]
        if len(record_cells) >= 3 and len(mutually_exclusive_values) / len(record_cells) >= 0.8:
            return ["record_key", "parameter_name", "value", "value"]
    # Một số ảnh mất hàng header sau OCR. Khi cột giữa lặp lại biểu thức dải
    # giá trị, đây là bằng chứng tổng quát hơn vị trí cho kiểu Parameter/Range/Value.
    if len(centres) == 3:
        data_rows = [_row_cells(row, centres)[0] for row in rows]
        middle = [cells[1].lower() for cells in data_rows if len(cells) > 1 and cells[1]]
        range_like = sum(" to " in value or "step" in value or "range" in value for value in middle)
        if middle and range_like / len(middle) >= 0.25:
            return ["parameter_name", "range", "value"]
    return default


def _is_code(text: str) -> bool:
    compact = text.replace(" ", "")
    return bool(PARAMETER_CODE.fullmatch(compact) or PLAIN_PARAMETER_CODE.fullmatch(compact))


def _is_document_metadata(row: dict[str, Any], pagination_block_ids: set[str] | None = None) -> bool:
    """Loại header phiếu bằng nội dung metadata chung, không theo tọa độ mẫu."""

    block_ids = {str(block["block_id"]) for block in row["blocks"]}
    return bool(
        DOCUMENT_METADATA.search(" ".join(_text(block) for block in row["blocks"]))
        or block_ids.intersection(pagination_block_ids or set())
    )


def _is_heading(cells: list[str], roles: list[str]) -> bool:
    non_empty = [(index, value) for index, value in enumerate(cells) if value]
    if not non_empty:
        return False
    text = " ".join(value for _, value in non_empty)
    if any(hint in text.lower() for hint in HEADER_HINTS) and len(non_empty) >= 2:
        return False
    if len(non_empty) == 1 and not _is_code(text) and not INTEGER_KEY.fullmatch(text):
        return True
    # Dòng trải nhiều cột nhưng không có value rõ là tiêu đề nhóm thường gặp.
    return len(non_empty) == 1 and roles[non_empty[0][0]] not in {"value", "range", "unit"}


def _is_table_header(cells: list[str], roles: list[str]) -> bool:
    """Nhận diện một hàng header đã đủ bằng chứng role để không xuất thành record."""

    found_roles: list[str] = []
    for index, text in enumerate(cells):
        if not text or index >= len(roles):
            continue
        lowered = text.lower()
        for hint, role in HEADER_HINTS.items():
            matches = hint == lowered if len(hint) <= 3 else hint == lowered or hint in lowered
            if matches and roles[index] == role:
                found_roles.append(role)
                break
    return len(found_roles) >= 2 and len(found_roles) == len(set(found_roles))


def _field(text: str, blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not text:
        return None
    return {"text": text, "source_block_ids": [str(block["block_id"]) for block in blocks]}


def _row_cells(
    row: dict[str, Any],
    centres: list[float],
    cell_ocr: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[str], list[list[dict[str, Any]]]]:
    members: list[list[dict[str, Any]]] = [[] for _ in centres]
    for block in row["blocks"]:
        x1, _, x2, _ = _bbox(block)
        boundaries = row.get("column_boundaries")
        if boundaries and len(boundaries) == len(centres) + 1:
            overlaps = [max(0.0, min(x2, right) - max(x1, left)) for left, right in zip(boundaries, boundaries[1:])]
            column_index = max(range(len(overlaps)), key=overlaps.__getitem__)
        else:
            column_index = _nearest_column((x1 + x2) / 2, centres)
        members[column_index].append(block)
    cells = [" ".join(_text(block) for block in column) for column in members]
    if cell_ocr and row.get("grid_region_id") is not None:
        for index in range(len(cells)):
            key = f"{row['grid_region_id']}:{row['grid_row_index']}:{index}"
            override = cell_ocr.get(key)
            if override and str(override.get("text", "")).strip():
                cells[index] = " ".join(str(override["text"]).split())
    return cells, members


def reconstruct_page(
    page: dict[str, Any],
    table_grid: dict[str, Any] | None = None,
    cell_ocr: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Tạo bảng logic và record candidates cho một trang OCR đã lưu."""

    blocks = [
        {"block_id": block["block_id"], "text": _text(block), "bbox_pixel": _bbox(block)}
        for block in page.get("block_predictions", []) if _text(block)
    ]
    pagination = detect_page_reference(blocks, expected_page_number=int(page["page_number"]))
    pagination_block_ids = {
        str(block["block_id"]) for block in (pagination or {}).get("source_blocks", [])
    }
    typical_height = median([max(1.0, _bbox(block)[3] - _bbox(block)[1]) for block in blocks]) if blocks else 1.0
    grid_rows: list[dict[str, Any]] = []
    assigned_to_grid: set[str] = set()
    regions = (table_grid or {}).get("regions", [])
    for region in regions:
        region_rows, assigned = build_grid_rows(blocks, region)
        grid_rows.extend(region_rows)
        assigned_to_grid.update(assigned)

    fallback_blocks = [block for block in blocks if str(block["block_id"]) not in assigned_to_grid]
    preliminary_rows, _ = build_rows(fallback_blocks)
    page_width = max((_bbox(block)[2] for block in blocks), default=1.0)
    fallback_centres = infer_column_centres(preliminary_rows, typical_height, page_width)
    if len(fallback_centres) < 2 and fallback_blocks:
        fallback_centres = sorted({round(_bbox(block)[0], 1) for block in fallback_blocks})[:2]
    fallback_rows, _ = build_rows(fallback_blocks, fallback_centres)
    for row in fallback_rows:
        row["column_centres_override"] = fallback_centres
        row["crossing_block_ids"] = []

    rows = sorted([*grid_rows, *fallback_rows], key=lambda item: (item["centre_y"], item["bbox"][0]))
    for index, row in enumerate(rows):
        row["row_id"] = f"row_{index:04d}"

    region_roles: dict[str, list[str]] = {}
    for region in regions:
        region_rows = [row for row in grid_rows if row["grid_region_id"] == region["region_id"]]
        centres = [float(value) for value in region["column_centres"]]
        region_roles[region["region_id"]] = _roles_from_header(region_rows, centres)
    fallback_content = [row for row in fallback_rows if not _is_document_metadata(row, pagination_block_ids)]
    fallback_roles = _roles_from_header(fallback_content, fallback_centres) if fallback_centres else []
    group_stack: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    structured_rows: list[dict[str, Any]] = []
    previous_record: dict[str, Any] | None = None
    previous_bottom: float | None = None

    for row in rows:
        centres = row.get("column_centres_override", fallback_centres)
        roles = region_roles.get(row.get("grid_region_id"), fallback_roles)
        cells, members = _row_cells(row, centres, cell_ocr)
        if _is_document_metadata(row, pagination_block_ids):
            structured_rows.append({"row_id": row["row_id"], "cells": cells, "row_type": "document_metadata", "source_block_ids": [block["block_id"] for block in row["blocks"]], "grid_region_id": row.get("grid_region_id")})
            previous_record = None
            previous_bottom = row["bbox"][3]
            continue
        table_header = _is_table_header(cells, roles)
        heading = _is_heading(cells, roles)
        row_text = " ".join(cell for cell in cells if cell)
        gap = row["bbox"][1] - previous_bottom if previous_bottom is not None else None
        non_empty = [index for index, value in enumerate(cells) if value]
        is_grid_row = row.get("grid_region_id") is not None
        has_new_identifier = any(
            cells[index] and roles[index] in {"record_key", "parameter_code"}
            for index in non_empty
        ) or bool(cells and (_is_code(cells[0]) or INTEGER_KEY.fullmatch(cells[0])))
        has_complete_record = any(
            cells[index] and roles[index] == "value" for index in non_empty
        ) and any(
            cells[index] and roles[index] in {"parameter_name", "parameter_code", "description"}
            for index in non_empty
        )
        continuation = bool(
            previous_record and non_empty and not is_grid_row
            and gap is not None and gap <= typical_height * 1.8
            and not has_new_identifier and not has_complete_record
            # Dòng quấn phải thụt vào một cột dữ liệu đã có. Một dòng bắt đầu
            # từ cột đầu nhiều khả năng là tiêu đề nhóm mới.
            and non_empty[0] > 0
        )
        row_type = "unassigned"
        if table_header:
            previous_record = None
            row_type = "table_header"
        elif continuation:
            for index in non_empty:
                role = roles[index]
                target = previous_record.get(role)
                value = _field(cells[index], members[index])
                if value is None:
                    continue
                if target is None:
                    previous_record[role] = value
                else:
                    target["text"] = f"{target['text']} {value['text']}"
                    target["source_block_ids"].extend(value["source_block_ids"])
            previous_record["source_row_ids"].append(row["row_id"])
            previous_record["evidence"].append("dòng quấn không có mã mới và không tạo đủ các cột của record mới")
            row_type = "continuation"
        elif heading:
            group = {"group_id": f"group_{len(group_stack) + 1:03d}", "title": row_text, "source_row_ids": [row["row_id"]]}
            group_stack.append(group)
            previous_record = None
            row_type = "group"
        elif any(cells):
            values = {role: _field(cells[index], members[index]) for index, role in enumerate(roles) if cells[index]}
            # Cột đầu mã/khóa có thể không được nhận biết từ header, nhưng hình dạng mã là tín hiệu bổ sung.
            first_value = cells[0] if cells else ""
            if values.get("parameter_code") is None and _is_code(first_value):
                values["parameter_code"] = _field(first_value, members[0])
                if "parameter_name" not in values and len(cells) > 1:
                    values["parameter_name"] = _field(cells[1], members[1])
            if values.get("record_key") is None and INTEGER_KEY.fullmatch(first_value):
                values["record_key"] = _field(first_value, members[0])
            evidence = [
                "hàng được xác định bởi hai đường ngang của cùng vùng bảng" if is_grid_row else "baseline được nhiều cột OCR cùng ủng hộ",
                "các cell cùng logical row được liên kết thành record",
            ]
            record = {
                "record_id": f"record_{len(records) + 1:04d}",
                "group_id": group_stack[-1]["group_id"] if group_stack else None,
                "source_row_ids": [row["row_id"]],
                "relationship_status": "layout_candidate_not_ground_truth",
                "evidence": evidence,
                **{name: value for name, value in values.items() if value is not None},
            }
            records.append(record)
            previous_record = record
            row_type = "record"
        structured_rows.append({
            "row_id": row["row_id"],
            "cells": cells,
            "row_type": row_type,
            "source_block_ids": [block["block_id"] for block in row["blocks"]],
            "grid_region_id": row.get("grid_region_id"),
            "grid_row_index": row.get("grid_row_index"),
            "crossing_block_ids": row.get("crossing_block_ids", []),
        })
        previous_bottom = row["bbox"][3]

    column_counts = [len(region["column_centres"]) for region in regions] or [len(fallback_centres)]
    dominant_columns = Counter(column_counts).most_common(1)[0][0] if column_counts else 0
    family = {2: "hai_cot_can_chinh", 3: "ba_cot_can_chinh", 4: "bon_cot_can_chinh"}.get(dominant_columns, "nhieu_cot_hoac_khong_xac_dinh")
    region_layouts = [
        {**region, "column_roles": region_roles.get(region["region_id"], [])}
        for region in regions
    ]
    return {
        "document_id": page["document_id"],
        "page_number": page["page_number"],
        "source_image": page["image_path"],
        "warning": "Đây là ứng viên layout suy ra từ OCR; cần đối chiếu ảnh gốc hoặc ground truth.",
        "layout": {
            "family": family,
            "column_centres_x": [round(value, 2) for value in fallback_centres],
            "column_roles": fallback_roles,
            "table_regions": region_layouts,
            "typical_block_height_px": round(typical_height, 2),
            "table_grid": table_grid or {"available": False, "reason": "chưa chạy phát hiện lưới"},
            "page_reference": None if pagination is None else {
                "text": pagination["text"],
                "page_number": pagination["page_number"],
                "total_pages": pagination["total_pages"],
                "matched_label": pagination["matched_label"],
                "source_block_ids": [str(block["block_id"]) for block in pagination["source_blocks"]],
            },
        },
        "groups": group_stack,
        "rows": structured_rows,
        "records": records,
        "summary": {"ocr_blocks": len(blocks), "physical_rows": len(rows), "columns": dominant_columns, "table_regions": len(regions), "candidate_groups": len(group_stack), "candidate_records": len(records)},
    }


def reconstruct_document(
    predictions: dict[str, Any],
    table_grids: dict[str, dict[str, Any]] | None = None,
    cell_ocr_by_page: dict[str, dict[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    table_grids = table_grids or {}
    cell_ocr_by_page = cell_ocr_by_page or {}
    pages = [
        reconstruct_page(
            page,
            table_grids.get(page["document_id"]),
            cell_ocr_by_page.get(page["document_id"]),
        )
        for page in predictions.get("pages", [])
    ]
    return {"schema_version": "2.0", "method": "per_page_geometry_layout_reconstruction", "pages": pages,
            "summary": {"pages": len(pages), "records": sum(page["summary"]["candidate_records"] for page in pages), "families": dict(Counter(page["layout"]["family"] for page in pages))}}
