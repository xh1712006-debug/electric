import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from src.layout_analysis import Page1LayoutAnalysisService, Page3PlusLayoutAnalysisService
from src.pdf_form_splitter.pdf_io import render_pdf
from src.relay_form_ocr import DocumentOcrOrchestrator, PdfCandidate, page_role
from src.relay_form_ocr.visual import demo_orchestrator_result, render_orchestrator_html


def _renderer_for(count):
    def render(_source, output, *, dpi):
        return [output / f"page_{index:04d}.png" for index in range(1, count + 1)]
    return render


def _recognition(regions):
    value = Mock()
    value.as_dict.return_value = {"regions": regions, "elapsed_ms": 1}
    return value


class DocumentOrchestratorUnitTests(unittest.TestCase):
    def test_page_roles_and_invalid_page_number(self):
        self.assertEqual(page_role(1), "page1")
        self.assertEqual(page_role(2), "page2_skipped")
        self.assertEqual(page_role(3), "page3_plus")
        self.assertEqual(page_role(99), "page3_plus")
        with self.assertRaises(ValueError):
            page_role(0)

    def test_models_load_vietocr_before_paddle_and_are_reused(self):
        calls = []
        orchestrator = DocumentOcrOrchestrator()
        with (
            patch(
                "src.relay_form_ocr.orchestrator.VietnameseRecognitionService",
                side_effect=lambda **_kwargs: calls.append("vietocr") or Mock(),
            ) as recognition_type,
            patch(
                "src.relay_form_ocr.orchestrator.DocumentTextDetectionService",
                side_effect=lambda **_kwargs: calls.append("paddle") or Mock(),
            ) as detection_type,
        ):
            first = orchestrator.models()
            second = orchestrator.models()

        self.assertEqual(calls, ["vietocr", "paddle"])
        self.assertIs(first[0], second[0])
        self.assertIs(first[1], second[1])
        recognition_type.assert_called_once()
        detection_type.assert_called_once()

    def test_routes_pages_aggregates_evidence_and_propagates_warnings(self):
        detector = Mock()
        detection = Mock(detections=[])
        detection.as_dict.return_value = {"detections": []}
        detector.detect_page.return_value = detection
        recognizer = Mock()
        page1_regions = [
            {"index": 0, "text": "Số phiếu: A1", "polygon": [[0, 0], [2, 0], [2, 1], [0, 1]]}
        ]
        page3_regions = [
            {"index": 0, "text": "Lưu ý:", "polygon": [[0, 0], [2, 0], [2, 1], [0, 1]]},
            {"index": 1, "text": "Kiểm tra thông số", "polygon": [[0, 2], [2, 2], [2, 3], [0, 3]]},
        ]
        recognizer.recognise_page.side_effect = [_recognition(page1_regions), _recognition(page3_regions)]

        page1_result = Mock()
        page1_result.as_dict.return_value = {
            "fields": {"ticket_number": {"text": "A1"}},
            "source_labels": {"ticket_number": {"text": "Số phiếu"}},
            "field_resolution": {
                "ticket_number": {
                    "status": "auto_selected",
                    "confidence": {"level": 5, "label": "very_high"},
                }
            },
            "warnings": ["page1_warning"],
        }
        page1 = Mock()
        page1.analyse_page.return_value = page1_result
        page3_result = Mock()
        page3_result.as_dict.return_value = {
            "records": [
                {"record_id": "r1", "parameter_name": {"text": "Pickup"}, "value": {"text": "5"}}
            ],
            "warning": "candidate_layout",
        }
        page3 = Mock()
        page3.analyse_page.return_value = page3_result

        orchestrator = DocumentOcrOrchestrator(
            detector=detector,
            recognizer=recognizer,
            page1_service=page1,
            page3_plus_service=page3,
            renderer=_renderer_for(3),
        )
        candidate = PdfCandidate("id", "form.pdf", "form.pdf", 3, "direct_pdf_x")
        with TemporaryDirectory() as temporary:
            result = orchestrator.extract_pdf_x(candidate, temporary)
            stored = json.loads((Path(temporary) / "extraction.json").read_text(encoding="utf-8"))

        self.assertEqual(detector.detect_page.call_count, 2)
        self.assertEqual(result["pages"][1]["status"], "skipped_by_document_policy")
        self.assertEqual(result["important_fields"]["ticket_number"], "A1")
        self.assertEqual(result["important_source_labels"]["ticket_number"], "Số phiếu")
        self.assertEqual(result["important_field_resolution"]["ticket_number"]["confidence"]["level"], 5)
        self.assertEqual(result["setting_records"][0]["value"], "5")
        self.assertEqual(result["note_candidates"][0]["page_number"], 3)
        self.assertEqual(
            [warning["code"] for warning in result["warnings"]],
            ["layout_warning", "page2_skipped_by_document_policy", "layout_warning"],
        )
        self.assertEqual(stored["summary"]["warnings"], 3)
        self.assertTrue(all(not Path(item["relative_path"]).is_absolute() for item in result["artifacts"]))

    def test_page_count_mismatch_is_an_explicit_warning(self):
        orchestrator = DocumentOcrOrchestrator(
            detector=Mock(), recognizer=Mock(), renderer=_renderer_for(0)
        )
        candidate = PdfCandidate("id", "empty.pdf", "empty.pdf", 1, "test")
        with TemporaryDirectory() as temporary:
            result = orchestrator.extract_pdf_x(candidate, temporary)
        self.assertEqual(result["warnings"][0]["code"], "page_count_mismatch")


class DocumentOrchestratorIntegrationTests(unittest.TestCase):
    def test_real_pdf_render_and_layout_path_with_fake_ocr(self):
        try:
            from pypdf import PdfWriter
        except ImportError as exc:  # pragma: no cover
            self.skipTest(f"pypdf unavailable: {exc}")

        detector = Mock()
        detection = Mock(detections=[])
        detection.as_dict.return_value = {"detections": []}
        detector.detect_page.return_value = detection
        recognizer = Mock()
        recognizer.recognise_page.side_effect = [_recognition([]), _recognition([])]

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "three-pages.pdf"
            writer = PdfWriter()
            for _ in range(3):
                writer.add_blank_page(width=320, height=480)
            with pdf.open("wb") as stream:
                writer.write(stream)
            output = root / "result"
            orchestrator = DocumentOcrOrchestrator(
                render_dpi=120,
                detector=detector,
                recognizer=recognizer,
                page1_service=Page1LayoutAnalysisService(),
                page3_plus_service=Page3PlusLayoutAnalysisService(),
                renderer=render_pdf,
            )
            result = orchestrator.extract_pdf_x(
                PdfCandidate("integration", pdf.name, str(pdf), 3, "test_fixture"), output
            )

            self.assertEqual(
                [page["page_role"] for page in result["pages"]],
                ["page1", "page2_skipped", "page3_plus"],
            )
            self.assertEqual(detector.detect_page.call_count, 2)
            self.assertEqual(len(list((output / "rendered").glob("page-*.png"))), 3)
            self.assertTrue((output / "pages" / "page_0003.json").is_file())
            self.assertTrue((output / "extraction.json").is_file())

    def test_production_package_has_no_debug_streamlit_or_lab_imports(self):
        root = Path("src/relay_form_ocr")
        forbidden = ("streamlit", "src.debug_ui", "src.lab", "lab")
        found = []
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                found.extend(name for name in names if any(name == item or name.startswith(item + ".") for item in forbidden))
        self.assertEqual(found, [])


class DocumentOrchestratorVisualTests(unittest.TestCase):
    def test_report_is_utf8_vietnamese_and_covers_all_routes_and_confidence_levels(self):
        with TemporaryDirectory() as temporary:
            output = render_orchestrator_html(
                demo_orchestrator_result(), Path(temporary) / "orchestrator_review.html"
            )
            html = output.read_text(encoding="utf-8")

        self.assertIn('<html lang="vi">', html)
        self.assertIn("Kiểm thử trực quan document orchestrator production", html)
        self.assertIn("Trang bìa và thông tin quan trọng", html)
        self.assertIn("Trang 2 — bỏ qua theo chính sách", html)
        self.assertIn("Trang thông số chỉnh định", html)
        for label in ("Rất thấp", "Thấp", "Trung bình", "Cao", "Rất cao"):
            self.assertIn(label, html)


if __name__ == "__main__":
    unittest.main()
