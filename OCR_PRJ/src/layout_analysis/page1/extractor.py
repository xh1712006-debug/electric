"""Template-aware page-1 layout reconstruction from OCR geometry and table grid."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from ..pagination import TICKET_PATTERN, detect_page_reference
from .field_resolution import Page1FieldResolutionEngine
from .relationships import RelationshipPolicy
from .rules import FieldRuleRegistry, load_field_rule_registry
from .schema import (
    COVER_TABLE_FIELD_NAMES,
    COVER_TABLE_ROWS,
    FIELD_SPECS,
    PAGE1_FIELD_NAMES,
    PROTECTION_TABLE_ROLES,
)


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _bbox(block: dict[str, Any]) -> list[float]:
    if "bbox_pixel" in block:
        return [float(value) for value in block["bbox_pixel"]]
    polygon = block["polygon"]
    xs = [float(point[0]) for point in polygon]
    ys = [float(point[1]) for point in polygon]
    return [min(xs), min(ys), max(xs), max(ys)]


def _text(block: dict[str, Any]) -> str:
    return " ".join(str(block.get("text", "")).split())


def _confidence(block: dict[str, Any]) -> float | None:
    value = block.get("recognition_score", block.get("confidence"))
    return round(float(value), 4) if isinstance(value, (int, float)) else None


def _source_block_ids(block: dict[str, Any]) -> list[str]:
    identifiers = block.get("_source_block_ids")
    if isinstance(identifiers, list):
        return [str(identifier) for identifier in identifiers]
    return [str(block["block_id"])]


def _segment_ids(block: dict[str, Any]) -> list[str]:
    identifiers = block.get("_segment_ids")
    if isinstance(identifiers, list):
        return [str(identifier) for identifier in identifiers]
    return [str(block.get("_segment_id", block["block_id"]))]


def _alias_pattern(alias: str) -> re.Pattern[str]:
    tokens = [token for token in re.split(r"[^\w]+", alias, flags=re.UNICODE) if token]
    return re.compile(r"(?<!\w)" + r"[^\w]*".join(re.escape(token) for token in tokens), re.IGNORECASE)


def _split_embedded_labels(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Split OCR lines at every embedded known label and preserve source spans.

    A detector may return one line such as `PCS-902 Phiên bản:`. Treating that
    as one value lets the same text leak into both fields. Virtual segments keep
    the original block provenance while giving each text span its own geometry.
    """

    aliases = sorted({alias for spec in FIELD_SPECS.values() for alias in spec["labels"]}, key=len, reverse=True)
    patterns = [(alias, _alias_pattern(alias)) for alias in aliases]
    split_blocks: list[dict[str, Any]] = []
    for block in blocks:
        text = _text(block)
        starts = sorted({
            match.start()
            for alias, pattern in patterns
            for match in pattern.finditer(text)
            if match.start() > 0
            and (_normalise(alias) == "phien ban" or text[match.end():].lstrip().startswith(":"))
        })
        if not starts:
            split_blocks.append({**block, "_segment_id": str(block.get("_segment_id", block["block_id"]))})
            continue
        x1, y1, x2, y2 = _bbox(block)
        source_ids = _source_block_ids(block)
        boundaries = [0, *starts, len(text)]
        for index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
            part = text[start:end].strip()
            if not part:
                continue
            left = x1 + (x2 - x1) * start / max(1, len(text))
            right = x1 + (x2 - x1) * end / max(1, len(text))
            split_blocks.append({
                **block,
                "text": part,
                "bbox_pixel": [left, y1, right, y2],
                "_source_block_ids": source_ids,
                "_segment_id": f"{block['block_id']}#part{index}",
            })
    return split_blocks


def _overlap(first: tuple[float, float], second: tuple[float, float]) -> float:
    intersect = max(0.0, min(first[1], second[1]) - max(first[0], second[0]))
    return intersect / max(1.0, min(first[1] - first[0], second[1] - second[0]))


def _grid_position(block: dict[str, Any], grid: dict[str, Any]) -> tuple[str, int, int] | None:
    x1, y1, x2, y2 = _bbox(block)
    centre_x, centre_y = (x1 + x2) / 2, (y1 + y2) / 2
    for region in grid.get("regions", []):
        rx1, ry1, rx2, ry2 = region["bbox"]
        if not (rx1 <= centre_x <= rx2 and ry1 <= centre_y <= ry2):
            continue
        row = min(range(len(region["row_bands"])), key=lambda index: abs(centre_y - sum(region["row_bands"][index]) / 2))
        boundaries = region["vertical_lines"]
        column = max(0, min(len(boundaries) - 2, next((index for index, right in enumerate(boundaries[1:]) if centre_x <= right), len(boundaries) - 2)))
        return str(region["region_id"]), row, column
    return None


def _label_match(text: str, aliases: list[str]) -> str | None:
    normalised = _normalise(text)
    matches = []
    for alias in aliases:
        normalised_alias = _normalise(alias)
        if not normalised.startswith(normalised_alias):
            continue
        match = _alias_pattern(alias).match(text)
        tail = text[match.end():].lstrip() if match else ""
        # Short field names also occur naturally inside values. For example,
        # `Máy cắt liên lạc 220kV` is the protected-equipment value, not a
        # second `Máy cắt` label. Without an explicit separator, accept a
        # continued short label only when its first token looks like a value
        # code (273, V4.8, DIGSI, ...), rather than ordinary prose.
        if tail and not tail.startswith((":", "：")) and len(normalised_alias.split()) <= 2:
            first_token = re.sub(r"[^\w.-]+", "", tail.split()[0], flags=re.UNICODE)
            looks_like_code = any(char.isdigit() for char in first_token) or (
                len(first_token) >= 2 and first_token.isupper()
            )
            if not looks_like_code:
                continue
        matches.append(alias)
    return max(matches, key=len) if matches else None


def _label_candidates(blocks: list[dict[str, Any]], aliases: list[str], grid: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    """Find labels contained in one OCR block or split over two nearby lines."""

    candidates: list[tuple[dict[str, Any], str]] = []
    ordered = sorted(blocks, key=lambda block: (_bbox(block)[1], _bbox(block)[0]))
    for block in ordered:
        direct = _label_match(_text(block), aliases)
        if direct:
            candidates.append((block, direct))
            continue
        x1, y1, x2, y2 = _bbox(block)
        position = _grid_position(block, grid)
        for continuation in ordered:
            if continuation is block:
                continue
            cx1, cy1, cx2, cy2 = _bbox(continuation)
            if cy1 < y1 or cy1 > y2 + max(20.0, (y2 - y1) * 0.9):
                continue
            horizontal_overlap = max(0.0, min(x2, cx2) - max(x1, cx1)) / max(1.0, min(x2 - x1, cx2 - cx1))
            continuation_position = _grid_position(continuation, grid)
            same_cell = position is not None and continuation_position is not None and position == continuation_position
            if horizontal_overlap < 0.35 and not (same_cell and abs(cx1 - x1) <= 80):
                continue
            combined = f"{_text(block)} {_text(continuation)}"
            match = _label_match(combined, aliases)
            if not match:
                continue
            scores = [score for score in (_confidence(block), _confidence(continuation)) if score is not None]
            merged = {
                **block,
                "text": combined,
                "bbox_pixel": [min(x1, cx1), min(y1, cy1), max(x2, cx2), max(y2, cy2)],
                "recognition_score": sum(scores) / len(scores) if scores else None,
                "_source_block_ids": list(dict.fromkeys([*_source_block_ids(block), *_source_block_ids(continuation)])),
                "_segment_ids": list(dict.fromkeys([*_segment_ids(block), *_segment_ids(continuation)])),
            }
            candidates.append((merged, match))
            break
    return candidates


def _inline_value(text: str, matched_label: str) -> str:
    if ":" in text:
        return text.split(":", 1)[1].strip()
    normalised_label = _normalise(matched_label)
    words = text.split()
    for count in range(1, len(words) + 1):
        if _normalise(" ".join(words[:count])) == normalised_label:
            return " ".join(words[count:]).strip(" :-")
    return ""


def _field_inline_value(name: str, text: str, matched_label: str) -> str:
    inline = _inline_value(text, matched_label)
    # A one-character tail after this long textual label is commonly a
    # detector/OCR boundary artefact; the neighbouring blocks hold the value.
    if name == "protection_type" and len(_normalise(inline)) < 5:
        return ""
    return inline


def _value_start_x(label: dict[str, Any], matched_label: str) -> float:
    """Estimate where the value starts when label and value share one OCR line."""

    x1, _, x2, _ = _bbox(label)
    text = _text(label)
    match = _alias_pattern(matched_label).search(text)
    if not match:
        return x2
    boundary = match.end()
    colon = text.find(":", boundary)
    if 0 <= colon <= boundary + 3:
        boundary = colon + 1
    return x1 + (x2 - x1) * boundary / max(1, len(text))


def _next_logical_row_y(
    label: dict[str, Any],
    blocks: list[dict[str, Any]],
    all_aliases: list[str],
) -> float | None:
    """Find the next labelled row on the same broad half of a borderless table."""

    label_box = _bbox(label)
    label_center_x = (label_box[0] + label_box[2]) / 2
    label_center_y = (label_box[1] + label_box[3]) / 2
    label_height = max(1.0, label_box[3] - label_box[1])
    page_width = max((_bbox(block)[2] for block in blocks), default=label_box[2])
    split_x = page_width * 0.5
    label_side = label_center_x >= split_x
    minimum_center_y = label_center_y + max(12.0, label_height * 0.65)
    rows = []
    for block in blocks:
        if not any(_label_match(_text(block), [alias]) for alias in all_aliases):
            continue
        box = _bbox(block)
        center_x = (box[0] + box[2]) / 2
        center_y = (box[1] + box[3]) / 2
        if center_y <= minimum_center_y:
            continue
        same_side = (center_x >= split_x) == label_side
        horizontally_near = abs(center_x - label_center_x) <= page_width * 0.22
        if same_side or horizontally_near:
            rows.append(box[1])
    return min(rows) if rows else None


def _next_ruling_line_y(label: dict[str, Any], grid: dict[str, Any]) -> float | None:
    """Return the first strong horizontal cell boundary below a label."""

    box = _bbox(label)
    center_y = (box[1] + box[3]) / 2
    minimum = center_y + max(5.0, (box[3] - box[1]) * 0.15)
    candidates = [
        float(y) for y in grid.get("page_horizontal_lines", [])
        if float(y) > minimum
    ]
    return min(candidates) if candidates else None


def _value_candidates(
    name: str,
    label: dict[str, Any],
    matched_label: str,
    blocks: list[dict[str, Any]],
    grid: dict[str, Any],
    all_aliases: list[str],
) -> list[dict[str, Any]]:
    label_box = _bbox(label)
    label_position = _grid_position(label, grid)
    label_segment_ids = set(_segment_ids(label))
    label_center_x = (label_box[0] + label_box[2]) / 2
    value_start_x = _value_start_x(label, matched_label)
    block_heights = [max(1.0, _bbox(block)[3] - _bbox(block)[1]) for block in blocks]
    typical_height = sorted(block_heights)[len(block_heights) // 2] if block_heights else 25.0
    next_row_y = _next_logical_row_y(label, blocks, all_aliases) if label_position is None else None
    ruling_bottom = _next_ruling_line_y(label, grid) if label_position is None else None
    maximum_row_depth = max(120.0, typical_height * 3.0)
    lower_boundaries = [
        value for value in (next_row_y, ruling_bottom)
        if value is not None and value - label_box[3] <= maximum_row_depth
    ]
    continuation_bottom = (
        min(lower_boundaries)
        if lower_boundaries
        else label_box[3] + max(30.0, typical_height * 0.9)
    )
    allow_borderless_continuation = FIELD_SPECS.get(name, {}).get("source_policy") == "right_cell"
    next_label_x = min((
        _bbox(block)[0] for block in blocks
        if not label_segment_ids.intersection(_segment_ids(block))
        and any(_label_match(_text(block), [alias]) for alias in all_aliases)
        and _bbox(block)[0] > label_box[0]
        and _overlap((label_box[1], label_box[3]), (_bbox(block)[1], _bbox(block)[3])) >= 0.35
    ), default=float("inf"))
    candidates = []
    for block in blocks:
        if label_segment_ids.intersection(_segment_ids(block)) or any(_label_match(_text(block), [alias]) for alias in all_aliases):
            continue
        box = _bbox(block)
        position = _grid_position(block, grid)
        center_x = (box[0] + box[2]) / 2
        center_y = (box[1] + box[3]) / 2
        same_grid_row = bool(label_position and position and label_position[:2] == position[:2] and position[2] >= label_position[2])
        same_visual_row = _overlap((label_box[1], label_box[3]), (box[1], box[3])) >= 0.35
        inferred_same_cell = bool(
            label_position is None
            and allow_borderless_continuation
            and box[1] >= label_box[1] + min(10.0, typical_height * 0.35)
            and box[1] <= label_box[3] + max(12.0, typical_height * 0.55)
            and center_y < continuation_bottom
            and center_x >= value_start_x - max(12.0, typical_height * 0.5)
        )
        if name == "relay_version":
            geometrically_valid = (same_visual_row and center_x >= label_box[2]) or inferred_same_cell
        else:
            geometrically_valid = ((same_grid_row or same_visual_row) and center_x > label_center_x) or inferred_same_cell
        if geometrically_valid and center_x < next_label_x:
            candidates.append(block)
    return sorted(candidates, key=lambda block: (_bbox(block)[1], _bbox(block)[0]))


def _field(name: str, label: dict[str, Any], matched_label: str, value_blocks: list[dict[str, Any]], page_number: int, grid: dict[str, Any]) -> dict[str, Any]:
    inline = _field_inline_value(name, _text(label), matched_label)
    texts = [inline] if inline else []
    for block in value_blocks:
        candidate = _text(block)
        normalised_candidate = _normalise(candidate)
        normalised_texts = [_normalise(text) for text in texts]
        if not normalised_candidate or any(normalised_candidate == text or normalised_candidate in text for text in normalised_texts):
            continue
        if normalised_texts and any(text and text in normalised_candidate for text in normalised_texts):
            texts = [candidate if text and text in normalised_candidate else original for original, text in zip(texts, normalised_texts)]
        else:
            texts.append(candidate)
    source_blocks = [label, *value_blocks]
    confidences = [value for value in (_confidence(block) for block in source_blocks) if value is not None]
    position = _grid_position(label, grid)
    source_ids = list(dict.fromkeys(identifier for block in source_blocks for identifier in _source_block_ids(block)))
    return {
        "text": " ".join(texts),
        "matched_label": matched_label,
        "source_page": page_number,
        "source_cell": f"{position[0]}:{position[1]}:{position[2]}" if position else None,
        "source_block_ids": source_ids,
        "source_bboxes": [_bbox(block) for block in source_blocks],
        "confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
        "_label_y": sum(_bbox(label)[1::2]) / 2,
        "_label_x": sum(_bbox(label)[::2]) / 2,
    }


def _direct_evidence(block: dict[str, Any], text: str, matched_label: str, page_number: int, grid: dict[str, Any]) -> dict[str, Any]:
    position = _grid_position(block, grid)
    return {
        "text": text.strip(),
        "matched_label": matched_label,
        "source_page": page_number,
        "source_cell": f"{position[0]}:{position[1]}:{position[2]}" if position else None,
        "source_block_ids": _source_block_ids(block),
        "source_bboxes": [_bbox(block)],
        "confidence": _confidence(block),
    }


def _cover_table_region(grid: dict[str, Any]) -> dict[str, Any] | None:
    """Return the upper seven-row company-defined general-description table."""

    candidates = [
        region for region in grid.get("regions", [])
        if len(region.get("row_bands", [])) >= len(COVER_TABLE_ROWS)
        and len(region.get("vertical_lines", [])) >= 3
    ]
    return min(candidates, key=lambda region: (region["bbox"][1], region["bbox"][0])) if candidates else None


def _canonical_cover_rows(region: dict[str, Any]) -> list[list[float]] | None:
    """Normalise occasional tiny spurious bands to the seven regulated rows."""

    bands = [[float(top), float(bottom)] for top, bottom in region.get("row_bands", [])]
    target = len(COVER_TABLE_ROWS)
    while len(bands) > target:
        smallest = min(range(len(bands)), key=lambda index: bands[index][1] - bands[index][0])
        if smallest == 0:
            bands[1][0] = bands[0][0]
        else:
            bands[smallest - 1][1] = bands[smallest][1]
        bands.pop(smallest)
    return bands if len(bands) == target else None


def _cover_horizontal_boundaries(region: dict[str, Any]) -> tuple[float, float, float, float]:
    left, _, right, _ = [float(value) for value in region["bbox"]]
    expected_middle = (left + right) / 2
    interior = [float(value) for value in region.get("vertical_lines", [])[1:-1]]
    middle_candidates = [value for value in interior if abs(value - expected_middle) <= (right - left) * 0.16]
    middle = min(middle_candidates, key=lambda value: abs(value - expected_middle)) if middle_candidates else expected_middle
    right_width = right - middle
    secondary_candidates = [
        value for value in interior
        if middle + right_width * 0.42 <= value <= middle + right_width * 0.82
    ]
    secondary = (
        sum(secondary_candidates) / len(secondary_candidates)
        if secondary_candidates
        else middle + right_width * 0.62
    )
    return left, middle, secondary, right


def _slot_bounds(slot_name: str, boundaries: tuple[float, float, float, float]) -> tuple[float, float, float]:
    left, middle, secondary, right = boundaries
    if slot_name == "left":
        return left, middle, 0.32
    if slot_name == "right":
        return middle, right, 0.34
    if slot_name == "right_primary":
        return middle, secondary, 0.43
    if slot_name == "right_secondary":
        return secondary, right, 0.60
    raise ValueError(f"Unknown cover-table slot: {slot_name}")


def _blocks_in_structure_slot(
    blocks: list[dict[str, Any]],
    row_band: list[float],
    left: float,
    right: float,
) -> list[dict[str, Any]]:
    top, bottom = row_band
    selected = []
    for block in blocks:
        x1, y1, x2, y2 = _bbox(block)
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2
        if top <= center_y <= bottom and left <= center_x <= right:
            selected.append(block)
    return sorted(selected, key=lambda block: (_bbox(block)[1], _bbox(block)[0]))


def _structure_source_label(
    field_name: str,
    label_parts: list[tuple[str, dict[str, Any]]],
    page_number: int,
    source_cell: str,
) -> dict[str, Any] | None:
    if not label_parts:
        return None
    text = " ".join(part.strip(" :：") for part, _block in label_parts if part.strip(" :："))
    if not text:
        return None
    blocks = [block for _part, block in label_parts]
    confidences = [value for value in (_confidence(block) for block in blocks) if value is not None]
    return {
        "text": text,
        "canonical_field": field_name,
        "source_page": page_number,
        "source_cell": source_cell,
        "source_block_ids": list(dict.fromkeys(identifier for block in blocks for identifier in _source_block_ids(block))),
        "source_bboxes": [_bbox(block) for block in blocks],
        "confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
    }


def _structure_slot_field(
    field_name: str,
    slot_blocks: list[dict[str, Any]],
    left: float,
    right: float,
    label_fraction: float,
    page_number: int,
    source_cell: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, set[str]]:
    boundary = left + (right - left) * label_fraction
    label_parts: list[tuple[str, dict[str, Any]]] = []
    value_parts: list[tuple[str, dict[str, Any]]] = []
    for block in slot_blocks:
        text = _text(block)
        box = _bbox(block)
        center_x = (box[0] + box[2]) / 2
        colon = min((index for index in (text.find(":"), text.find("：")) if index >= 0), default=-1)
        if colon >= 0 and box[0] <= boundary:
            label_text = text[:colon].strip()
            value_text = text[colon + 1:].strip()
            if label_text:
                label_parts.append((label_text, block))
            if value_text:
                value_parts.append((value_text, block))
        elif center_x <= boundary:
            label_parts.append((text, block))
        else:
            value_parts.append((text, block))

    source_label = _structure_source_label(field_name, label_parts, page_number, f"{source_cell}:label")
    value_text = " ".join(part for part, _block in value_parts if part).strip()
    used_blocks = [block for _part, block in [*label_parts, *value_parts]]
    assigned = {
        identifier
        for block in used_blocks
        for identifier in _source_block_ids(block)
    }
    if not value_text:
        return None, source_label, assigned
    confidences = [value for value in (_confidence(block) for block in used_blocks) if value is not None]
    label_text = source_label["text"] if source_label else None
    return ({
        "text": value_text,
        "matched_label": label_text,
        "source_label": label_text,
        "extraction_method": "table_structure",
        "source_page": page_number,
        "source_cell": source_cell,
        "source_block_ids": list(dict.fromkeys(identifier for block in used_blocks for identifier in _source_block_ids(block))),
        "source_bboxes": [_bbox(block) for block in used_blocks],
        "confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
    }, source_label, assigned)


def _extract_cover_table_by_structure(
    blocks: list[dict[str, Any]],
    grid: dict[str, Any],
    page_number: int,
) -> tuple[dict[str, Any], dict[str, Any], set[str]] | None:
    """Assign canonical cover fields from regulated table topology, not label text."""

    region = _cover_table_region(grid)
    if region is None:
        return None
    rows = _canonical_cover_rows(region)
    if rows is None:
        return None
    boundaries = _cover_horizontal_boundaries(region)
    fields: dict[str, Any] = {}
    source_labels: dict[str, Any] = {}
    assigned: set[str] = set()
    for row_index, row_slots in enumerate(COVER_TABLE_ROWS):
        for field_name, slot_name in row_slots:
            left, right, label_fraction = _slot_bounds(slot_name, boundaries)
            slot_blocks = _blocks_in_structure_slot(blocks, rows[row_index], left, right)
            source_cell = f"{region['region_id']}:cover_row_{row_index}:{slot_name}"
            field, source_label, field_blocks = _structure_slot_field(
                field_name,
                slot_blocks,
                left,
                right,
                label_fraction,
                page_number,
                source_cell,
            )
            fields[field_name] = field
            source_labels[field_name] = source_label
            assigned.update(field_blocks)
    return fields, source_labels, assigned


def _apply_direct_header_fields(
    fields: dict[str, Any],
    blocks: list[dict[str, Any]],
    grid: dict[str, Any],
    page_number: int,
    warnings: list[str],
) -> None:
    """Read header values independently so a wide page crop cannot consume the ticket."""

    if not blocks:
        return
    page_bottom = max(_bbox(block)[3] for block in blocks)
    header_blocks = [block for block in blocks if _bbox(block)[1] <= page_bottom * 0.20]
    ticket_candidates = []
    for block in header_blocks:
        match = TICKET_PATTERN.search(_text(block))
        if match:
            ticket_candidates.append((block, match.group(0)))
    if ticket_candidates:
        block, ticket = max(ticket_candidates, key=lambda item: (_confidence(item[0]) or 0.0, len(item[1])))
        fields["ticket_number"] = _direct_evidence(block, ticket, "Số phiếu", page_number, grid)
        warnings[:] = [warning for warning in warnings if warning not in {"missing_required_field:ticket_number", "empty_required_field:ticket_number"}]

    warnings[:] = [warning for warning in warnings if warning not in {
        "invalid_page_reference",
        "missing_required_field:page_reference",
        "empty_required_field:page_reference",
    }]
    pagination = detect_page_reference(blocks, expected_page_number=page_number)
    if pagination:
        evidence = _direct_evidence(
            pagination["value_block"],
            pagination["text"],
            pagination["matched_label"] or "pagination_geometry",
            page_number,
            grid,
        )
        source_blocks = pagination["source_blocks"]
        evidence["source_block_ids"] = list(dict.fromkeys(
            identifier for block in source_blocks for identifier in _source_block_ids(block)
        ))
        evidence["source_bboxes"] = [_bbox(block) for block in source_blocks]
        fields["page_reference"] = evidence
        fields["page_number"] = {**evidence, "text": str(pagination["page_number"])}
        fields["total_pages"] = (
            {**evidence, "text": str(pagination["total_pages"])}
            if pagination["total_pages"] is not None
            else None
        )
    if fields["page_reference"] is None:
        warnings.append("missing_required_field:page_reference")
    elif fields["total_pages"] is None:
        warnings.append("invalid_page_reference")


def _extract_fields(blocks: list[dict[str, Any]], grid: dict[str, Any], page_number: int) -> tuple[dict[str, Any], set[str], list[str]]:
    fields: dict[str, Any] = {name: None for name in PAGE1_FIELD_NAMES}
    assigned: set[str] = set()
    warnings: list[str] = []
    aliases = [alias for spec in FIELD_SPECS.values() for alias in spec["labels"]]
    for name, spec in FIELD_SPECS.items():
        if name == "page_reference":
            continue
        labels = _label_candidates(blocks, spec["labels"], grid)
        if not labels:
            if spec.get("required"):
                warnings.append(f"missing_required_field:{name}")
            continue
        extracted = []
        for label, match in labels:
            value_blocks = _value_candidates(name, label, match, blocks, grid, aliases)
            value = _field(name, label, match, value_blocks, page_number, grid)
            if value["text"]:
                extracted.append(value)
                assigned.update(value["source_block_ids"])
        if extracted:
            fields[name] = extracted if spec.get("allow_multiple") else max(extracted, key=lambda item: len(item["text"]))
        elif spec.get("required"):
            warnings.append(f"empty_required_field:{name}")
    versions = fields.get("relay_version")
    if isinstance(versions, list) and versions:
        version_row_tolerance = max(50.0, max(_bbox(block)[3] for block in blocks) * 0.04)

        def same_grid_row(first: dict[str, Any], second: dict[str, Any]) -> bool:
            first_cell = str(first.get("source_cell") or "").split(":")
            second_cell = str(second.get("source_cell") or "").split(":")
            return len(first_cell) >= 2 and len(second_cell) >= 2 and first_cell[:2] == second_cell[:2]

        def version_for(anchor: Any) -> dict[str, Any] | None:
            if not isinstance(anchor, dict):
                return None
            eligible = [
                version for version in versions
                if version["_label_x"] > anchor["_label_x"]
                and abs(version["_label_y"] - anchor["_label_y"]) <= version_row_tolerance
                and (same_grid_row(version, anchor) or not version.get("source_cell") or not anchor.get("source_cell"))
                and _normalise(version["text"]) != _normalise(anchor["text"])
            ]
            return min(eligible, key=lambda item: abs(item["_label_y"] - anchor["_label_y"])) if eligible else None

        relay_anchor = fields.get("relay_name")
        software_anchor = fields.get("software")
        fields["relay_version"] = None
        fields["software_version"] = None
        fields["relay_version"] = version_for(relay_anchor)
        fields["software_version"] = version_for(software_anchor)

    _apply_direct_header_fields(fields, blocks, grid, page_number, warnings)
    for value in fields.values():
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict):
                assigned.update(str(identifier) for identifier in item.get("source_block_ids", []))
                item.pop("_label_y", None)
                item.pop("_label_x", None)
    return fields, assigned, warnings


def _cell_blocks(blocks: list[dict[str, Any]], region: dict[str, Any], row_index: int, column_index: int) -> list[dict[str, Any]]:
    top, bottom = region["row_bands"][row_index]
    left, right = region["vertical_lines"][column_index:column_index + 2]
    selected = []
    for block in blocks:
        x1, y1, x2, y2 = _bbox(block)
        horizontal = max(0.0, min(x2, right) - max(x1, left)) / max(1.0, x2 - x1)
        vertical = max(0.0, min(y2, bottom) - max(y1, top)) / max(1.0, y2 - y1)
        if horizontal >= 0.35 and vertical >= 0.25:
            selected.append(block)
    return sorted(selected, key=lambda block: (_bbox(block)[1], _bbox(block)[0]))


def _extract_protection_records(blocks: list[dict[str, Any]], grid: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    records: list[dict[str, Any]] = []
    assigned: set[str] = set()
    for region in grid.get("regions", []):
        if len(region.get("column_centres", [])) != 6:
            continue
        for row_index in range(len(region["row_bands"])):
            cells = []
            cell_members = []
            for column_index in range(6):
                members = _cell_blocks(blocks, region, row_index, column_index)
                cell_members.append(members)
                cells.append(" ".join(_text(block) for block in members))
            normalised = " ".join(_normalise(cell) for cell in cells)
            header_tokens = sum(token in normalised.split() for token in ("chuc", "cap", "nguong", "gia", "thoi", "tin", "tac"))
            if not any(cells) or header_tokens >= 2 or "chuc nang" in normalised or "nguong chinh dinh" in normalised or "gia tri" in normalised:
                continue
            values = {}
            for role, text, members in zip(PROTECTION_TABLE_ROLES, cells, cell_members):
                if text:
                    values[role] = {"text": text, "source_cell": f"{region['region_id']}:{row_index}:{PROTECTION_TABLE_ROLES.index(role)}", "source_block_ids": [str(block["block_id"]) for block in members]}
                    assigned.update(values[role]["source_block_ids"])
            if values.get("protection_level") or values.get("setting_value"):
                records.append({"record_id": f"protection_{len(records) + 1:03d}", **values})
        for role in ("function", "external_control_signal", "action"):
            populated = [record[role] for record in records if role in record]
            unique = {item["text"] for item in populated}
            if len(unique) == 1:
                template = populated[0]
                for record in records:
                    if role not in record:
                        record[role] = {**template, "inherited_from_merged_cell": True}
    return records, assigned


def extract_page1(
    page: dict[str, Any],
    table_grid: dict[str, Any],
    *,
    field_rule_registry: FieldRuleRegistry | None = None,
    relationship_policy: RelationshipPolicy | None = None,
) -> dict[str, Any]:
    source_blocks = [
        {
            **block,
            "block_id": str(block.get("block_id", f"ocr_{index}")),
            "bbox_pixel": _bbox(block),
        }
        for index, block in enumerate(page.get("block_predictions", []))
        if _text(block)
    ]
    blocks = _split_embedded_labels(source_blocks)
    page_number = int(page.get("page_number", 1))
    fields, field_blocks, warnings = _extract_fields(blocks, table_grid, page_number)
    source_labels: dict[str, Any] = {name: None for name in PAGE1_FIELD_NAMES}
    cover_structure = _extract_cover_table_by_structure(blocks, table_grid, page_number)
    if cover_structure is not None:
        structure_fields, structure_labels, structure_blocks = cover_structure
        # The company form fixes canonical meaning by row/side. Geometry owns
        # these fields; OCR label aliases are evidence only and cannot steal a
        # neighbouring slot when the wording changes.
        for field_name in COVER_TABLE_FIELD_NAMES:
            fields[field_name] = structure_fields[field_name]
            source_labels[field_name] = structure_labels[field_name]
        field_blocks.update(structure_blocks)
        cover_strategy = "table_structure"
    else:
        cover_strategy = "label_fallback"
        for field_name, field in fields.items():
            if not isinstance(field, dict) or not field.get("matched_label"):
                continue
            source_labels[field_name] = {
                "text": field["matched_label"],
                "canonical_field": field_name,
                "source_page": page_number,
                "source_cell": field.get("source_cell"),
                "source_block_ids": field.get("source_block_ids", []),
                "source_bboxes": field.get("source_bboxes", []),
                "confidence": field.get("confidence"),
            }
    for name, anchor in {
        "form_title": "Phiếu chỉnh định rơ-le bảo vệ",
        "protection_principle_heading": "Nguyên tắc hoạt động của các chức năng bảo vệ chính trong rơ-le",
    }.items():
        candidates = [block for block in blocks if _normalise(anchor) in _normalise(_text(block))]
        if candidates:
            block = max(candidates, key=lambda item: len(_text(item)))
            fields[name] = {"text": _text(block), "matched_label": anchor, "source_page": page_number,
                            "source_cell": None, "source_block_ids": [str(block["block_id"])],
                            "source_bboxes": [_bbox(block)], "confidence": _confidence(block)}
            field_blocks.add(str(block["block_id"]))
    for field_name, field in fields.items():
        if source_labels.get(field_name) is not None:
            continue
        candidates = field if isinstance(field, list) else [field]
        item = next((candidate for candidate in candidates if isinstance(candidate, dict)), None)
        if item is None:
            continue
        label_text = item.get("source_label") or item.get("matched_label")
        if not label_text:
            continue
        source_labels[field_name] = {
            "text": label_text,
            "canonical_field": field_name,
            "source_page": page_number,
            "source_cell": item.get("source_cell"),
            "source_block_ids": item.get("source_block_ids", []),
            "source_bboxes": item.get("source_bboxes", []),
            "confidence": item.get("confidence"),
        }
    # Table 02 varies materially between form families. Keep its grid evidence,
    # but defer semantic record extraction until it has a dedicated analyser.
    records: list[dict[str, Any]] = []
    record_blocks: set[str] = set()
    assigned = field_blocks | record_blocks
    payload = {
        "schema_version": "1.1",
        "document_id": page.get("document_id"),
        "page_number": page_number,
        "page_role": "cover",
        "source_image": page.get("image_path"),
        "fields": fields,
        "source_labels": source_labels,
        "layout_strategy": {"cover_fields": cover_strategy},
        "protection_records": records,
        "skipped_sections": ["protection_principle_table"],
        "table_grid": table_grid,
        "unassigned_blocks": [block for block in source_blocks if str(block["block_id"]) not in assigned],
        "warnings": warnings,
        "summary": {"ocr_blocks": len(source_blocks), "fields": len(fields), "protection_records": len(records), "unassigned_blocks": sum(str(block["block_id"]) not in assigned for block in source_blocks)},
    }
    registry = field_rule_registry or load_field_rule_registry()
    payload["field_resolution"] = Page1FieldResolutionEngine(
        registry,
        relationship_policy,
    ).integrate(payload, source_blocks, table_grid)
    return payload
