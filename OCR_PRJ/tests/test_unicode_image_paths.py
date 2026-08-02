"""Regression tests for Windows OpenCV paths containing Vietnamese text."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import cv2
import numpy as np

from src.detection.preprocessing import load_detection_input
from src.image_io import read_image, write_image
from src.layout_analysis.table_grid import detect_table_grid
from src.recognition.service import VietnameseRecognitionService


class _UnusedRecognizer:
    model_version = "test"

    def recognise(self, _crop):  # pragma: no cover - no regions are supplied.
        raise AssertionError("The recognizer must not run for an empty detection list.")


class UnicodeImagePathTests(unittest.TestCase):
    def test_production_image_stages_accept_vietnamese_path(self) -> None:
        with TemporaryDirectory() as temporary:
            image_path = Path(temporary) / "220kV Việt Trì" / "trang-01.png"
            source = np.full((80, 120, 3), 245, dtype=np.uint8)
            source[25:55, 40:80] = (0, 0, 0)
            write_image(image_path, source)

            decoded = read_image(image_path, cv2.IMREAD_COLOR)
            self.assertEqual(decoded.shape, source.shape)
            prepared, stamp_mask, _ = load_detection_input(image_path)
            self.assertEqual(prepared.shape, source.shape)
            self.assertEqual(stamp_mask.shape, source.shape[:2])

            recognition = VietnameseRecognitionService(recognizer=_UnusedRecognizer()).recognise_page(image_path, [])
            self.assertEqual(recognition.regions, [])
            self.assertIn("available", detect_table_grid(image_path))

    def test_unicode_overlay_output_is_written(self) -> None:
        with TemporaryDirectory() as temporary:
            destination = Path(temporary) / "kết quả" / "ảnh review.png"
            write_image(destination, np.zeros((12, 12), dtype=np.uint8))
            self.assertTrue(destination.is_file())
            self.assertEqual(read_image(destination, cv2.IMREAD_GRAYSCALE).shape, (12, 12))
