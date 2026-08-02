import unittest
import importlib.util
import io
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.pdf_form_splitter.cli import build_parser
from src.pdf_form_splitter.evidence import PageEvidence, build_page_evidence
from src.pdf_form_splitter.pdf_io import pdf_page_count, poppler_binary, split_pdf
from src.pdf_form_splitter.service import PdfFormSplitterService, PdfSplitterConfig, discover_pdf_files
from src.pdf_form_splitter.segmenter import segment_pages


def evidence(index, current=None, total=None, cover=0.0, ticket="A1-01-2026/E5.8/220"):
    return PageEvidence(
        page_index=index,
        page_reference=f"{current}/{total}" if current is not None and total is not None else None,
        current_page=current,
        total_pages=total,
        pagination_label=None,
        ticket_number=ticket,
        cover_score=cover,
    )


class CombinedPdfSegmenterTests(unittest.TestCase):
    @unittest.skipUnless(
        any((Path.home() / ".cache" / "codex-runtimes").glob("*/dependencies/native/poppler/Library/bin/pdftoppm.exe")),
        "bundled Poppler runtime is unavailable",
    )
    def test_poppler_fallback_finds_bundled_runtime_without_path(self):
        self.assertTrue(Path(poppler_binary("pdftoppm")).is_file())
        self.assertTrue(Path(poppler_binary("pdfinfo")).is_file())

    def test_folder_discovery_is_direct_case_insensitive_and_sorted(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "b.PDF").touch()
            (root / "A.pdf").touch()
            (root / "notes.txt").touch()
            nested = root / "nested"
            nested.mkdir()
            (nested / "ignored.pdf").touch()
            self.assertEqual([path.name for path in discover_pdf_files(root)], ["A.pdf", "b.PDF"])

    def test_cli_requires_exactly_one_input_source(self):
        parser = build_parser()
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args([])
            with self.assertRaises(SystemExit):
                parser.parse_args(["one.pdf", "--folder_dir", "incoming"])
        self.assertEqual(parser.parse_args(["--folder_dir", "incoming"]).folder_dir, Path("incoming"))

    def test_production_service_configuration_validates_ranges(self):
        with self.assertRaises(ValueError):
            PdfSplitterConfig(scan_ratio=0.10)
        service = PdfFormSplitterService(PdfSplitterConfig(render_reviews=False))
        self.assertFalse(service.config.render_reviews)

    def test_production_service_reuses_ocr_models_across_calls(self):
        service = PdfFormSplitterService()
        with (
            patch("src.detection.DocumentTextDetectionService") as detector_factory,
            patch("src.recognition.VietnameseRecognitionService") as recognizer_factory,
            patch("src.pdf_form_splitter.service.analyse_rendered_pages", return_value=([], [])) as analyse,
        ):
            service._analyse_rendered_pages([])
            service._analyse_rendered_pages([])
        detector_factory.assert_called_once_with(use_gpu=False)
        recognizer_factory.assert_called_once_with(use_gpu=False)
        self.assertEqual(analyse.call_count, 2)

    def test_terminal_pages_and_cover_signatures_split_two_forms(self):
        pages = [
            evidence(1, 1, 3, 0.8, "A1-01-2026/E5.8/220"),
            evidence(2, 2, 3, 0.0, "A1-01-2026/E5.8/220"),
            evidence(3, 3, 3, 0.0, "A1-01-2026/E5.8/220"),
            evidence(4, 1, 2, 0.8, "A1-02-2026/E5.8/220"),
            evidence(5, 2, 2, 0.0, "A1-02-2026/E5.8/220"),
        ]
        segments = segment_pages(pages)
        self.assertEqual([(item.start_page, item.end_page) for item in segments], [(1, 3), (4, 5)])
        self.assertTrue(all(item.end_reason == "pagination_terminal" for item in segments))

    def test_strong_page1_signature_recovers_boundary_when_pagination_is_missing(self):
        pages = [evidence(1, None, None, 0.8), evidence(2), evidence(3, None, None, 0.8, "A1-02-2026/E5.8/220"), evidence(4)]
        segments = segment_pages(pages)
        self.assertEqual([(item.start_page, item.end_page) for item in segments], [(1, 2), (3, 4)])

    def test_page_number_one_alone_does_not_create_boundary(self):
        pages = [evidence(1, 1, 3, 0.8), evidence(2, 1, 5, 0.0), evidence(3, 3, 3, 0.0)]
        segments = segment_pages(pages)
        self.assertEqual(len(segments), 1)
        self.assertIn("pagination_jump:1->1", segments[0].warnings)

    def test_page_after_terminal_starts_orphan_even_without_cover_features(self):
        pages = [evidence(1, 1, 1, 0.8), evidence(2), evidence(3)]
        segments = segment_pages(pages)
        self.assertEqual([(item.start_page, item.end_page) for item in segments], [(1, 1), (2, 3)])
        self.assertIn("after_terminal_page", segments[1].start_reasons)

    def test_missing_intermediate_pagination_is_not_a_false_jump(self):
        pages = [evidence(1, 1, 5, 0.8), evidence(2), evidence(3), evidence(4), evidence(5, 5, 5)]
        segment = segment_pages(pages)[0]
        self.assertFalse(any(warning.startswith("pagination_jump") for warning in segment.warnings))

    def test_cover_evidence_uses_multiple_page1_characteristics(self):
        blocks = [
            {"block_id": "a", "text": "PHIẾU CHỈNH ĐỊNH RƠ-LE BẢO VỆ", "bbox_pixel": [700, 30, 1100, 60]},
            {"block_id": "b", "text": "Leaf: 1/5", "bbox_pixel": [900, 80, 1050, 105]},
            {"block_id": "c", "text": "Mô tả chung", "bbox_pixel": [100, 150, 300, 180]},
            {"block_id": "d", "text": "Thiết bị được bảo vệ", "bbox_pixel": [100, 210, 400, 240]},
            {"block_id": "e", "text": "footer", "bbox_pixel": [100, 1000, 200, 1020]},
        ]
        result = build_page_evidence(1, blocks)
        self.assertGreaterEqual(result.cover_score, 0.5)
        self.assertEqual(result.current_page, 1)
        self.assertEqual(result.total_pages, 5)

    def test_ticket_evidence_prefers_header_over_referenced_old_ticket(self):
        blocks = [
            {"block_id": "header", "text": "Số phiếu: A1-29-2026/E5.8/220", "bbox_pixel": [700, 50, 1100, 80]},
            {"block_id": "note", "text": "Phiếu này thay phiếu số A1-04-2021/E5.8/220", "bbox_pixel": [100, 400, 800, 430]},
        ]
        result = build_page_evidence(5, blocks)
        self.assertEqual(result.ticket_number, "A1-29-2026/E5.8/220")

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "pypdf production dependency is unavailable")
    def test_pdf_writer_preserves_source_and_segment_page_counts(self):
        from pypdf import PdfReader, PdfWriter

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "combined.pdf"
            writer = PdfWriter()
            for _ in range(5):
                writer.add_blank_page(width=595, height=842)
            with source.open("wb") as stream:
                writer.write(stream)
            segments = segment_pages([
                evidence(1, 1, 3, 0.8, "A1-01-2026/E5.8/220"),
                evidence(2, 2, 3, 0.0, "A1-01-2026/E5.8/220"),
                evidence(3, 3, 3, 0.0, "A1-01-2026/E5.8/220"),
                evidence(4, 1, 2, 0.8, "A1-02-2026/E5.8/220"),
                evidence(5, 2, 2, 0.0, "A1-02-2026/E5.8/220"),
            ])
            outputs = split_pdf(source, segments, root / "documents")
            self.assertEqual(pdf_page_count(source), 5)
            self.assertEqual([item["validated_page_count"] for item in outputs], [3, 2])
            self.assertEqual([len(PdfReader(item["output_pdf"]).pages) for item in outputs], [3, 2])

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "pypdf production dependency is unavailable")
    def test_source_prefixes_allow_shared_batch_output_folder(self):
        from pypdf import PdfWriter

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            documents = root / "documents"
            segments = segment_pages([evidence(1, 1, 1, 0.8, "A1-01-2026/E5.8/220")])
            output_names = []
            for source_name in ("form_a.pdf", "form_b.pdf"):
                source = root / source_name
                writer = PdfWriter()
                writer.add_blank_page(width=595, height=842)
                with source.open("wb") as stream:
                    writer.write(stream)
                result = split_pdf(source, segments, documents, filename_prefix=source.stem)
                output_names.append(Path(result[0]["output_pdf"]).name)
            self.assertEqual(len(set(output_names)), 2)
            self.assertTrue(all((documents / name).is_file() for name in output_names))
            self.assertEqual(output_names[0], "form_a__001_A1-01-2026_E5.8_220.pdf")


if __name__ == "__main__":
    unittest.main()
