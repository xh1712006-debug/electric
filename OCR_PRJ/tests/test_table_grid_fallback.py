"""Tests for ruling-line evidence when no connected table can be rebuilt."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import cv2
import numpy as np

from src.image_io import write_image
from src.layout_analysis.table_grid import detect_table_grid


class TableGridFallbackTests(unittest.TestCase):
    def test_horizontal_boundaries_survive_without_complete_grid(self) -> None:
        with TemporaryDirectory() as temporary:
            image = np.full((600, 800, 3), 255, dtype=np.uint8)
            for y in (120, 180, 240):
                cv2.line(image, (50, y), (750, y), (0, 0, 0), 2)
            path = Path(temporary) / "borderless-table.png"
            write_image(path, image)

            grid = detect_table_grid(path)

            self.assertFalse(grid["available"])
            for expected in (120, 180, 240):
                self.assertTrue(any(abs(actual - expected) <= 3 for actual in grid["page_horizontal_lines"]))

    def test_skewed_seven_row_table_is_recovered_from_ruling_lines(self) -> None:
        with TemporaryDirectory() as temporary:
            image = np.full((700, 900, 3), 255, dtype=np.uint8)
            left, right = 90, 810
            boundaries = (120, 185, 230, 305, 350, 395, 455, 510)
            for y in boundaries:
                cv2.line(image, (left, y), (right, y + 12), (40, 40, 40), 2, cv2.LINE_AA)
            cv2.line(image, (left, boundaries[0]), (left + 7, boundaries[-1]), (40, 40, 40), 2, cv2.LINE_AA)
            cv2.line(image, (520, boundaries[0] + 7), (527, boundaries[-1] + 7), (40, 40, 40), 2, cv2.LINE_AA)
            cv2.line(image, (right, boundaries[0] + 12), (right + 7, boundaries[-1] + 12), (40, 40, 40), 2, cv2.LINE_AA)
            path = Path(temporary) / "skewed-table.png"
            write_image(path, image)

            grid = detect_table_grid(path)

            self.assertTrue(grid["available"])
            seven_row_regions = [region for region in grid["regions"] if len(region["row_bands"]) == 7]
            self.assertTrue(seven_row_regions)
            self.assertGreaterEqual(len(seven_row_regions[0]["vertical_lines"]), 3)
