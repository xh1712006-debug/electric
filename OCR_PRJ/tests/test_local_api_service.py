import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from pydantic import ValidationError

from src.relay_form_ocr import (
    DocumentOcrOrchestrator,
    ErrorCode,
    OcrRequest,
    OcrResult,
    PageRole,
    PageStatus,
    ProcessingStatus,
    RelayFormOcrService,
    ReviewStatus,
)
from src.layout_analysis import Page1LayoutAnalysisService, Page3PlusLayoutAnalysisService
from src.pdf_form_splitter.pdf_io import render_pdf
from src.relay_form_ocr.service_visual import render_service_review


class _FakeOrchestrator:
    def __init__(self, page_count=3, *, fail=False, warnings=True):
        self.page_count = page_count
        self.fail = fail
        self.include_warnings = warnings
        self.calls = 0
        self.model_loads = 0
        self._models_loaded = False

    def extract_pdf_x(self, candidate, output_dir):
        self.calls += 1
        if not self._models_loaded:
            self._models_loaded = True
            self.model_loads += 1
        output = Path(output_dir)
        rendered = output / "rendered"
        pages_dir = output / "pages"
        rendered.mkdir(parents=True, exist_ok=True)
        pages_dir.mkdir(parents=True, exist_ok=True)

        artifacts = []
        pages = []
        for page_number in range(1, self.page_count + 1):
            image = rendered / f"page-{page_number}.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([page_number]))
            artifacts.append({"kind": "rendered_page", "relative_path": f"rendered/{image.name}"})

        for page_number in range(1, self.page_count + 1):
            if page_number == 1:
                role = "page1"
                status = "completed"
            elif page_number == 2:
                role = "page2_skipped"
                status = "skipped_by_document_policy"
            else:
                role = "page3_plus"
                status = "completed"
            payload = {
                "page_number": page_number,
                "page_role": role,
                "status": status,
                "warnings": [],
            }
            page_path = pages_dir / f"page_{page_number:04d}.json"
            page_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            artifacts.append({"kind": "page_result", "relative_path": f"pages/{page_path.name}"})
            pages.append(payload)

        extraction = output / "extraction.json"
        extraction.write_text('{"internal": "raw evidence"}', encoding="utf-8")
        artifacts.append({"kind": "extraction_result", "relative_path": "extraction.json"})
        if self.fail:
            raise RuntimeError(r"pipeline failed at C:\private\input.pdf with traceback")

        warnings = []
        if self.include_warnings and self.page_count >= 2:
            warnings.append(
                {
                    "code": "page2_skipped_by_document_policy",
                    "message": "Trang 2 được bỏ qua theo chính sách tài liệu.",
                    "page_number": 2,
                }
            )
        if self.include_warnings and self.page_count >= 3:
            warnings.append(
                {
                    "code": "layout_warning",
                    "message": "Candidate layout inferred from OCR geometry; it is not ground truth.",
                    "page_number": 3,
                }
            )
        setting_records = []
        notes = []
        if self.page_count >= 3:
            setting_records.append(
                {
                    "page_number": 3,
                    "parameter_code": "0103",
                    "parameter_name": "Tùy chọn chuyển nhóm chỉnh định",
                    "value": "Enabled",
                    "unit": None,
                    "description": "Ứng viên cần xem xét",
                }
            )
            notes.append({"page_number": 3, "text": "Lưu ý: kiểm tra thông số trước khi duyệt."})

        return {
            "schema_version": "1.0",
            "important_fields": {
                "ticket_number": "A1-09-2021/E4.4/220",
                "station": "Trạm 220 kV Việt Trì",
            },
            "important_field_resolution": {
                "ticket_number": {
                    "status": "auto_selected",
                    "preserved_existing_value": False,
                    "effective_score": 96.5,
                    "confidence": {"level": 5, "label": "very_high"},
                },
                "station": {
                    "status": "preserved_existing",
                    "preserved_existing_value": True,
                    "effective_score": 84.0,
                    "confidence": {"level": 4, "label": "high"},
                },
            },
            "setting_records": setting_records,
            "note_candidates": notes,
            "warnings": warnings,
            "pages": pages,
            "artifacts": artifacts,
        }


def _write_pdf(path):
    path.write_bytes(b"%PDF-1.4\n% synthetic service fixture\n")
    return path


class LocalPythonApiTests(unittest.TestCase):
    def _request(self, root, correlation_id="api-test", *, filename="fixture.pdf"):
        source = _write_pdf(root / filename)
        output = root / "artifacts"
        return OcrRequest(
            input_pdf=source.resolve(),
            output_root=output.resolve(),
            correlation_id=correlation_id,
        )

    def test_public_service_maps_internal_result_to_strict_typed_contract(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self._request(root)
            fake = _FakeOrchestrator(page_count=3)
            result = RelayFormOcrService(orchestrator=fake, page_counter=lambda _path: 3).process_pdf(request)

            self.assertIsInstance(result, OcrResult)
            self.assertEqual(result.status, ProcessingStatus.SUCCESS_WITH_WARNINGS)
            self.assertEqual(result.review_status, ReviewStatus.REVIEW_REQUIRED)
            self.assertEqual(result.document.source_name, "fixture.pdf")
            self.assertEqual(result.business.page1_fields.station.value, "Trạm 220 kV Việt Trì")
            self.assertEqual(result.business.page1_fields.ticket_number.confidence.score, 96.5)
            self.assertEqual(result.business.page1_fields.ticket_number.confidence.level, 5)
            self.assertEqual(len(result.business.page1_fields.__class__.model_fields), 25)
            self.assertEqual(len(result.business.setting_records), 1)
            self.assertEqual(len(result.business.note_candidates), 1)
            self.assertTrue(all(record.review_status == ReviewStatus.REVIEW_REQUIRED for record in result.business.setting_records))
            self.assertTrue(all(note.review_status == ReviewStatus.REVIEW_REQUIRED for note in result.business.note_candidates))
            self.assertEqual([page.role for page in result.pages], [PageRole.PAGE1, PageRole.PAGE2, PageRole.PAGE3_PLUS])
            self.assertEqual(result.pages[1].status, PageStatus.SKIPPED_BY_POLICY)
            self.assertTrue(result.artifact_manifest.artifacts)
            self.assertTrue(all(not Path(item.relative_path).is_absolute() for item in result.artifact_manifest.artifacts))
            self.assertTrue(all(item.relative_path.startswith("api-test/") for item in result.artifact_manifest.artifacts))
            self.assertEqual(OcrResult.model_validate_json(result.model_dump_json()), result)

    def test_one_page_without_warning_or_review_is_success(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self._request(root)
            result = RelayFormOcrService(
                orchestrator=_FakeOrchestrator(page_count=1, warnings=False),
                page_counter=lambda _path: 1,
            ).process_pdf(request)
        self.assertEqual(result.status, ProcessingStatus.SUCCESS)
        self.assertEqual(result.review_status, ReviewStatus.NOT_REQUIRED)
        self.assertEqual(result.warnings, [])

    def test_service_reuses_same_orchestrator_and_model_lifecycle(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = _FakeOrchestrator(page_count=1, warnings=False)
            service = RelayFormOcrService(orchestrator=fake, page_counter=lambda _path: 1)
            first = service.process_pdf(self._request(root, "sequential-001", filename="first.pdf"))
            second = service.process_pdf(self._request(root, "sequential-002", filename="second.pdf"))
        self.assertEqual((first.status, second.status), (ProcessingStatus.SUCCESS, ProcessingStatus.SUCCESS))
        self.assertEqual(fake.calls, 2)
        self.assertEqual(fake.model_loads, 1)

    def test_missing_file_returns_typed_failure(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = OcrRequest(
                input_pdf=(root / "missing.pdf").resolve(),
                output_root=(root / "out").resolve(),
                correlation_id="missing-file",
            )
            result = RelayFormOcrService(page_counter=lambda _path: 1).process_pdf(request)
        self.assertEqual(result.status, ProcessingStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INPUT_NOT_FOUND)
        self.assertIsNone(result.business)
        self.assertNotIn(str(root), result.model_dump_json())

    def test_directory_with_pdf_suffix_returns_input_not_file(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "folder.pdf"
            folder.mkdir()
            request = OcrRequest(
                input_pdf=folder.resolve(),
                output_root=(root / "out").resolve(),
                correlation_id="folder-input",
            )
            result = RelayFormOcrService(page_counter=lambda _path: 1).process_pdf(request)
        self.assertEqual(result.error.code, ErrorCode.INPUT_NOT_FILE)

    def test_invalid_signature_and_corrupt_pdf_return_invalid_pdf(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            invalid = root / "invalid.pdf"
            invalid.write_bytes(b"not-a-pdf")
            invalid_request = OcrRequest(
                input_pdf=invalid.resolve(),
                output_root=(root / "out-invalid").resolve(),
                correlation_id="invalid-signature",
            )
            invalid_result = RelayFormOcrService(page_counter=lambda _path: 1).process_pdf(invalid_request)

            corrupt_request = self._request(root, "corrupt-structure", filename="corrupt.pdf")
            corrupt_result = RelayFormOcrService(
                page_counter=lambda _path: (_ for _ in ()).throw(ValueError("corrupt"))
            ).process_pdf(corrupt_request)

        self.assertEqual(invalid_result.error.code, ErrorCode.INVALID_PDF)
        self.assertEqual(corrupt_result.error.code, ErrorCode.INVALID_PDF)

    def test_empty_pdf_page_count_is_invalid(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self._request(root)
            result = RelayFormOcrService(page_counter=lambda _path: 0).process_pdf(request)
        self.assertEqual(result.error.code, ErrorCode.INVALID_PDF)

    def test_output_root_file_and_nonempty_workspace_are_not_overwritten(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _write_pdf(root / "fixture.pdf")
            output_file = root / "output-file"
            output_file.write_text("do not overwrite", encoding="utf-8")
            file_request = OcrRequest(
                input_pdf=source.resolve(),
                output_root=output_file.resolve(),
                correlation_id="output-file",
            )
            file_result = RelayFormOcrService(page_counter=lambda _path: 1).process_pdf(file_request)

            output_root = root / "out"
            occupied = output_root / "occupied"
            occupied.mkdir(parents=True)
            marker = occupied / "keep.txt"
            marker.write_text("không ghi đè", encoding="utf-8")
            collision_request = OcrRequest(
                input_pdf=source.resolve(),
                output_root=output_root.resolve(),
                correlation_id="occupied",
            )
            collision_result = RelayFormOcrService(page_counter=lambda _path: 1).process_pdf(collision_request)

            marker_text = marker.read_text(encoding="utf-8")

        self.assertEqual(file_result.error.code, ErrorCode.OUTPUT_NOT_WRITABLE)
        self.assertEqual(collision_result.error.code, ErrorCode.OUTPUT_NOT_WRITABLE)
        self.assertEqual(marker_text, "không ghi đè")

    def test_pipeline_exception_becomes_safe_failure_and_keeps_partial_artifacts(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self._request(root)
            result = RelayFormOcrService(
                orchestrator=_FakeOrchestrator(page_count=1, fail=True),
                page_counter=lambda _path: 1,
            ).process_pdf(request)
            payload = result.model_dump_json()

        self.assertEqual(result.status, ProcessingStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INTERNAL_PIPELINE_ERROR)
        self.assertEqual(result.error.stage.value, "pipeline")
        self.assertTrue(result.artifact_manifest.artifacts)
        self.assertNotIn("traceback", payload.lower())
        self.assertNotIn("private", payload.lower())
        self.assertNotIn(str(root), payload)

    def test_wrong_extension_and_non_model_are_rejected_at_typed_boundary(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValidationError):
                OcrRequest(
                    input_pdf=(root / "input.txt").resolve(),
                    output_root=(root / "out").resolve(),
                    correlation_id="wrong-extension",
                )
        with self.assertRaises(TypeError):
            RelayFormOcrService().process_pdf({"input_pdf": "x"})
        with self.assertRaises(ValueError):
            RelayFormOcrService(pipeline_version="development")

    def test_service_import_and_process_are_independent_of_working_directory(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "consumer"
            outside.mkdir()
            missing_pdf = (root / "không-tồn-tại.pdf").resolve()
            output_root = (root / "artifacts").resolve()
            repository = Path(__file__).resolve().parents[1]
            code = (
                "from pathlib import Path; "
                "from src.relay_form_ocr import OcrRequest, RelayFormOcrService; "
                f"r=OcrRequest(input_pdf=Path({str(missing_pdf)!r}), output_root=Path({str(output_root)!r}), correlation_id='external-cwd'); "
                "print(RelayFormOcrService().process_pdf(r).error.code.value)"
            )
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(repository) + os.pathsep + environment.get("PYTHONPATH", "")
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=outside,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "INPUT_NOT_FOUND")

    def test_visual_report_is_utf8_vietnamese_and_covers_public_contract(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self._request(root)
            result = RelayFormOcrService(
                orchestrator=_FakeOrchestrator(page_count=3),
                page_counter=lambda _path: 3,
            ).process_pdf(request)
            output = render_service_review(result, root / "service_review.html")
            html = output.read_text(encoding="utf-8")
        self.assertIn('<html lang="vi">', html)
        self.assertIn("Kiểm thử trực quan synchronous local Python API", html)
        self.assertIn("Trạm 220 kV Việt Trì", result.model_dump_json())
        self.assertIn("Trang 2 — bỏ qua theo chính sách", html)
        self.assertIn("Cần xem xét", html)
        self.assertIn("Ranh giới an toàn", html)
        self.assertIn("Bố cục ứng viên được suy ra từ hình học OCR", html)
        self.assertNotIn("Candidate layout inferred from OCR geometry", html)
        for label in ("Rất thấp", "Thấp", "Trung bình", "Cao", "Rất cao"):
            self.assertIn(label, html)

    def test_visual_cli_is_safe_on_cp1258_console_and_keeps_utf8_html(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self._request(root)
            result = RelayFormOcrService(
                orchestrator=_FakeOrchestrator(page_count=3),
                page_counter=lambda _path: 3,
            ).process_pdf(request)
            result_json = root / "public_result.json"
            result_json.write_text(result.model_dump_json(indent=2), encoding="utf-8")
            report = root / "service_review.html"
            environment = os.environ.copy()
            environment["PYTHONIOENCODING"] = "cp1258"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.relay_form_ocr.service_visual",
                    "--result-json",
                    str(result_json),
                    "--output",
                    str(report),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                capture_output=True,
                timeout=30,
                check=False,
            )
            html = report.read_text(encoding="utf-8")
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("ascii", errors="replace"))
        self.assertIn(b"Status: success_with_warnings", completed.stdout)
        self.assertIn("Kiểm thử trực quan synchronous local Python API", html)
        self.assertIn("Cần xem xét", html)


class LocalPythonApiIntegrationTests(unittest.TestCase):
    def test_public_service_processes_real_pdf_fixture_with_real_render_and_layout(self):
        try:
            from pypdf import PdfWriter
        except ImportError as exc:  # pragma: no cover
            self.skipTest(f"pypdf unavailable: {exc}")

        detector = Mock()
        detection = Mock(detections=[])
        detection.as_dict.return_value = {"detections": []}
        detector.detect_page.return_value = detection
        recognizer = Mock()
        recognition = Mock()
        recognition.as_dict.return_value = {"regions": [], "elapsed_ms": 0.0}
        recognizer.recognise_page.return_value = recognition

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "phiếu-thử-nghiệm.pdf"
            writer = PdfWriter()
            for _ in range(3):
                writer.add_blank_page(width=320, height=480)
            with pdf.open("wb") as stream:
                writer.write(stream)

            orchestrator = DocumentOcrOrchestrator(
                render_dpi=72,
                detector=detector,
                recognizer=recognizer,
                page1_service=Page1LayoutAnalysisService(),
                page3_plus_service=Page3PlusLayoutAnalysisService(),
                renderer=render_pdf,
            )
            request = OcrRequest(
                input_pdf=pdf.resolve(),
                output_root=(root / "artifacts").resolve(),
                correlation_id="real-render-layout",
            )
            result = RelayFormOcrService(orchestrator=orchestrator).process_pdf(request)

            self.assertNotEqual(result.status, ProcessingStatus.FAILED, result.error)
            self.assertEqual(result.document.page_count, 3)
            self.assertEqual(len(result.pages), 3)
            self.assertEqual(detector.detect_page.call_count, 2)
            self.assertEqual(recognizer.recognise_page.call_count, 2)
            self.assertTrue((root / "artifacts" / "real-render-layout" / "extraction.json").is_file())
            self.assertTrue(result.artifact_manifest.artifacts)
            self.assertEqual(OcrResult.model_validate_json(result.model_dump_json()), result)


if __name__ == "__main__":
    unittest.main()
