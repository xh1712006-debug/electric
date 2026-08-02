"""Visual audit output for inferred roles, records, and grouping links."""

from __future__ import annotations

from pathlib import Path
from typing import Any


ROLE_COLORS = {
    "section_heading": (255, 140, 0),
    "parameter_code": (180, 0, 255),
    "parameter_name": (0, 160, 255),
    "parameter_value": (0, 190, 0),
    "continuation_line": (255, 80, 80),
    "unassigned": (160, 160, 160),
}


def image_line_evidence(image: Any) -> dict[str, float]:
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, image.shape[1] // 35), 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(15, image.shape[0] // 45)))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)
    pixels = float(image.shape[0] * image.shape[1])
    return {
        "horizontal_density": float(np.count_nonzero(horizontal)) / pixels,
        "vertical_density": float(np.count_nonzero(vertical)) / pixels,
    }


def write_visualization(image_path: Path, blocks: list[dict[str, Any]], records: list[dict[str, Any]], destination: Path) -> None:
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    source = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if source is None:
        raise RuntimeError(f"Could not read source image for visualization: {image_path}")
    canvas = cv2.cvtColor(source, cv2.COLOR_BGR2RGB)
    by_id = {block["id"]: block for block in blocks}
    for record in records:
        members = [by_id[block_id] for block_id in record["block_ids"] if block_id in by_id]
        for left, right in zip(members, members[1:]):
            start = tuple(int(value) for value in left["center_normalized"])
            end = tuple(int(value) for value in right["center_normalized"])
            start = (int(start[0] * source.shape[1]), int(start[1] * source.shape[0]))
            end = (int(end[0] * source.shape[1]), int(end[1] * source.shape[0]))
            cv2.line(canvas, start, end, (255, 0, 180), 2, cv2.LINE_AA)
    for block in blocks:
        points = np.asarray(block["polygon"], dtype=np.int32).reshape((-1, 1, 2))
        color = ROLE_COLORS.get(block["semantic_role"], ROLE_COLORS["unassigned"])
        cv2.polylines(canvas, [points], True, color, 2, cv2.LINE_AA)

    image = Image.fromarray(canvas).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", max(12, min(20, image.width // 110)))
    except OSError:
        font = ImageFont.load_default()
    for block in blocks:
        x, y = int(block["bbox"][0]), int(block["bbox"][1])
        record = block["record_id"] or "-"
        role = block["semantic_role"]
        label = f"{block['id']} {record} {role}: {block['text'][:38]}"
        box = draw.textbbox((x, y), label, font=font)
        label_y = max(0, y - (box[3] - box[1] + 4))
        draw.rectangle((x, label_y, min(image.width, x + box[2] - box[0] + 6), label_y + box[3] - box[1] + 4), fill=(0, 0, 0, 185))
        draw.text((x + 3, label_y + 1), label, font=font, fill=(255, 255, 0, 255))
    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(image, overlay).convert("RGB").save(destination)
