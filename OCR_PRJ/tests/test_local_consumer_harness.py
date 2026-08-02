import ast
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory, TemporaryFile
import unittest

from examples.local_consumer.consumer_visual import render_consumer_review
from examples.local_consumer.python_consumer import (
    ConsumerIntegrityError,
    EXIT_CONSUMER_FAILURE,
    EXIT_OCR_FAILED,
    EXIT_READY,
    EXIT_REVIEW_REQUIRED,
    _safe_artifact_path,
    audit_artifact_manifest,
    consume_document,
    isolate_consumer_stdout,
)
from src.relay_form_ocr import (
    ErrorCode,
    OcrRequest,
    ProcessingStatus,
    RelayFormOcrService,
    ReviewStatus,
)


ROOT = Path(__file__).resolve().parents[1]
PYTHON_CONSUMER = ROOT / "examples" / "local_consumer" / "python_consumer.py"
POWERSHELL_CONSUMER = ROOT / "examples" / "local_consumer" / "invoke_ocr.ps1"
PYTHON_EXE = ROOT / "lab" / "structure_analysis_2" / ".venv" / "Scripts" / "python.exe"


def _write_pdf(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n% consumer integration fixture\n")
    return path


class _ConsumerOrchestrator:
    def __init__(self, *, review_required: bool = False, fail: bool = False):
        self.review_required = review_required
        self.fail = fail

    def extract_pdf_x(self, candidate, output_dir):
        output = Path(output_dir)
        rendered = output / "rendered"
        pages = output / "pages"
        rendered.mkdir(parents=True, exist_ok=True)
        pages.mkdir(parents=True, exist_ok=True)
        image = rendered / "page-1.png"
        page_json = pages / "page_0001.json"
        extraction = output / "extraction.json"
        image.write_bytes(b"\x89PNG\r\n\x1a\nconsumer")
        page_json.write_text('{"page_number":1}', encoding="utf-8")
        extraction.write_text('{"evidence":"candidate"}', encoding="utf-8")
        if self.fail:
            raise RuntimeError(r"private failure at C:\secret\document.pdf")
        resolution = {}
        fields = {}
        if self.review_required:
            fields["station"] = "Trạm cần duyệt"
            resolution["station"] = {
                "status": "review_required",
                "effective_score": 55.0,
                "confidence": {"level": 3, "label": "medium"},
            }
        return {
            "important_fields": fields,
            "important_field_resolution": resolution,
            "setting_records": [],
            "note_candidates": [],
            "warnings": [],
            "pages": [{"page_number": 1, "page_role": "page1", "status": "completed"}],
            "artifacts": [
                {"kind": "rendered_page", "relative_path": "rendered/page-1.png"},
                {"kind": "page_result", "relative_path": "pages/page_0001.json"},
                {"kind": "extraction_result", "relative_path": "extraction.json"},
            ],
        }


class LocalConsumerHarnessTests(unittest.TestCase):
    def _request(self, root: Path, correlation_id: str) -> OcrRequest:
        source = _write_pdf(root / "dữ-liệu" / "phiếu-consumer.pdf")
        return OcrRequest(
            input_pdf=source.resolve(),
            output_root=(root / "kết-quả consumer").resolve(),
            correlation_id=correlation_id,
        )

    def _consume(self, root: Path, correlation_id: str, *, review=False, fail=False):
        request = self._request(root, correlation_id)
        service = RelayFormOcrService(
            orchestrator=_ConsumerOrchestrator(review_required=review, fail=fail),
            page_counter=lambda _path: 1,
        )
        return request, consume_document(request, service=service)

    def test_python_example_imports_only_public_relay_form_ocr_surface(self):
        tree = ast.parse(PYTHON_CONSUMER.read_text(encoding="utf-8"))
        project_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src"):
                project_imports.append(node.module)
            if isinstance(node, ast.Import):
                project_imports.extend(alias.name for alias in node.names if alias.name.startswith("src"))
        self.assertEqual(project_imports, ["src.relay_form_ocr"])
        source = PYTHON_CONSUMER.read_text(encoding="utf-8")
        self.assertNotIn("src.relay_form_ocr.service", source)
        self.assertNotIn("src.relay_form_ocr.workspace", source)
        self.assertNotIn("src.debug_ui", source)

    def test_successful_fixture_is_schema_valid_manifest_audited_and_ready(self):
        with TemporaryDirectory() as temporary:
            request, run = self._consume(Path(temporary), "consumer-ready")
            manifest = next(
                item for item in run.result.artifact_manifest.artifacts if item.kind == "artifact_manifest"
            )
            manifest_payload = json.loads(
                (request.output_root / Path(manifest.relative_path)).read_text(encoding="utf-8")
            )
        self.assertEqual(run.result.status, ProcessingStatus.SUCCESS)
        self.assertEqual(run.result.review_status, ReviewStatus.NOT_REQUIRED)
        self.assertEqual(run.exit_code, EXIT_READY)
        self.assertEqual(run.summary["outcome"], "ready_for_use")
        self.assertTrue(run.summary["manifest_audit"]["all_verified"])
        self.assertTrue(run.summary["manifest_audit"]["source_unchanged"])
        self.assertEqual(manifest_payload["workspace_id"], "consumer-ready")

    def test_review_required_can_never_become_approved_or_ready(self):
        with TemporaryDirectory() as temporary:
            _request, run = self._consume(Path(temporary), "consumer-review", review=True)
        encoded = json.dumps(run.summary, ensure_ascii=False).casefold()
        self.assertEqual(run.exit_code, EXIT_REVIEW_REQUIRED)
        self.assertEqual(run.summary["outcome"], "manual_review_required")
        self.assertEqual(run.summary["review_status"], "review_required")
        self.assertNotIn("approved", encoded)
        self.assertNotIn("ready_for_use", encoded)

    def test_public_failure_uses_safe_code_stage_retryability_and_partial_manifest(self):
        with TemporaryDirectory() as temporary:
            _request, run = self._consume(Path(temporary), "consumer-failed", fail=True)
        serialized = json.dumps(run.summary, ensure_ascii=False)
        self.assertEqual(run.exit_code, EXIT_OCR_FAILED)
        self.assertEqual(run.summary["outcome"], "failed")
        self.assertEqual(run.summary["public_error"]["code"], ErrorCode.INTERNAL_PIPELINE_ERROR.value)
        self.assertFalse(run.summary["public_error"]["retryable"])
        self.assertTrue(run.summary["manifest_audit"]["all_verified"])
        self.assertNotIn("secret", serialized.casefold())
        self.assertNotIn("document.pdf", serialized)
        self.assertNotIn("traceback", serialized.casefold())

    def test_tampered_artifact_is_rejected_as_consumer_failure(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            request, run = self._consume(root, "consumer-tamper")
            target = next(
                item for item in run.result.artifact_manifest.artifacts if item.kind == "extraction_result"
            )
            (request.output_root / Path(target.relative_path)).write_text("đã bị sửa", encoding="utf-8")
            with self.assertRaisesRegex(ConsumerIntegrityError, "artifact_(size|checksum)_mismatch"):
                audit_artifact_manifest(run.result, request.output_root)

    def test_artifact_path_escape_is_rejected_without_reading_outside_root(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for candidate in ("../secret.json", "/server/private.json", r"C:\private\secret.json"):
                with self.subTest(candidate=candidate):
                    with self.assertRaises(ConsumerIntegrityError):
                        _safe_artifact_path(root, candidate)

    def test_missing_input_is_a_typed_failure_without_fabricated_manifest(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = OcrRequest(
                input_pdf=(root / "không-tồn-tại.pdf").resolve(),
                output_root=(root / "output").resolve(),
                correlation_id="consumer-missing",
            )
            run = consume_document(request, service=RelayFormOcrService(page_counter=lambda _path: 1))
        self.assertEqual(run.exit_code, EXIT_OCR_FAILED)
        self.assertEqual(run.summary["public_error"]["code"], ErrorCode.INPUT_NOT_FOUND.value)
        self.assertFalse(run.summary["manifest_audit"]["available"])
        self.assertTrue(run.summary["manifest_audit"]["all_verified"])

    def test_python_consumer_runs_from_separate_unicode_directory(self):
        with TemporaryDirectory() as temporary:
            external = Path(temporary) / "thư-mục consumer"
            external.mkdir()
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
            completed = subprocess.run(
                [
                    str(PYTHON_EXE),
                    "-m",
                    "examples.local_consumer.python_consumer",
                    "--input",
                    str(external / "không-có.pdf"),
                    "--output-root",
                    str(external / "kết-quả"),
                    "--correlation-id",
                    "external-python",
                ],
                cwd=external,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, EXIT_OCR_FAILED)
        self.assertEqual(payload["outcome"], "failed")
        self.assertEqual(payload["public_error"]["code"], "INPUT_NOT_FOUND")
        self.assertNotIn(str(external), completed.stdout)

    def test_python_consumer_isolates_python_and_native_model_output_from_summary_stream(self):
        with TemporaryFile("w+", encoding="utf-8") as stdout, TemporaryFile("w+", encoding="utf-8") as stderr:
            with isolate_consumer_stdout(stdout, stderr):
                print("python model noise")
                os.write(stdout.fileno(), b"native model noise\n")
            stdout.write('{"outcome":"ready_for_use"}\n')
            stdout.flush()
            stdout.seek(0)
            stderr.seek(0)
            machine = stdout.read()
            diagnostics = stderr.read()
        self.assertEqual(machine, '{"outcome":"ready_for_use"}\n')
        self.assertIn("python model noise", diagnostics)
        self.assertIn("native model noise", diagnostics)

    @unittest.skipUnless(sys.platform == "win32" and PYTHON_EXE.is_file(), "requires Windows PowerShell")
    def test_powershell_consumer_runs_from_separate_unicode_directory(self):
        with TemporaryDirectory() as temporary:
            external = Path(temporary) / "consumer PowerShell"
            external.mkdir()
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(POWERSHELL_CONSUMER),
                    "-InputPdf",
                    str(external / "không-có.pdf"),
                    "-OutputRoot",
                    str(external / "kết-quả"),
                    "-CorrelationId",
                    "external-powershell",
                    "-ProjectRoot",
                    str(ROOT),
                    "-PythonExe",
                    str(PYTHON_EXE),
                ],
                cwd=external,
                capture_output=True,
                text=True,
                encoding="utf-8-sig",
                timeout=45,
            )
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, EXIT_OCR_FAILED)
        self.assertEqual(payload["outcome"], "failed")
        self.assertEqual(payload["cli_exit_code"], 3)
        self.assertNotIn(str(external), completed.stdout)

    def test_visual_review_is_accented_vietnamese_and_covers_all_decisions(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _request, review_run = self._consume(root, "consumer-visual", review=True)
            output = render_consumer_review(
                [
                    review_run.summary,
                    {
                        **review_run.summary,
                        "correlation_id": "consumer-visual-failure",
                        "outcome": "consumer_failure",
                        "consumer_error": "artifact_checksum_mismatch",
                    },
                ],
                root / "consumer_review.html",
            )
            html = output.read_text(encoding="utf-8")
        self.assertIn('<html lang="vi">', html)
        self.assertIn("Kiểm thử trực quan consumer local OCR", html)
        self.assertIn("Bắt buộc duyệt thủ công", html)
        self.assertIn("Consumer từ chối kết quả", html)
        self.assertIn("Không auto-approve", html)
        self.assertIn("Đã xác nhận", html)
        self.assertNotIn("C:\\", html)


if __name__ == "__main__":
    unittest.main()
