"""Deterministic preparation of PDF-rendered pages for text detection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.image_io import read_image


def suppress_gray_watermark(gray: Any) -> tuple[Any, dict[str, int]]:
    """Keep dark ink while removing a light-gray watermark on an even white page.

    The first Otsu threshold separates white paper from marks. A second Otsu
    threshold, calculated only from those marks, separates black ink from the
    gray watermark. Their midpoint is chosen independently for every page.
    """
    import cv2
    import numpy as np

    paper_threshold, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    foreground = gray[gray <= paper_threshold]
    if foreground.size == 0:
        return np.full_like(gray, 255), {
            "paper_threshold": int(paper_threshold),
            "ink_threshold": 0,
            "selected_threshold": 0,
        }

    ink_threshold, _ = cv2.threshold(foreground, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    selected_threshold = int(round((float(ink_threshold) + float(paper_threshold)) / 2))
    binary = np.where(gray <= selected_threshold, 0, 255).astype(np.uint8)
    return binary, {
        "paper_threshold": int(paper_threshold),
        "ink_threshold": int(ink_threshold),
        "selected_threshold": selected_threshold,
    }


def detect_red_stamp_mask(image: Any) -> tuple[Any, dict[str, int]]:
    """Tìm vùng mực đỏ của con dấu mà không thay đổi ảnh gốc.

    Hai dải hue bao quanh điểm quấn đỏ của HSV được dùng để nhận cả đỏ cam và
    đỏ sẫm. Chỉ những cụm mực có diện tích đủ lớn mới được xem là con dấu;
    nét bút đỏ đơn lẻ sẽ không vô tình bị xóa khỏi đầu vào OCR.
    """
    import cv2
    import numpy as np

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    # Một số dấu scan rất nhạt nên saturation có thể thấp. Điều kiện R trội
    # hơn G/B ngăn các vùng xám có hue ngẫu nhiên bị nhận nhầm là đỏ.
    lower_red = cv2.inRange(hsv, np.array([0, 12, 35]), np.array([15, 255, 255]))
    upper_red = cv2.inRange(hsv, np.array([165, 12, 35]), np.array([180, 255, 255]))
    hue_mask = cv2.bitwise_or(lower_red, upper_red)
    blue, green, red = cv2.split(image)
    red_dominant = (
        (red.astype(np.int16) - green.astype(np.int16) >= 12)
        & (red.astype(np.int16) - blue.astype(np.int16) >= 12)
    ).astype(np.uint8) * 255
    raw_mask = cv2.bitwise_and(hue_mask, red_dominant)
    height, width = raw_mask.shape
    support = cv2.morphologyEx(
        raw_mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)),
    )
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(support, connectivity=8)
    minimum_area = max(80, int(height * width * 0.00004))
    accepted_labels = [
        index for index in range(1, component_count)
        if int(stats[index, cv2.CC_STAT_AREA]) >= minimum_area
    ]
    accepted_support = np.isin(labels, accepted_labels).astype(np.uint8) * 255
    # Giữ màu đỏ thật, rồi nới rất nhẹ để loại nét biên anti-aliasing của dấu.
    stamp_mask = cv2.bitwise_and(raw_mask, accepted_support)
    if accepted_labels:
        stamp_mask = cv2.dilate(
            stamp_mask,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
            iterations=1,
        )
    return stamp_mask, {
        "red_pixel_count": int(cv2.countNonZero(stamp_mask)),
        "red_component_count": len(accepted_labels),
        "red_component_min_area_px": minimum_area,
    }


def encode_mask_rle(mask: Any) -> dict[str, Any]:
    """Mã hóa mask nhị phân theo run-length để lưu cùng OCR job khi cần review."""
    import numpy as np

    active = (mask > 0).astype(np.uint8).reshape(-1)
    padded = np.concatenate(([0], active, [0]))
    transitions = np.flatnonzero(padded[1:] != padded[:-1])
    runs = [
        [int(start), int(end - start)]
        for start, end in zip(transitions[0::2], transitions[1::2])
    ]
    return {"shape": [int(mask.shape[0]), int(mask.shape[1])], "runs": runs}


def prepare_detection_image(image: Any) -> tuple[Any, Any, dict[str, Any]]:
    """Tạo ảnh dẫn xuất cho detector cùng mask dấu đỏ có thể truy vết."""
    import cv2

    stamp_mask, stamp_metadata = detect_red_stamp_mask(image)
    without_stamp = image.copy()
    without_stamp[stamp_mask > 0] = (255, 255, 255)
    gray = cv2.cvtColor(without_stamp, cv2.COLOR_BGR2GRAY)
    binary, watermark_metadata = suppress_gray_watermark(gray)
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR), stamp_mask, {
        **watermark_metadata,
        "red_stamp": stamp_metadata,
        "red_stamp_mask_rle": encode_mask_rle(stamp_mask),
    }


def load_detection_input(image_path: Path) -> tuple[Any, Any, dict[str, Any]]:
    """Đọc trang gốc và trả ảnh detector, mask dấu đỏ và metadata."""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for detection preprocessing.") from exc

    image = read_image(image_path, cv2.IMREAD_COLOR)
    return prepare_detection_image(image)


def load_detection_image(image_path: Path) -> tuple[Any, dict[str, Any]]:
    """Read a page and return the watermark-suppressed BGR image for PP-OCR.

    This function never changes the source image. Persist the returned metadata
    with the OCR job so a reviewer can trace how the detector input was made.
    """
    prepared, _, metadata = load_detection_input(image_path)
    # Đây là API cũ được recognition/lab gọi lặp trên crop; không lặp RLE mask
    # lớn vào từng payload crop. Detection service vẫn nhận đầy đủ RLE.
    metadata = {key: value for key, value in metadata.items() if key != "red_stamp_mask_rle"}
    return prepared, metadata
