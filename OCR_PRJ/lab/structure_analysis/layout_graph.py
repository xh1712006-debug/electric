"""Coordinate normalization, reading rows, and generic geometric graph edges."""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any


def overlap_1d(a1: float, a2: float, b1: float, b2: float) -> float:
    intersection = max(0.0, min(a2, b2) - max(a1, b1))
    denominator = max(1e-9, min(a2 - a1, b2 - b1))
    return intersection / denominator


def normalize_blocks(raw_blocks: list[dict[str, Any]], image_width: int, image_height: int, page_number: int) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_blocks):
        polygon = [[float(x), float(y)] for x, y in raw["polygon"]]
        xs = [point[0] for point in polygon]
        ys = [point[1] for point in polygon]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
        normalized = [bbox[0] / image_width, bbox[1] / image_height, bbox[2] / image_width, bbox[3] / image_height]
        blocks.append({
            "id": str(raw.get("id", f"b{index:04d}")),
            "page_number": page_number,
            "text": " ".join(str(raw.get("text", "")).split()),
            "polygon": polygon,
            "bbox": bbox,
            "bbox_normalized": normalized,
            "center_normalized": [(normalized[0] + normalized[2]) / 2, (normalized[1] + normalized[3]) / 2],
            "width_normalized": normalized[2] - normalized[0],
            "height_normalized": normalized[3] - normalized[1],
            "detection_confidence": raw.get("detection_confidence"),
            "recognition_confidence": raw.get("recognition_confidence"),
            "row_id": None,
            "semantic_role": "unassigned",
            "role_confidence": 0.0,
            "record_id": None,
        })
    return blocks


def assign_reading_rows(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cluster blocks into rows without relying on absolute page coordinates."""
    if not blocks:
        return []
    median_height = median(block["height_normalized"] for block in blocks)
    rows: list[dict[str, Any]] = []
    for block in sorted(blocks, key=lambda item: (item["center_normalized"][1], item["bbox_normalized"][0])):
        y1, y2 = block["bbox_normalized"][1], block["bbox_normalized"][3]
        candidate = None
        candidate_distance = float("inf")
        for row in rows:
            vertical_overlap = overlap_1d(y1, y2, row["bbox"][1], row["bbox"][3])
            distance = abs(block["center_normalized"][1] - row["center_y"])
            if (vertical_overlap >= 0.35 or distance <= median_height * 0.65) and distance < candidate_distance:
                candidate, candidate_distance = row, distance
        if candidate is None:
            candidate = {"id": "", "block_ids": [], "bbox": list(block["bbox_normalized"]), "center_y": block["center_normalized"][1]}
            rows.append(candidate)
        candidate["block_ids"].append(block["id"])
        candidate["bbox"] = [
            min(candidate["bbox"][0], block["bbox_normalized"][0]),
            min(candidate["bbox"][1], y1),
            max(candidate["bbox"][2], block["bbox_normalized"][2]),
            max(candidate["bbox"][3], y2),
        ]
        candidate["center_y"] = (candidate["bbox"][1] + candidate["bbox"][3]) / 2

    by_id = {block["id"]: block for block in blocks}
    rows.sort(key=lambda row: row["center_y"])
    for index, row in enumerate(rows):
        row["id"] = f"row_{index:04d}"
        row["block_ids"].sort(key=lambda block_id: by_id[block_id]["bbox_normalized"][0])
        for block_id in row["block_ids"]:
            by_id[block_id]["row_id"] = row["id"]
    return rows


def build_graph(blocks: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {block["id"]: block for block in blocks}
    edges: list[dict[str, Any]] = []
    edge_keys: set[tuple[str, str, str]] = set()

    def add_edge(source: str, target: str, relation: str, distance: float, overlap: float = 0.0) -> None:
        key = (source, target, relation)
        if source != target and key not in edge_keys:
            edge_keys.add(key)
            edges.append({"source": source, "target": target, "relation": relation, "distance": round(distance, 6), "overlap": round(overlap, 6)})

    for row in rows:
        ids = row["block_ids"]
        for left, right in zip(ids, ids[1:]):
            left_box, right_box = by_id[left]["bbox_normalized"], by_id[right]["bbox_normalized"]
            add_edge(left, right, "nearest_right", max(0.0, right_box[0] - left_box[2]), overlap_1d(left_box[1], left_box[3], right_box[1], right_box[3]))
            add_edge(right, left, "nearest_left", max(0.0, right_box[0] - left_box[2]), overlap_1d(left_box[1], left_box[3], right_box[1], right_box[3]))

    for source in blocks:
        sx1, sy1, sx2, sy2 = source["bbox_normalized"]
        above: tuple[float, dict[str, Any], float] | None = None
        below: tuple[float, dict[str, Any], float] | None = None
        for target in blocks:
            if source["id"] == target["id"]:
                continue
            tx1, ty1, tx2, ty2 = target["bbox_normalized"]
            horizontal_overlap = overlap_1d(sx1, sx2, tx1, tx2)
            center_dx = abs(source["center_normalized"][0] - target["center_normalized"][0])
            if horizontal_overlap < 0.2 and center_dx > max(source["width_normalized"], target["width_normalized"], 0.04):
                continue
            if ty2 <= sy1:
                gap = sy1 - ty2
                if above is None or gap < above[0]:
                    above = (gap, target, horizontal_overlap)
            elif ty1 >= sy2:
                gap = ty1 - sy2
                if below is None or gap < below[0]:
                    below = (gap, target, horizontal_overlap)
            if abs(sx1 - tx1) <= 0.018 and abs(source["center_normalized"][1] - target["center_normalized"][1]) <= 0.25:
                add_edge(source["id"], target["id"], "aligned_left", abs(sx1 - tx1), horizontal_overlap)
        if above:
            add_edge(source["id"], above[1]["id"], "nearest_above", above[0], above[2])
        if below:
            add_edge(source["id"], below[1]["id"], "nearest_below", below[0], below[2])

    return {"nodes": blocks, "rows": rows, "edges": edges}


def repeated_column_anchors(rows: list[dict[str, Any]], blocks: list[dict[str, Any]], tolerance: float = 0.025) -> list[dict[str, Any]]:
    by_id = {block["id"]: block for block in blocks}
    anchors: list[list[float]] = []
    for row in rows:
        for block_id in row["block_ids"]:
            x = by_id[block_id]["bbox_normalized"][0]
            cluster = next((values for values in anchors if abs(sum(values) / len(values) - x) <= tolerance), None)
            if cluster is None:
                anchors.append([x])
            else:
                cluster.append(x)
    return [
        {"x": round(sum(values) / len(values), 6), "support": len(values)}
        for values in anchors
        if len(values) >= 2
    ]
