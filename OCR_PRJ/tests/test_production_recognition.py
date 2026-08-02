"""Tests for the VietOCR production service contract without loading a model."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.recognition.service import PageRecognitionResult, RecognisedRegion, VietnameseRecognitionService  # noqa: E402


class ProductionRecognitionTests(unittest.TestCase):
    def test_accepts_detection_json_shape(self) -> None:
        polygon, score = VietnameseRecognitionService._detection_fields({
            "polygon": [[1, 2], [3, 2], [3, 4], [1, 4]],
            "score": 0.87,
        })
        self.assertEqual(polygon, [[1.0, 2.0], [3.0, 2.0], [3.0, 4.0], [1.0, 4.0]])
        self.assertEqual(score, 0.87)

    def test_result_serialises_for_the_ocr_job(self) -> None:
        result = PageRecognitionResult(
            regions=[RecognisedRegion(0, [[1.0, 2.0]], 0.9, "Không theo phiếu", 0.95)],
            recognizer_version="vietocr_vgg_transformer",
            elapsed_ms=12.5,
        )
        payload = result.as_dict()
        self.assertEqual(payload["regions"][0]["text"], "Không theo phiếu")
        self.assertEqual(payload["recognizer_version"], "vietocr_vgg_transformer")


if __name__ == "__main__":
    unittest.main()
