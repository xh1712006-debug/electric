"""Geometry- and pattern-based pagination detection shared by page roles."""

from __future__ import annotations

import re
from typing import Any, Iterable


# Labels are intentionally absent: they may be Vietnamese, English, another
# language, or organisation-specific wording unknown at development time.
PAGE_REFERENCE_PATTERN = re.compile(
    r"(?<![\w./-])(\d{1,3})\s*/\s*(\d{1,3})(?![\d/])",
    re.UNICODE,
)
TICKET_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]*-\d{1,3}-\d{4}/[A-Z0-9.]+/\d+\b", re.IGNORECASE)


def _text(block: dict[str, Any]) -> str:
    return " ".join(str(block.get("text", "")).split())


def _bbox(block: dict[str, Any]) -> list[float]:
    return [float(value) for value in block["bbox_pixel"]]


def _confidence(block: dict[str, Any]) -> float:
    for key in ("recognition_score", "confidence", "detection_score"):
        value = block.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def _overlap(first: tuple[float, float], second: tuple[float, float]) -> float:
    intersection = max(0.0, min(first[1], second[1]) - max(first[0], second[0]))
    shortest = max(1.0, min(first[1] - first[0], second[1] - second[0]))
    return intersection / shortest


def _clean_label(text: str) -> str | None:
    label = text.strip().rstrip(":：.- ")
    if not label or label.isdigit() or TICKET_PATTERN.search(label):
        return None
    return label


def _left_label(
    value_block: dict[str, Any],
    header_blocks: list[dict[str, Any]],
    page_right: float,
) -> tuple[str | None, dict[str, Any] | None]:
    vx1, vy1, _, vy2 = _bbox(value_block)
    candidates: list[tuple[float, dict[str, Any], str]] = []
    for block in header_blocks:
        if block is value_block:
            continue
        _, y1, x2, y2 = _bbox(block)
        label = _clean_label(_text(block))
        gap = vx1 - x2
        if (
            label
            and -20.0 <= gap <= page_right * 0.22
            and _overlap((vy1, vy2), (y1, y2)) >= 0.25
            and not PAGE_REFERENCE_PATTERN.search(_text(block))
        ):
            candidates.append((abs(gap), block, label))
    if not candidates:
        return None, None
    _, block, label = min(candidates, key=lambda item: item[0])
    return label, block


def detect_page_reference(
    blocks: Iterable[dict[str, Any]],
    *,
    expected_page_number: int | None = None,
    page_width: float | None = None,
    page_height: float | None = None,
) -> dict[str, Any] | None:
    """Detect header pagination without knowing the label vocabulary.

    A complete ``x/y`` value is authoritative. If OCR only preserves ``x``,
    geometry relative to the ticket row and an arbitrary neighbouring label is
    used, while ``total_pages`` remains unknown.
    """

    source = [block for block in blocks if _text(block) and block.get("bbox_pixel")]
    if not source:
        return None
    page_bottom = float(page_height) if page_height is not None else max(_bbox(block)[3] for block in source)
    page_right = float(page_width) if page_width is not None else max(_bbox(block)[2] for block in source)
    # OCR-only unit callers may provide just a header crop rather than a full
    # portrait page. In that case every supplied block belongs to the header.
    header_limit = (
        page_bottom * 0.22
        if page_height is not None
        else page_bottom if page_bottom <= page_right * 0.5 else page_bottom * 0.22
    )
    header_blocks = [block for block in source if _bbox(block)[1] <= header_limit]
    tickets = [block for block in header_blocks if TICKET_PATTERN.search(_text(block))]
    ticket_row_tolerance = max(40.0, page_bottom * 0.08)

    complete: list[tuple[float, dict[str, Any]]] = []
    for block in header_blocks:
        if TICKET_PATTERN.search(_text(block)):
            continue
        text = _text(block)
        for match in PAGE_REFERENCE_PATTERN.finditer(text):
            current, total = int(match.group(1)), int(match.group(2))
            if current < 1 or total < current:
                continue
            if expected_page_number is not None and current != expected_page_number:
                continue
            x1, y1, x2, _ = _bbox(block)
            if (x1 + x2) / 2 < page_right * 0.52:
                continue
            ticket_context = any(
                y1 >= _bbox(ticket)[1]
                and y1 - _bbox(ticket)[3] <= ticket_row_tolerance
                and abs(x1 - _bbox(ticket)[0]) <= page_right * 0.18
                for ticket in tickets
            )
            if tickets and not ticket_context:
                continue
            inline_label = _clean_label(text[:match.start()])
            label, label_block = (inline_label, None) if inline_label else _left_label(block, header_blocks, page_right)
            source_blocks = [block] if label_block is None else [label_block, block]
            evidence = {
                "text": f"{current}/{total}",
                "page_number": current,
                "total_pages": total,
                "matched_label": label,
                "source_blocks": source_blocks,
                "value_block": block,
            }
            score = (
                _confidence(block)
                + (0.3 if label else 0.0)
                + (0.2 if ticket_context else 0.0)
                + (x1 + x2) / max(1.0, 2 * page_right)
                + (1.0 - y1 / max(1.0, page_bottom)) * 0.5
            )
            complete.append((score, evidence))
    if complete:
        return max(complete, key=lambda item: item[0])[1]

    standalone: list[tuple[float, dict[str, Any]]] = []
    for block in header_blocks:
        text = _text(block).strip()
        if not re.fullmatch(r"\d{1,3}", text):
            continue
        current = int(text)
        if current < 1 or (expected_page_number is not None and current != expected_page_number):
            continue
        x1, y1, x2, _ = _bbox(block)
        if (x1 + x2) / 2 < page_right * 0.52:
            continue
        label, label_block = _left_label(block, header_blocks, page_right)
        ticket_context = any(
            y1 >= _bbox(ticket)[1]
            and y1 - _bbox(ticket)[3] <= ticket_row_tolerance
            and abs(x1 - _bbox(ticket)[0]) <= page_right * 0.18
            for ticket in tickets
        )
        if not ticket_context:
            continue
        source_blocks = [block] if label_block is None else [label_block, block]
        evidence = {
            "text": str(current),
            "page_number": current,
            "total_pages": None,
            "matched_label": label,
            "source_blocks": source_blocks,
            "value_block": block,
        }
        score = _confidence(block) + (0.3 if label else 0.0) + (0.2 if ticket_context else 0.0)
        standalone.append((score, evidence))
    return max(standalone, key=lambda item: item[0])[1] if standalone else None
