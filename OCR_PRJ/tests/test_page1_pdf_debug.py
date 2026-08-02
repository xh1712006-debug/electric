"""Tests for multi-page PDF input to page-1 debug analysis."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from src.image_io import write_image
from src.layout_analysis.page1.pdf_debug import analyse_pdf_page1


class _Detector:
    def __init__(self) -> None:
        self.calls = 0

    def detect_page(self, _image_path: Path):
        self.calls += 1
        return SimpleNamespace(detections=[], as_dict=lambda: {"detections": []})


class _Recognizer:
    def __init__(self) -> None:
        self.calls = 0

    def recognise_page(self, _image_path: Path, _detections):
        self.calls += 1
        return SimpleNamespace(as_dict=lambda: {
            "regions": [],
            "recognizer_version": "test",
            "elapsed_ms": 0.0,
        })


class Page1PdfDebugTests(unittest.TestCase):
    def test_multi_page_pdf_outputs_debug_artifacts_and_reuses_ocr(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "phiếu nhiều trang.pdf"
            source.write_bytes(b"%PDF-1.4\nsynthetic-test")
            rendered = []
            for page_number in range(1, 4):
                image_path = root / "prepared" / f"page-{page_number}.png"
                write_image(image_path, np.full((100, 80, 3), 255, dtype=np.uint8))
                rendered.append(image_path)
            output = root / "debug"
            detector = _Detector()
            recognizer = _Recognizer()

            with patch("src.layout_analysis.page1.pdf_debug.render_pdf", return_value=rendered):
                manifest = analyse_pdf_page1(
                    source,
                    output,
                    detector=detector,
                    recognizer=recognizer,
                )
                cached = analyse_pdf_page1(source, output, reuse_ocr=True)

            self.assertEqual(detector.calls, 1)
            self.assertEqual(recognizer.calls, 1)
            self.assertEqual(manifest["source"]["page_count"], 3)
            self.assertEqual(manifest["analysis"]["analysed_pages"], [1])
            self.assertEqual(manifest["analysis"]["other_pages"], [2, 3])
            self.assertEqual(cached["analysis"]["ocr_mode"], "cached")
            for filename in (
                "debug_manifest.json",
                "detection.json",
                "recognition.json",
                "ocr_blocks.json",
                "page1_layout.json",
                "table_grid.json",
                "table_grid.png",
                "review_overlay.png",
            ):
                self.assertTrue((output / filename).is_file(), filename)
