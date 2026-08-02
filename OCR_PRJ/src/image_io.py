"""Unicode-safe OpenCV image file IO.

OpenCV's ``imread``/``imwrite`` on Windows may fail for paths containing
Vietnamese or other non-ASCII characters. Decode/encode bytes in Python so
every production OCR stage can work with the original document name.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def read_image(path: Path | str, flags: int) -> Any:
    """Read an image with OpenCV while supporting Unicode filesystem paths."""

    import cv2
    import numpy as np

    source = Path(path)
    try:
        encoded = np.frombuffer(source.read_bytes(), dtype=np.uint8)
    except OSError as exc:
        raise ValueError(f"Cannot read image bytes: {source}") from exc
    image = cv2.imdecode(encoded, flags)
    if image is None:
        raise ValueError(f"OpenCV could not decode image: {source}")
    return image


def write_image(path: Path | str, image: Any) -> Path:
    """Write an OpenCV image while supporting Unicode filesystem paths."""

    import cv2

    destination = Path(path)
    extension = destination.suffix.lower() or ".png"
    success, encoded = cv2.imencode(extension, image)
    if not success:
        raise ValueError(f"OpenCV could not encode image for: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encoded.tobytes())
    return destination
