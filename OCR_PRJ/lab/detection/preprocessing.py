"""Non-destructive image variants for text-detection experiments."""

from __future__ import annotations

from pathlib import Path
from typing import Any


PREPROCESSORS = ("original", "clahe", "adaptive_threshold")


def watermark_suppression(gray: Any) -> tuple[Any, dict[str, int]]:
    """Separate black ink from gray watermark using two-stage global Otsu.

    Rendered PDFs have an even white background, so local/adaptive thresholding
    tends to preserve the diagonal watermark. The first Otsu split separates
    paper from all non-paper marks; a second split within those marks separates
    dark ink from light-gray watermark. The midpoint is selected automatically
    per page, preserving an anti-aliasing margin around printed black text.
    """
    import cv2
    import numpy as np

    paper_threshold, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    foreground = gray[gray <= paper_threshold]
    if foreground.size == 0:
        return np.full_like(gray, 255), {"paper_threshold": int(paper_threshold), "ink_threshold": 0, "selected_threshold": 0}
    ink_threshold, _ = cv2.threshold(foreground, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    selected_threshold = int(round((float(ink_threshold) + float(paper_threshold)) / 2))
    binary = np.where(gray <= selected_threshold, 0, 255).astype(np.uint8)
    return binary, {
        "paper_threshold": int(paper_threshold),
        "ink_threshold": int(ink_threshold),
        "selected_threshold": selected_threshold,
    }


def load_and_preprocess(image_path: Path, method: str, include_metadata: bool = False) -> Any:
    """Return a BGR image variant suitable for a detector; never alters input."""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for preprocessing.") from exc

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"OpenCV could not read {image_path}")
    if method == "original":
        return (image, {}) if include_metadata else image

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if method == "clahe":
        # Local contrast enhancement keeps dark text strong without globally
        # whitening pale stamps or subtle character strokes.
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        result = cv2.cvtColor(clahe.apply(gray), cv2.COLOR_GRAY2BGR)
        return (result, {"clip_limit": 2, "tile_grid": 8}) if include_metadata else result
    if method == "adaptive_threshold":
        binary, metadata = watermark_suppression(gray)
        result = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        return (result, metadata) if include_metadata else result
    raise ValueError(f"Unknown preprocessing method: {method}. Available: {', '.join(PREPROCESSORS)}")


def write_image(destination: Path, image: Any) -> None:
    """Write a generated image, creating only its output parent directories."""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for preprocessing.") from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(destination), image):
        raise RuntimeError(f"Could not write {destination}")
