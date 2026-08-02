import io
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from src.relay_form_ocr import (
    DocumentOcrOrchestrator,
    ErrorCode,
    ErrorStage,
    JsonLineFormatter,
    OcrRequest,
    ProcessingStatus,
    RelayFormOcrService,
)
from src.relay_form_ocr.cli import CliExitCode, main as cli_main
from src.relay_form_ocr.observability_visual import render_observability_review
from src.relay_form_ocr.workspace import WorkspaceManager, WorkspaceWriteError


REPOSITORY = Path(__file__).resolve().parents[1]
ERROR_CATALOG = REPOSITORY / "contracts" / "local_api" / "v1" / "error_catalog.json"
PRIVATE_TEXT = r"OCR bí mật tại C:\private\phiếu.pdf"


def _write_pdf(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n% observability fixture\n")
    return path


def _renderer(source, output, *, dpi):
    output.mkdir(parents=True, exist_ok=True)
    page = output / "page-1.png"
    page.write_bytes(b"\x89PNG\r\n\x1a\nobservability")
    return [page]


def _raising_renderer(source, output, *, dpi):
    raise RuntimeError(PRIVATE_TEXT)


def _detection_result():
    value = Mock(detections=[])
    value.as_dict.return_value = {"detections": []}
    return value


def _recognition_result():
    value = Mock()
    value.as_dict.return_value = {"regions": [], "elapsed_ms": 1}
    return value


def _layout_result():
    value = Mock()
    value.as_dict.return_value = {
        "fields": {},
        "source_labels": {},
        "field_resolution": {},
        "warnings": [],
    }
    return value


def _logger(stream: io.StringIO, name: str) -> logging.Logger:
    logger = logging.Logger(name, level=logging.INFO)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def _request(root: Path, correlation_id: str) -> OcrRequest:
    return OcrRequest(
        input_pdf=_write_pdf(root / "dữ-liệu" / "phiếu-quan-sát.pdf").resolve(),
        output_root=(root / "kết-quả").resolve(),
        correlation_id=correlation_id,
    )


def _orchestrator(*, failure_stage: ErrorStage | None = None) -> DocumentOcrOrchestrator:
    detector = Mock()
    recognizer = Mock()
    page1 = Mock()
    if failure_stage == ErrorStage.DETECTION:
        detector.detect_page.side_effect = RuntimeError(PRIVATE_TEXT)
    else:
        detector.detect_page.return_value = _detection_result()
    if failure_stage == ErrorStage.RECOGNITION:
        recognizer.recognise_page.side_effect = RuntimeError(PRIVATE_TEXT)
    else:
        recognizer.recognise_page.return_value = _recognition_result()
    if failure_stage == ErrorStage.LAYOUT:
        page1.analyse_page.side_effect = RuntimeError(PRIVATE_TEXT)
    else:
        page1.analyse_page.return_value = _layout_result()
    return DocumentOcrOrchestrator(
        detector=detector,
        recognizer=recognizer,
        page1_service=page1,
        renderer=_raising_renderer if failure_stage == ErrorStage.RENDERING else _renderer,
    )


class _FailingArtifactManager(WorkspaceManager):
    def declared_artifacts(self, handle, raw_artifacts):
        raise WorkspaceWriteError(PRIVATE_TEXT)


class LocalObservabilityTests(unittest.TestCase):
    def test_public_progress_is_monotonic_bounded_structured_and_terminal(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = []
            result = RelayFormOcrService(
                orchestrator=_orchestrator(),
                page_counter=lambda _path: 1,
            ).process_pdf(_request(root, "progress-success"), progress=events.append)

        completed = [event.completed for event in events]
        self.assertEqual(result.status, ProcessingStatus.SUCCESS)
        self.assertEqual(completed, sorted(completed))
        self.assertTrue(all(0 <= value <= event.total == 100 for value, event in zip(completed, events)))
        self.assertEqual(events[0].event, "validation_started")
        self.assertEqual(events[-1].event, "request_completed")
        self.assertEqual(events[-1].completed, 100)
        self.assertTrue(events[-1].terminal)
        self.assertTrue(all(event.correlation_id == "progress-success" for event in events))
        self.assertTrue(
            {ErrorStage.RENDERING, ErrorStage.DETECTION, ErrorStage.RECOGNITION, ErrorStage.LAYOUT}
            <= {event.stage for event in events}
        )

    def test_callback_exception_is_logged_once_then_disabled_without_failing_ocr(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            stream = io.StringIO()
            calls = []

            def broken_callback(event):
                calls.append(event)
                raise RuntimeError(PRIVATE_TEXT)

            result = RelayFormOcrService(
                orchestrator=_orchestrator(),
                page_counter=lambda _path: 1,
                logger=_logger(stream, "callback-policy"),
            ).process_pdf(_request(root, "callback-failure"), progress=broken_callback)

        self.assertEqual(result.status, ProcessingStatus.SUCCESS)
        self.assertEqual(len(calls), 1)
        self.assertEqual(stream.getvalue().count('"event":"progress_callback_failed"'), 1)
        self.assertNotIn(PRIVATE_TEXT, stream.getvalue())

    def test_stable_stage_mapping_and_retryability_for_injected_failures(self):
        cases = (
            (ErrorStage.RENDERING, ErrorCode.PDF_RENDER_FAILED, True),
            (ErrorStage.DETECTION, ErrorCode.DETECTION_FAILED, True),
            (ErrorStage.RECOGNITION, ErrorCode.RECOGNITION_FAILED, True),
            (ErrorStage.LAYOUT, ErrorCode.LAYOUT_FAILED, False),
        )
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (stage, code, retryable) in enumerate(cases, start=1):
                with self.subTest(stage=stage):
                    result = RelayFormOcrService(
                        orchestrator=_orchestrator(failure_stage=stage),
                        page_counter=lambda _path: 1,
                    ).process_pdf(_request(root, f"stage-failure-{index}"))
                    self.assertEqual(result.status, ProcessingStatus.FAILED)
                    self.assertEqual(result.error.code, code)
                    self.assertEqual(result.error.stage, stage)
                    self.assertEqual(result.error.retryable, retryable)
                    self.assertTrue(
                        any(item.kind == "artifact_manifest" for item in result.artifact_manifest.artifacts)
                    )
                    self.assertNotIn(PRIVATE_TEXT, result.model_dump_json())

    def test_failed_call_emits_one_terminal_failure_without_forcing_false_completion(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = []
            result = RelayFormOcrService(
                orchestrator=_orchestrator(failure_stage=ErrorStage.RECOGNITION),
                page_counter=lambda _path: 1,
            ).process_pdf(_request(root, "terminal-failure"), progress=events.append)
        self.assertEqual(result.status, ProcessingStatus.FAILED)
        self.assertEqual(events[-1].event, "request_failed")
        self.assertTrue(events[-1].terminal)
        self.assertLess(events[-1].completed, 100)
        self.assertEqual(sum(event.terminal for event in events), 1)
        self.assertEqual([event.completed for event in events], sorted(event.completed for event in events))

    def test_validation_and_workspace_collision_are_non_retryable(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = OcrRequest(
                input_pdf=(root / "missing.pdf").resolve(),
                output_root=(root / "output").resolve(),
                correlation_id="missing-input",
            )
            missing_result = RelayFormOcrService(page_counter=lambda _path: 1).process_pdf(missing)
            request = _request(root, "collision")
            service = RelayFormOcrService(orchestrator=_orchestrator(), page_counter=lambda _path: 1)
            first = service.process_pdf(request)
            collision = service.process_pdf(request)
        self.assertEqual(missing_result.error.code, ErrorCode.INPUT_NOT_FOUND)
        self.assertFalse(missing_result.error.retryable)
        self.assertEqual(first.status, ProcessingStatus.SUCCESS)
        self.assertEqual(collision.error.code, ErrorCode.OUTPUT_NOT_WRITABLE)
        self.assertFalse(collision.error.retryable)
        self.assertEqual(collision.error.details, {"reason": "workspace_collision"})

    def test_filesystem_failure_is_artifact_write_retryable_and_keeps_partial_evidence(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = RelayFormOcrService(
                orchestrator=_orchestrator(),
                page_counter=lambda _path: 1,
                workspace_manager=_FailingArtifactManager(),
            ).process_pdf(_request(root, "artifact-failure"))
        self.assertEqual(result.status, ProcessingStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.ARTIFACT_WRITE_FAILED)
        self.assertEqual(result.error.stage, ErrorStage.ARTIFACT_WRITE)
        self.assertTrue(result.error.retryable)
        self.assertEqual(result.error.details, {"reason": "workspace_write"})
        self.assertGreaterEqual(len(result.artifact_manifest.artifacts), 2)

    def test_default_structured_logs_cover_stages_and_redact_paths_text_and_traceback(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            stream = io.StringIO()
            request = _request(root, "redacted-log")
            result = RelayFormOcrService(
                orchestrator=_orchestrator(failure_stage=ErrorStage.DETECTION),
                page_counter=lambda _path: 1,
                logger=_logger(stream, "redaction"),
            ).process_pdf(request)
            lines = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(result.error.code, ErrorCode.DETECTION_FAILED)
        self.assertTrue(lines)
        self.assertTrue(all(line.get("timestamp", "").endswith("Z") for line in lines))
        self.assertTrue(all(line["correlation_id"] == "redacted-log" for line in lines))
        self.assertTrue(all("stage" in line and "event" in line for line in lines))
        serialized = stream.getvalue()
        self.assertNotIn(str(request.input_pdf), serialized)
        self.assertNotIn("OCR bí mật", serialized)
        self.assertNotIn("private", serialized)
        self.assertNotIn("traceback", serialized.lower())
        self.assertIn('"exception_type":"RuntimeError"', serialized)

    def test_orchestrator_legacy_three_argument_callback_remains_compatible(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _write_pdf(root / "legacy.pdf")
            calls = []
            _orchestrator().extract_pdf_x(
                Mock(candidate_id="legacy", name="legacy.pdf", path=str(source), page_count=1, origin="test", as_dict=lambda: {}),
                root / "legacy-output",
                progress=lambda completed, total, message: calls.append((completed, total, message)),
            )
        self.assertEqual(calls[0][:2], (0, 1))
        self.assertEqual(calls[-1][:2], (1, 1))

    def test_error_catalog_matches_public_enums_and_security_policy(self):
        catalog = json.loads(ERROR_CATALOG.read_text(encoding="utf-8"))
        entries = catalog["errors"]
        self.assertEqual({item["code"] for item in entries}, {item.value for item in ErrorCode})
        self.assertTrue({item["stage"] for item in entries} <= {item.value for item in ErrorStage})
        self.assertFalse(catalog["policies"]["public_exception_text"])
        self.assertFalse(catalog["policies"]["public_stack_trace"])
        self.assertFalse(catalog["policies"]["default_log_pdf_path"])
        self.assertFalse(catalog["policies"]["default_log_ocr_text"])

    def test_cli_keeps_stdout_machine_json_and_writes_structured_stage_logs_to_stderr(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            stdout = io.StringIO()
            stderr = io.StringIO()
            code = cli_main(
                [
                    "--input", str(root / "không-tồn-tại.pdf"),
                    "--output-root", str(root / "kết-quả"),
                    "--correlation-id", "cli-observability",
                    "--json",
                ],
                stdout=stdout,
                stderr=stderr,
            )
        payload = json.loads(stdout.getvalue())
        structured = [json.loads(line) for line in stderr.getvalue().splitlines() if line.startswith("{")]
        self.assertEqual(code, CliExitCode.INPUT)
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)
        self.assertEqual(payload["error"]["code"], "INPUT_NOT_FOUND")
        self.assertTrue(structured)
        self.assertTrue(all(item["correlation_id"] == "cli-observability" for item in structured))
        self.assertTrue(any(item["event"] == "request_failed" for item in structured))

    def test_visual_report_is_accented_vietnamese_and_covers_progress_logs_and_errors(self):
        catalog = json.loads(ERROR_CATALOG.read_text(encoding="utf-8"))
        progress = [
            {"sequence": 1, "stage": "validation", "event": "validation_started", "completed": 0, "total": 100, "message": "Bắt đầu kiểm tra."},
            {"sequence": 2, "stage": "pipeline", "event": "request_completed", "completed": 100, "total": 100, "terminal": True, "message": "Đã hoàn tất."},
        ]
        with TemporaryDirectory() as temporary:
            output = render_observability_review(
                Path(temporary) / "observability_review.html",
                progress_events=progress,
                error_catalog=catalog,
            )
            html = output.read_text(encoding="utf-8")
        self.assertIn('<html lang="vi">', html)
        self.assertIn("Kiểm thử trực quan progress, logging và lỗi ổn định", html)
        self.assertIn("Dòng tiến độ", html)
        self.assertIn("Catalog lỗi public", html)
        self.assertIn("Log JSON đã khử dữ liệu nhạy cảm", html)
        self.assertIn("Callback không điều khiển pipeline", html)
        self.assertIn("Không lộ dữ liệu", html)
        for code in ErrorCode:
            self.assertIn(code.value, html)


if __name__ == "__main__":
    unittest.main()
