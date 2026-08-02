"""Vietnamese text recognition for regions found by the detection service."""

from .service import PageRecognitionResult, RecognisedRegion, VietnameseRecognitionService
from .vietocr import VietOCRRecognizer

__all__ = [
    "PageRecognitionResult",
    "RecognisedRegion",
    "VietnameseRecognitionService",
    "VietOCRRecognizer",
]
