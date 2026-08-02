"""OCR lại các ô bị block OCR cũ cắt qua biên lưới.

Detector chạy trên ảnh đã giảm watermark, còn recognizer luôn đọc crop từ ảnh gốc.
Model chỉ được nạp khi thực sự có ô cần OCR lại.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _bbox(block: dict[str, Any]) -> list[float]:
    return [float(value) for value in block["bbox_pixel"]]


def _intersection(box: list[float], cell: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = box
    cx1, cy1, cx2, cy2 = cell
    return max(0.0, min(x2, cx2) - max(x1, cx1)) * max(0.0, min(y2, cy2) - max(y1, cy1))


def cells_requiring_reocr(page: dict[str, Any], table_grid: dict[str, Any]) -> list[dict[str, Any]]:
    """Lập kế hoạch OCR ô, không nạp model và có thể unit test độc lập."""

    blocks = [block for block in page.get("block_predictions", []) if str(block.get("text", "")).strip()]
    planned: dict[str, dict[str, Any]] = {}
    for region in table_grid.get("regions", []):
        left, top, right, bottom = [float(value) for value in region["bbox"]]
        verticals = [float(value) for value in region["vertical_lines"]]
        bands = [[float(value) for value in band] for band in region["row_bands"]]
        relevant = [
            block for block in blocks
            if left <= (_bbox(block)[0] + _bbox(block)[2]) / 2 <= right
            and max(0.0, min(_bbox(block)[3], bottom) - max(_bbox(block)[1], top)) > 0
        ]
        row_members: list[list[dict[str, Any]]] = [[] for _ in bands]
        for block in relevant:
            box = _bbox(block)
            overlaps = [max(0.0, min(box[3], band[1]) - max(box[1], band[0])) for band in bands]
            if overlaps and max(overlaps) > 0:
                row_members[max(range(len(overlaps)), key=overlaps.__getitem__)].append(block)

        for assigned_row, members in enumerate(row_members):
            # Một tiêu đề nhóm đơn lẻ thường cố ý trải nhiều cột, không phải lỗi OCR.
            if len(members) < 2:
                continue
            for block in members:
                bx1, by1, bx2, by2 = _bbox(block)
                block_width = max(1.0, bx2 - bx1)
                block_height = max(1.0, by2 - by1)
                crosses_vertical = any(
                    min(x - bx1, bx2 - x) >= max(4.0, block_width * 0.22)
                    for x in verticals[1:-1] if bx1 < x < bx2
                )
                horizontal_hits = []
                for index, (band_top, band_bottom) in enumerate(bands):
                    overlap = max(0.0, min(by2, band_bottom) - max(by1, band_top))
                    if overlap >= max(4.0, block_height * 0.22):
                        horizontal_hits.append(index)
                crosses_horizontal = len(horizontal_hits) > 1
                if not crosses_vertical and not crosses_horizontal:
                    continue
                candidate_rows = horizontal_hits if crosses_horizontal else [assigned_row]
                for row_index in candidate_rows:
                    band_top, band_bottom = bands[row_index]
                    for column_index, (cell_left, cell_right) in enumerate(zip(verticals, verticals[1:])):
                        cell = (cell_left, band_top, cell_right, band_bottom)
                        if _intersection([bx1, by1, bx2, by2], cell) <= 4:
                            continue
                        key = f"{region['region_id']}:{row_index}:{column_index}"
                        planned[key] = {
                            "key": key,
                            "region_id": region["region_id"],
                            "row_index": row_index,
                            "column_index": column_index,
                            "bbox": [round(value) for value in cell],
                            "trigger_block_ids": sorted({
                                *planned.get(key, {}).get("trigger_block_ids", []),
                                str(block["block_id"]),
                            }),
                        }
    return list(planned.values())


class CellOCRService:
    """Tái sử dụng detector PP-OCR và VietOCR production cho crop từng ô."""

    def __init__(self, use_gpu: bool = False) -> None:
        from src.detection.pp_ocr import PPTextDetector
        from src.recognition.vietocr import VietOCRRecognizer

        self.detector = PPTextDetector(use_gpu=use_gpu)
        self.recognizer = VietOCRRecognizer(use_gpu=use_gpu)

    def run(
        self,
        image_path: str | Path,
        plans: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        import cv2

        from src.detection.preprocessing import load_detection_image
        from src.recognition.crop import crop_polygon

        original = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if original is None:
            raise ValueError(f"Không đọc được ảnh gốc: {image_path}")
        prepared, preprocessing = load_detection_image(Path(image_path))
        results: dict[str, dict[str, Any]] = {}
        for plan in plans:
            x1, y1, x2, y2 = plan["bbox"]
            x1, y1 = max(0, x1 + 2), max(0, y1 + 2)
            x2, y2 = min(original.shape[1], x2 - 2), min(original.shape[0], y2 - 2)
            if x2 - x1 < 8 or y2 - y1 < 8:
                continue
            detected = self.detector.detect(prepared[y1:y2, x1:x2])
            recognised = []
            for detection in detected:
                if detection.score is not None and detection.score < 0.25:
                    continue
                crop = crop_polygon(original[y1:y2, x1:x2], detection.polygon)
                prediction = self.recognizer.recognise(crop)
                text = " ".join(prediction.text.split())
                if text:
                    recognised.append({
                        "text": text,
                        "score": prediction.score,
                        "polygon": detection.polygon,
                        "top": min(point[1] for point in detection.polygon),
                        "left": min(point[0] for point in detection.polygon),
                    })
            recognised.sort(key=lambda item: (round(item["top"] / 8), item["left"]))
            if recognised:
                results[plan["key"]] = {
                    "text": " ".join(item["text"] for item in recognised),
                    "confidence": sum(item["score"] for item in recognised) / len(recognised),
                    "source": "cell_reocr_original_image",
                    "cell_bbox": plan["bbox"],
                    "trigger_block_ids": plan["trigger_block_ids"],
                    "preprocessing": preprocessing,
                }
        return results
