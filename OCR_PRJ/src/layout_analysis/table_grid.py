"""Phát hiện đường kẻ ngang/dọc của bảng trực tiếp từ ảnh gốc."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from src.image_io import read_image, write_image


def _line_positions(projection: np.ndarray, minimum_length: float) -> list[tuple[int, int]]:
    """Chuyển projection của mask đường kẻ thành tâm và độ dài cụm đường."""

    active = projection >= minimum_length
    positions: list[tuple[int, int]] = []
    start: int | None = None
    for index, enabled in enumerate(active.tolist() + [False]):
        if enabled and start is None:
            start = index
        elif not enabled and start is not None:
            positions.append(((start + index - 1) // 2, int(projection[start:index].max())))
            start = None
    return positions


def _merge_nearby(values: list[int], tolerance: int = 12) -> list[int]:
    merged: list[list[int]] = []
    for value in sorted(values):
        if merged and value - round(sum(merged[-1]) / len(merged[-1])) <= tolerance:
            merged[-1].append(value)
        else:
            merged.append([value])
    return [round(sum(group) / len(group)) for group in merged]


def _candidate_regions(grid_mask: np.ndarray, width: int, height: int) -> list[tuple[int, int, int, int]]:
    """Tìm từng thành phần lưới liên thông thay vì coi cả trang là một bảng."""

    count, _, stats, _ = cv2.connectedComponentsWithStats((grid_mask > 0).astype(np.uint8), 8)
    candidates: list[tuple[int, int, int, int]] = []
    for index in range(1, count):
        x, y, w, h, area = [int(value) for value in stats[index]]
        touches_page_edge = x <= width * 0.03 or x + w >= width * 0.97
        if touches_page_edge and h >= height * 0.80:
            continue
        if w >= width * 0.35 and h >= height * 0.08 and area >= max(500, (w + h) * 0.3):
            candidates.append((x, y, x + w - 1, y + h - 1))
    candidates.sort(key=lambda box: (box[1], box[0]))
    return candidates


def _hough_table_regions(binary: np.ndarray, width: int, height: int) -> list[dict[str, Any]]:
    """Recover ruled tables whose scan skew breaks morphology connectivity.

    The fallback uses only long ruling-line geometry.  It does not inspect OCR
    text or assume any field label, which keeps table ownership independent of
    wording changes.
    """

    detected = cv2.HoughLinesP(
        binary,
        1,
        np.pi / 1800,
        threshold=max(50, width // 20),
        minLineLength=max(120, width // 8),
        maxLineGap=max(20, width // 45),
    )
    if detected is None:
        return []

    horizontal_segments: list[tuple[int, int, int]] = []
    vertical_segments: list[tuple[int, int, int]] = []
    for x1, y1, x2, y2 in detected[:, 0]:
        dx, dy = int(x2) - int(x1), int(y2) - int(y1)
        if abs(dx) >= width * 0.25 and abs(dy) <= max(4, abs(dx) * 0.035):
            horizontal_segments.append((round((int(y1) + int(y2)) / 2), min(int(x1), int(x2)), max(int(x1), int(x2))))
        if abs(dy) >= height * 0.07 and abs(dx) <= max(4, abs(dy) * 0.035):
            vertical_segments.append((round((int(x1) + int(x2)) / 2), min(int(y1), int(y2)), max(int(y1), int(y2))))

    candidates: list[dict[str, Any]] = []
    for left in vertical_segments:
        for right in vertical_segments:
            x1, x2 = left[0], right[0]
            if x2 - x1 < width * 0.35:
                continue
            overlap_top = max(left[1], right[1])
            overlap_bottom = min(left[2], right[2])
            if overlap_bottom - overlap_top < height * 0.08:
                continue
            # A stamp or weak scan can interrupt one outer border earlier than
            # the other.  Once the two borders overlap substantially, use
            # their combined vertical span to recover the remaining rows.
            span_top = min(left[1], right[1])
            span_bottom = max(left[2], right[2])
            table_width = x2 - x1
            line_y = [
                y
                for y, start_x, end_x in horizontal_segments
                if span_top - 20 <= y <= span_bottom + 20
                and start_x <= x1 + table_width * 0.09
                and end_x >= x2 - table_width * 0.09
            ]
            horizontal_lines = _merge_nearby(line_y, tolerance=max(8, height // 250))
            if len(horizontal_lines) < 3:
                continue
            top, bottom = horizontal_lines[0], horizontal_lines[-1]
            row_bands = [
                [row_top, row_bottom]
                for row_top, row_bottom in zip(horizontal_lines, horizontal_lines[1:])
                if row_bottom - row_top >= 8
            ]
            if len(row_bands) < 2:
                continue
            local_verticals = _merge_nearby([
                x
                for x, start_y, end_y in vertical_segments
                if x1 <= x <= x2
                and min(end_y, bottom) - max(start_y, top) >= (bottom - top) * 0.12
            ])
            local_verticals = _merge_nearby([x1, *local_verticals, x2])
            candidates.append({
                "bbox": [x1, top, x2, bottom],
                "vertical_lines": local_verticals,
                "horizontal_lines": horizontal_lines,
                "column_centres": [
                    round((a + b) / 2, 2)
                    for a, b in zip(local_verticals, local_verticals[1:])
                    if b - a >= table_width * 0.035
                ],
                "row_bands": row_bands,
            })

    # Many Hough segments describe the same outer border. Keep the widest
    # candidate for each strongly-overlapping vertical span.
    selected: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: (item["bbox"][1], -(item["bbox"][2] - item["bbox"][0]))):
        box = candidate["bbox"]
        duplicate = next((
            current for current in selected
            if abs(current["bbox"][1] - box[1]) <= 18 and abs(current["bbox"][3] - box[3]) <= 18
        ), None)
        if duplicate is None:
            selected.append(candidate)
        elif box[2] - box[0] > duplicate["bbox"][2] - duplicate["bbox"][0]:
            selected[selected.index(duplicate)] = candidate
    selected.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
    for index, region in enumerate(selected, start=1):
        region["region_id"] = f"table_{index:02d}"
    return selected


def _region_grid(
    horizontal: np.ndarray,
    vertical: np.ndarray,
    box: tuple[int, int, int, int],
    region_id: str,
) -> dict[str, Any] | None:
    x1, y1, x2, y2 = box
    region_width = max(1, x2 - x1 + 1)
    region_height = max(1, y2 - y1 + 1)
    horizontal_projection = (horizontal[y1:y2 + 1, x1:x2 + 1] > 0).sum(axis=1)
    vertical_projection = (vertical[y1:y2 + 1, x1:x2 + 1] > 0).sum(axis=0)
    horizontal_lines = _merge_nearby([
        y1 + position for position, _ in _line_positions(horizontal_projection, max(region_width * 0.35, 80))
    ])
    vertical_lines = _merge_nearby([
        x1 + position for position, _ in _line_positions(vertical_projection, max(region_height * 0.12, 35))
    ])
    # Cạnh ngoài thường rõ trên mask tổng nhưng có thể yếu ở projection cục bộ.
    vertical_lines = _merge_nearby([x1, *vertical_lines, x2])
    horizontal_lines = _merge_nearby([y1, *horizontal_lines, y2])
    column_centres = [
        round((left + right) / 2, 2)
        for left, right in zip(vertical_lines, vertical_lines[1:])
        if right - left >= region_width * 0.035
    ]
    row_bands = [
        [top, bottom]
        for top, bottom in zip(horizontal_lines, horizontal_lines[1:])
        if bottom - top >= 8
    ]
    if len(column_centres) < 2 or len(row_bands) < 2:
        return None
    return {
        "region_id": region_id,
        "bbox": [x1, y1, x2, y2],
        "vertical_lines": vertical_lines,
        "horizontal_lines": horizontal_lines,
        "column_centres": column_centres,
        "row_bands": row_bands,
    }


def detect_table_grid(image_path: str | Path, overlay_path: str | Path | None = None) -> dict[str, Any]:
    """Tìm lưới bảng bằng morphology, không cần biết trước mẫu phiếu.

    Chỉ trả lưới khi có ít nhất ba vùng cột (bốn đường dọc) và các đường có
    độ dài đủ lớn. Với trang không có viền như 7SJ622, caller sẽ dùng lại OCR
    geometry thay vì ép nó vào bảng.
    """

    path = Path(image_path)
    try:
        image = read_image(path, cv2.IMREAD_GRAYSCALE)
    except ValueError:
        return {"available": False, "reason": "không đọc được ảnh", "vertical_lines": [], "horizontal_lines": [], "column_centres": []}
    height, width = image.shape
    fixed = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    adaptive = cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 12)
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(35, width // 35), 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(35, height // 45)))
    horizontal = cv2.bitwise_or(
        cv2.morphologyEx(fixed, cv2.MORPH_OPEN, horizontal_kernel),
        cv2.morphologyEx(adaptive, cv2.MORPH_OPEN, horizontal_kernel),
    )
    vertical = cv2.bitwise_or(
        cv2.morphologyEx(fixed, cv2.MORPH_OPEN, vertical_kernel),
        cv2.morphologyEx(adaptive, cv2.MORPH_OPEN, vertical_kernel),
    )
    # Keep strong page-wide ruling evidence even when broken intersections mean
    # no complete connected table region can be reconstructed. Page-1 field
    # ownership still needs these horizontal cell boundaries.
    page_horizontal_lines = _merge_nearby([
        position for position, _ in _line_positions(
            (horizontal > 0).sum(axis=1), max(width * 0.18, 120)
        )
    ])
    page_vertical_lines = _merge_nearby([
        position for position, _ in _line_positions(
            (vertical > 0).sum(axis=0), max(height * 0.04, 80)
        )
    ])
    # Nối các khe rất nhỏ tại giao điểm, nhưng không nối hai bảng cách nhau.
    grid_mask = cv2.morphologyEx(cv2.bitwise_or(horizontal, vertical), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    regions: list[dict[str, Any]] = []
    for index, box in enumerate(_candidate_regions(grid_mask, width, height), start=1):
        region = _region_grid(horizontal, vertical, box, f"table_{index:02d}")
        if region:
            regions.append(region)
    method = "connected_table_regions_with_local_ruling_lines"
    if not regions:
        regions = _hough_table_regions(fixed, width, height)
        if regions:
            method = "skew_tolerant_hough_ruling_lines"
    available = bool(regions)
    vertical_lines = _merge_nearby([x for region in regions for x in region["vertical_lines"]])
    horizontal_lines = _merge_nearby([y for region in regions for y in region["horizontal_lines"]])
    columns = regions[0]["column_centres"] if len(regions) == 1 else []
    result = {
        "available": available,
        "image_width": width,
        "image_height": height,
        "vertical_lines": vertical_lines,
        "horizontal_lines": horizontal_lines,
        "column_centres": columns,
        "regions": regions,
        "page_horizontal_lines": page_horizontal_lines,
        "page_vertical_lines": page_vertical_lines,
        "method": method,
    }
    if overlay_path:
        overlay = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        for region in regions:
            x1, y1, x2, y2 = region["bbox"]
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 180, 0), 4)
            for x in region["vertical_lines"]:
                cv2.line(overlay, (x, y1), (x, y2), (0, 0, 255), 2)
            for y in region["horizontal_lines"]:
                cv2.line(overlay, (x1, y), (x2, y), (255, 0, 0), 2)
        destination = Path(overlay_path)
        write_image(destination, overlay)
        result["overlay_path"] = str(destination)
    return result
