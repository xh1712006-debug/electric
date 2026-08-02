import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from src.debug_ui.pipeline import (
    PdfCandidate,
    PdfOcrDebugPipeline,
    flatten_record,
    note_candidate,
    page_role,
    safe_pdf_name,
)


class DebugUiPipelineTests(unittest.TestCase):
    def test_upload_name_is_basename_and_pdf(self):
        self.assertEqual(safe_pdf_name(r"..\unsafe:name.PDF"), "unsafe_name.pdf")
        self.assertEqual(safe_pdf_name("phiếu A"), "phiếu A.pdf")

    def test_different_uploads_with_same_name_do_not_overwrite(self):
        with TemporaryDirectory() as temporary:
            first = PdfOcrDebugPipeline.save_uploaded_pdf("same.pdf", b"%PDF-first", temporary)
            second = PdfOcrDebugPipeline.save_uploaded_pdf("same.pdf", b"metadata%PDF-second", temporary)
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), b"%PDF-first")
            self.assertEqual(second.read_bytes(), b"metadata%PDF-second")

    def test_page_roles_follow_known_form_contract(self):
        self.assertEqual(page_role(1), "page1")
        self.assertEqual(page_role(2), "page2_skipped")
        self.assertEqual(page_role(3), "page3_plus")

    def test_note_candidate_starts_at_luu_y_heading(self):
        regions = [
            {"text": "0406 Capture Time", "polygon": [[10, 10], [20, 10], [20, 20], [10, 20]]},
            {"text": "Lưu ý:", "polygon": [[10, 30], [20, 30], [20, 40], [10, 40]]},
            {"text": "1. Nội dung quan trọng", "polygon": [[10, 50], [20, 50], [20, 60], [10, 60]]},
        ]
        self.assertEqual(note_candidate(regions), "Lưu ý:\n1. Nội dung quan trọng")

    def test_record_fields_are_flattened_for_debug_table(self):
        result = flatten_record({"record_id": "r1", "parameter_name": {"text": "Pickup"}, "value": {"text": "5"}})
        self.assertEqual(result["parameter_name"], "Pickup")
        self.assertEqual(result["value"], "5")
        self.assertIsNone(result["unit"])

    def test_extract_delegates_to_production_orchestrator_without_changing_result(self):
        pipeline = PdfOcrDebugPipeline(render_dpi=160)
        expected = {"schema_version": "1.0", "summary": {"pages": 3}}
        pipeline._orchestrator = Mock()
        pipeline._orchestrator.extract_pdf_x.return_value = expected
        candidate = PdfCandidate("id", "form.pdf", "form.pdf", 3, "direct_pdf_x")

        with TemporaryDirectory() as temporary:
            result = pipeline.extract_pdf_x(candidate, Path(temporary))

        self.assertIs(result, expected)
        pipeline._orchestrator.extract_pdf_x.assert_called_once()


if __name__ == "__main__":
    unittest.main()
