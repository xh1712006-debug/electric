"""Perspective crops from original source pages using detector polygons."""

from __future__ import annotations

from typing import Any


def crop_polygon(image: Any, polygon: list[list[float]], padding: int = 2) -> Any:
    """Rectify one detector quadrilateral from the untouched original image."""
    import cv2
    import numpy as np

    if len(polygon) != 4:
        raise ValueError(f"Expected a quadrilateral detector polygon, got {len(polygon)} points")
    points = np.asarray(polygon, dtype=np.float32)
    ordered = order_quad(points)
    width = max(1, int(round(max(np.linalg.norm(ordered[1] - ordered[0]), np.linalg.norm(ordered[2] - ordered[3])))))
    height = max(1, int(round(max(np.linalg.norm(ordered[3] - ordered[0]), np.linalg.norm(ordered[2] - ordered[1])))))
    destination = np.array(
        [[padding, padding], [width + padding - 1, padding], [width + padding - 1, height + padding - 1], [padding, height + padding - 1]],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(ordered, destination)
    crop = cv2.warpPerspective(
        image,
        transform,
        (width + padding * 2, height + padding * 2),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    # VietOCR recognises horizontal text lines; preserve the original page for
    # the crop, then turn a tall region into a horizontal line image.
    return cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE) if crop.shape[0] > crop.shape[1] else crop


def order_quad(points: Any) -> Any:
    """Order points as top-left, top-right, bottom-right, bottom-left."""
    import numpy as np

    if getattr(points, "shape", None) != (4, 2):
        raise ValueError("A quadrilateral must have shape (4, 2)")
    ordered = np.empty((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    ordered[0] = points[np.argmin(sums)]
    ordered[2] = points[np.argmax(sums)]
    ordered[1] = points[np.argmin(differences)]
    ordered[3] = points[np.argmax(differences)]
    return ordered
