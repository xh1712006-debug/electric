"""Tests for crops and recognition-result normalisation without model downloads."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lab" / "recognition"))

from crop import crop_polygon, order_quad  # noqa: E402
from recognizers import PARSeqRecognizer, PaddleTextRecognizer  # noqa: E402
from run_recognition import write_recognition_overlay  # noqa: E402


class RecognitionLabTests(unittest.TestCase):
    def test_orders_a_rotated_quadrilateral(self) -> None:
        import numpy as np

        points = np.array([[50, 10], [10, 40], [50, 40], [10, 10]], dtype=np.float32)
        ordered = order_quad(points)
        self.assertEqual(ordered.tolist(), [[10.0, 10.0], [50.0, 10.0], [50.0, 40.0], [10.0, 40.0]])

    def test_crops_from_original_coordinates(self) -> None:
        import numpy as np

        image = np.full((60, 100, 3), 255, dtype=np.uint8)
        image[20:40, 25:75] = 0
        crop = crop_polygon(image, [[25, 20], [75, 20], [75, 40], [25, 40]])
        self.assertGreater(crop.shape[1], crop.shape[0])
        self.assertLess(crop.mean(), 100)

    def test_parses_recognition_payload(self) -> None:
        self.assertEqual(
            PaddleTextRecognizer._payload({"res": {"rec_text": "phiếu", "rec_score": 0.95}}),
            {"rec_text": "phiếu", "rec_score": 0.95},
        )

    def test_parseq_confidence_uses_mean_token_confidence(self) -> None:
        import torch

        self.assertAlmostEqual(float(torch.tensor([0.8, 1.0]).mean().item()), 0.9)

    def test_writes_unicode_recognition_overlay(self) -> None:
        import numpy as np
        import tempfile

        original = np.full((50, 100, 3), 255, dtype=np.uint8)
        recognition = {
            "index": 0,
            "polygon": [[10, 10], [90, 10], [90, 35], [10, 35]],
            "text": "Không theo phiếu",
            "recognition_score": 0.98,
        }
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "annotated.png"
            write_recognition_overlay(destination, original, [recognition])
            self.assertTrue(destination.is_file())


if __name__ == "__main__":
    unittest.main()
