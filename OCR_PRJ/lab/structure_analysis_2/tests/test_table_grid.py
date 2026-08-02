import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from lab.structure_analysis_2.table_grid import detect_table_grid


class TableGridTests(unittest.TestCase):
    def test_two_disconnected_tables_are_detected_as_two_regions(self):
        image = np.full((1000, 800), 255, dtype=np.uint8)
        for top, bottom in ((100, 400), (550, 900)):
            for x in (80, 250, 500, 720):
                cv2.line(image, (x, top), (x, bottom), 0, 3)
            for y in range(top, bottom + 1, 50):
                cv2.line(image, (80, y), (720, y), 0, 3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "two_tables.png"
            cv2.imwrite(str(path), image)
            result = detect_table_grid(path)
        self.assertTrue(result["available"])
        self.assertEqual(len(result["regions"]), 2)
        self.assertEqual([len(region["column_centres"]) for region in result["regions"]], [3, 3])


if __name__ == "__main__":
    unittest.main()
