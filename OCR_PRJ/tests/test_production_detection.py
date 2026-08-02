"""Unit tests for the dependency-light production detection contract."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.detection.pp_ocr import Detection, PPTextDetector  # noqa: E402
from src.detection.preprocessing import detect_red_stamp_mask, encode_mask_rle, prepare_detection_image, suppress_gray_watermark  # noqa: E402
from src.detection.service import DetectionResult, filter_stamp_detections  # noqa: E402


class ProductionDetectionTests(unittest.TestCase):
    def test_watermark_suppression_keeps_dark_ink_only(self) -> None:
        import numpy as np

        gray = np.array([[0, 10, 80, 85, 160, 170, 250, 255]] * 12, dtype=np.uint8)
        binary, metadata = suppress_gray_watermark(gray)

        self.assertLess(metadata["ink_threshold"], metadata["selected_threshold"])
        self.assertLess(metadata["selected_threshold"], metadata["paper_threshold"])
        self.assertEqual(binary[0, 0], 0)
        self.assertEqual(binary[0, 4], 255)

    def test_result_is_serialisable_for_an_ocr_job(self) -> None:
        result = DetectionResult(
            detections=[Detection(polygon=[[1.0, 2.0], [3.0, 2.0], [3.0, 4.0]], score=0.91)],
            preprocessing={"selected_threshold": 128},
            detector_version="PP-OCRv5_mobile_det",
            elapsed_ms=12.5,
        )

        self.assertEqual(result.as_dict()["detections"][0]["score"], 0.91)
        self.assertEqual(result.as_dict()["preprocessing"]["selected_threshold"], 128)

    def test_red_stamp_mask_removes_red_ink_but_keeps_black_text(self) -> None:
        import cv2
        import numpy as np

        image = np.full((180, 220, 3), 255, dtype=np.uint8)
        cv2.circle(image, (160, 90), 35, (0, 0, 220), 4)
        cv2.rectangle(image, (20, 80), (40, 100), (0, 0, 0), thickness=-1)
        mask, metadata = detect_red_stamp_mask(image)
        prepared, _, _ = prepare_detection_image(image)

        self.assertGreater(metadata["red_pixel_count"], 100)
        self.assertEqual(mask[90, 125], 255)
        self.assertTrue((prepared[90, 125] == 255).all())
        self.assertTrue((prepared[90, 30] == 0).all())

    def test_detections_mostly_inside_stamp_are_suppressed(self) -> None:
        import numpy as np

        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[20:80, 20:80] = 255
        inside = Detection(polygon=[[25, 25], [75, 25], [75, 75], [25, 75]], score=0.9)
        outside = Detection(polygon=[[0, 0], [15, 0], [15, 15], [0, 15]], score=0.9)
        kept, suppressed = filter_stamp_detections([inside, outside], mask)

        self.assertEqual(suppressed, 1)
        self.assertEqual(kept, [outside])

    def test_stamp_mask_rle_preserves_active_pixel_locations(self) -> None:
        import numpy as np

        mask = np.zeros((2, 4), dtype=np.uint8)
        mask[0, 1:3] = 255
        mask[1, 0] = 255
        self.assertEqual(encode_mask_rle(mask), {"shape": [2, 4], "runs": [[1, 2], [4, 1]]})

    def test_paddle_payload_is_normalised(self) -> None:
        self.assertEqual(
            PPTextDetector._payload({"res": {"dt_polys": [], "dt_scores": []}}),
            {"dt_polys": [], "dt_scores": []},
        )


if __name__ == "__main__":
    unittest.main()
