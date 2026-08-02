"""Generic semantic roles, table candidates, and logical-record reconstruction."""

from __future__ import annotations

import re
from statistics import median
from typing import Any

from layout_graph import repeated_column_anchors


# Conservative generic form such as 003.085 or 040.077. Slash-separated
# dates/ratios and hyphenated document IDs are deliberately excluded.
PARAMETER_CODE = re.compile(r"^(?:[A-Za-z]{1,4}[- ]?)?\d{2,4}\.\d{2,4}(?:\.\d{1,4})?(?:\b|\s|$)")
NUMBER_OR_UNIT = re.compile(r"(?:\d|[<>=±%Ω]|\b(?:ms|s|A|V|kV|Hz|Ohm)\b)", re.IGNORECASE)


def _uppercase_ratio(text: str) -> float:
    letters = [character for character in text if character.isalpha()]
    return sum(character.isupper() for character in letters) / len(letters) if letters else 0.0


def infer_semantic_roles(blocks: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    if not blocks:
        return
    median_height = median(block["height_normalized"] for block in blocks)
    by_id = {block["id"]: block for block in blocks}
    row_by_id = {row["id"]: row for row in rows}
    for block in blocks:
        text = block["text"].strip()
        x1, _, x2, _ = block["bbox_normalized"]
        centered = abs((x1 + x2) / 2 - 0.5) <= 0.18
        role, confidence = "unassigned", 0.0
        if PARAMETER_CODE.match(text):
            role, confidence = "parameter_code", 0.92
        elif text.endswith(":") and len(text) <= 100:
            role, confidence = "parameter_name", 0.78
        elif centered and len(text) <= 120 and block["height_normalized"] >= median_height * 1.08 and _uppercase_ratio(text) >= 0.55:
            role, confidence = "section_heading", 0.72
        else:
            row = row_by_id[block["row_id"]]
            position = row["block_ids"].index(block["id"])
            has_left_peer = position > 0
            if has_left_peer and (NUMBER_OR_UNIT.search(text) or x1 >= 0.32):
                role, confidence = "parameter_value", 0.58
            elif has_left_peer:
                role, confidence = "parameter_name", 0.42
        block["semantic_role"] = role
        block["role_confidence"] = confidence


def _row_text(row: dict[str, Any], by_id: dict[str, dict[str, Any]], start: int = 0) -> str:
    return " ".join(by_id[block_id]["text"] for block_id in row["block_ids"][start:] if by_id[block_id]["text"])


def reconstruct_records(blocks: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build record hypotheses from generic code/label anchors and aligned continuations."""
    if not blocks:
        return []
    by_id = {block["id"]: block for block in blocks}
    median_height = median(block["height_normalized"] for block in blocks)
    records: list[dict[str, Any]] = []
    consumed_rows: set[str] = set()

    def attach(record: dict[str, Any], block_ids: list[str], role: str) -> None:
        for block_id in block_ids:
            if block_id not in record["block_ids"]:
                record["block_ids"].append(block_id)
            block = by_id[block_id]
            block["record_id"] = record["record_id"]
            if block["semantic_role"] == "unassigned" or role == "continuation_line":
                block["semantic_role"] = role
                block["role_confidence"] = max(block["role_confidence"], 0.62)

    for row_index, row in enumerate(rows):
        ids = row["block_ids"]
        if not ids or row["id"] in consumed_rows:
            continue
        code_positions = [index for index, block_id in enumerate(ids) if PARAMETER_CODE.match(by_id[block_id]["text"])]
        label_positions = [index for index, block_id in enumerate(ids) if by_id[block_id]["text"].endswith(":")]
        generic_column_record = (
            not code_positions
            and not label_positions
            and len(ids) >= 3
            and all(by_id[block_id]["semantic_role"] != "section_heading" for block_id in ids)
        )
        anchor_position = code_positions[0] if code_positions else (label_positions[0] if label_positions else (0 if generic_column_record else None))
        if anchor_position is None:
            continue

        record_id = f"record_{len(records) + 1:04d}"
        record: dict[str, Any] = {
            "record_id": record_id,
            "code": None,
            "name": None,
            "values": [],
            "block_ids": [],
            "source_row_ids": [row["id"]],
            "confidence": 0.0,
        }
        anchor_id = ids[anchor_position]
        anchor = by_id[anchor_id]
        tail_ids = ids[anchor_position + 1 :]
        value_start_x: float | None = None
        if code_positions:
            record["code"] = anchor["text"]
            attach(record, [anchor_id], "parameter_code")
            second_code_position = next((position for position in code_positions if position > anchor_position), None)
            if second_code_position is not None:
                name_ids = ids[anchor_position + 1 : second_code_position]
                value_ids = ids[second_code_position:]
            elif len(tail_ids) >= 2:
                name_ids, value_ids = tail_ids[:1], tail_ids[1:]
            else:
                name_ids, value_ids = tail_ids, []
            record["name"] = " ".join(by_id[item]["text"] for item in name_ids) or None
            attach(record, name_ids, "parameter_name")
        elif label_positions:
            record["name"] = anchor["text"].rstrip(":").strip() or anchor["text"]
            attach(record, [anchor_id], "parameter_name")
            value_ids = tail_ids
        else:
            name_ids = ids[:2]
            value_ids = ids[2:]
            record["name"] = " | ".join(by_id[item]["text"] for item in name_ids)
            attach(record, name_ids, "parameter_name")

        if value_ids:
            value_text = " ".join(by_id[item]["text"] for item in value_ids)
            record["values"].append({"text": value_text, "block_ids": list(value_ids), "line_count": 1})
            attach(record, value_ids, "parameter_value")
            value_start_x = by_id[value_ids[0]]["bbox_normalized"][0]
        elif tail_ids:
            value_start_x = by_id[tail_ids[0]]["bbox_normalized"][0]

        previous_bottom = row["bbox"][3]
        for continuation_row in rows[row_index + 1 :]:
            gap = continuation_row["bbox"][1] - previous_bottom
            if gap > median_height * 2.8:
                break
            continuation_ids = continuation_row["block_ids"]
            if not continuation_ids:
                continue
            first = by_id[continuation_ids[0]]
            first_x = first["bbox_normalized"][0]
            begins_new_anchor = PARAMETER_CODE.match(first["text"]) and first_x <= anchor["bbox_normalized"][0] + 0.035
            if begins_new_anchor or first["text"].endswith(":"):
                break
            expected_x = value_start_x if value_start_x is not None else anchor["bbox_normalized"][2]
            if first_x < expected_x - 0.045:
                break
            line_text = _row_text(continuation_row, by_id)
            if not line_text:
                continue
            is_new_value = bool(PARAMETER_CODE.match(first["text"]))
            if is_new_value or not record["values"]:
                record["values"].append({"text": line_text, "block_ids": list(continuation_ids), "line_count": 1})
                attach(record, continuation_ids, "parameter_value")
            else:
                record["values"][-1]["text"] = f"{record['values'][-1]['text']} {line_text}".strip()
                record["values"][-1]["block_ids"].extend(continuation_ids)
                record["values"][-1]["line_count"] += 1
                attach(record, continuation_ids, "continuation_line")
            record["source_row_ids"].append(continuation_row["id"])
            consumed_rows.add(continuation_row["id"])
            previous_bottom = continuation_row["bbox"][3]

        evidence = int(record["code"] is not None) + int(record["name"] is not None) + int(bool(record["values"]))
        record["confidence"] = round(min(0.95, 0.35 + evidence * 0.18 + min(0.12, len(record["block_ids"]) * 0.015)), 3)
        record["is_multiline"] = len(record["source_row_ids"]) > 1 or any(value["line_count"] > 1 for value in record["values"])
        record["is_multi_value"] = len(record["values"]) > 1
        records.append(record)
        consumed_rows.add(row["id"])
    return records


def detect_table_candidates(rows: list[dict[str, Any]], blocks: list[dict[str, Any]], line_evidence: dict[str, float]) -> list[dict[str, Any]]:
    """Infer table-like zones from repeated columns, with optional border evidence."""
    by_id = {block["id"]: block for block in blocks}
    multi_column_rows = [row for row in rows if len(row["block_ids"]) >= 2]
    if len(multi_column_rows) < 3:
        return []
    anchors = repeated_column_anchors(multi_column_rows, blocks)
    stable_anchors = [anchor for anchor in anchors if anchor["support"] >= 3]
    if len(stable_anchors) < 2:
        return []
    bbox = [
        min(row["bbox"][0] for row in multi_column_rows),
        min(row["bbox"][1] for row in multi_column_rows),
        max(row["bbox"][2] for row in multi_column_rows),
        max(row["bbox"][3] for row in multi_column_rows),
    ]
    border_score = min(1.0, (line_evidence.get("horizontal_density", 0.0) + line_evidence.get("vertical_density", 0.0)) * 22.0)
    alignment_score = min(1.0, len(stable_anchors) / 5.0 + len(multi_column_rows) / max(10.0, len(rows)))
    return [{
        "table_id": "table_0001",
        "bbox_normalized": bbox,
        "row_ids": [row["id"] for row in multi_column_rows],
        "column_anchors": stable_anchors,
        "alignment_score": round(alignment_score, 3),
        "bordered_likelihood": round(border_score, 3),
        "classification": "possibly_bordered" if border_score >= 0.35 else "aligned_columns_without_confirmed_borders",
    }]
