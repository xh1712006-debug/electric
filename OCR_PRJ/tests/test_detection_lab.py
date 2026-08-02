"""Tests for dependency-free detector result normalisation."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lab" / "detection"))

from run_comparison import concise_error  # noqa: E402
from detectors import DetectorNotConfiguredError, PaddleDetector, paddle_prediction_payload, polygons_from_nested  # noqa: E402
from preprocessing import PREPROCESSORS  # noqa: E402
from preprocessing import watermark_suppression  # noqa: E402


class PolygonNormalisationTests(unittest.TestCase):
    def test_extracts_a_polygon_from_nested_paddle_result(self) -> None:
        result = [[[[1, 2], [10, 2], [10, 8], [1, 8]]]]

        self.assertEqual(
            polygons_from_nested(result),
            [[[1.0, 2.0], [10.0, 2.0], [10.0, 8.0], [1.0, 8.0]]],
        )

    def test_ignores_scalars_and_non_polygon_lists(self) -> None:
        self.assertEqual(polygons_from_nested(["ignored", [1, 2], None]), [])

    def test_native_error_is_condensed_for_the_summary(self) -> None:
        self.assertLessEqual(len(concise_error(RuntimeError("line\n" * 500))), 700)
        self.assertNotIn("\n", concise_error(RuntimeError("line\nline")))

    def test_reads_the_v3_detection_payload(self) -> None:
        self.assertEqual(
            paddle_prediction_payload({"res": {"dt_polys": [], "dt_scores": []}}),
            {"dt_polys": [], "dt_scores": []},
        )

    def test_missing_custom_checkpoint_is_not_a_runtime_failure(self) -> None:
        with self.assertRaises(DetectorNotConfiguredError):
            PaddleDetector(Path("does-not-exist"), model_name=None, use_gpu=False)

    def test_training_weights_receive_an_export_hint(self) -> None:
        with self.assertRaisesRegex(DetectorNotConfiguredError, "must be exported"):
            PaddleDetector(
                Path("does-not-exist"),
                model_name=None,
                use_gpu=False,
                training_checkpoint_dir=Path("."),
            )

    def test_preprocessing_options_are_stable(self) -> None:
        self.assertEqual(PREPROCESSORS, ("original", "clahe", "adaptive_threshold"))

    def test_two_stage_otsu_removes_the_light_gray_class(self) -> None:
        import numpy as np

        gray = np.array([[0, 10, 80, 85, 160, 170, 250, 255]] * 12, dtype=np.uint8)
        binary, metadata = watermark_suppression(gray)
        self.assertLess(metadata["ink_threshold"], metadata["selected_threshold"])
        self.assertLess(metadata["selected_threshold"], metadata["paper_threshold"])
        self.assertEqual(binary[0, 0], 0)
        self.assertEqual(binary[0, 4], 255)


if __name__ == "__main__":
    unittest.main()
