import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from src.relay_form_ocr import ErrorCode, ErrorStage, OcrResult
from src.relay_form_ocr.cli import (
    CliExitCode,
    CliUsageError,
    exit_code_for_result,
    main,
    parse_cli_args,
)
from src.relay_form_ocr.cli_visual import render_cli_review


REPOSITORY = Path(__file__).resolve().parents[1]
SUCCESS_FIXTURE = REPOSITORY / "contracts" / "local_api" / "v1" / "examples" / "success.json"
FAILURE_FIXTURE = REPOSITORY / "contracts" / "local_api" / "v1" / "examples" / "failure.json"


def _fixture_result(path: Path, correlation_id: str) -> OcrResult:
    outer = json.loads(path.read_text(encoding="utf-8"))
    result = OcrResult.model_validate(outer["result"])
    return result.model_copy(update={"correlation_id": correlation_id})


class _SuccessfulService:
    def process_pdf(self, request):
        print("simulated model output")
        return _fixture_result(SUCCESS_FIXTURE, request.correlation_id)


class _ProcessingFailureService:
    def process_pdf(self, request):
        result = _fixture_result(FAILURE_FIXTURE, request.correlation_id)
        error = result.error.model_copy(
            update={
                "code": ErrorCode.INTERNAL_PIPELINE_ERROR,
                "stage": ErrorStage.PIPELINE,
                "message": "Không thể hoàn tất pipeline OCR.",
            }
        )
        return result.model_copy(update={"error": error})


class _CrashingService:
    def process_pdf(self, request):
        print("model output before crash")
        raise RuntimeError("private pipeline traceback")


class LocalCliJsonAdapterTests(unittest.TestCase):
    def _base_args(self, root: Path, *, correlation_id: str = "cli-test") -> list[str]:
        return [
            "--input",
            str(root / "phiếu-chỉnh-định.pdf"),
            "--output-root",
            str(root / "kết-quả"),
            "--correlation-id",
            correlation_id,
            "--json",
        ]

    def test_parser_accepts_input_output_correlation_and_result_file_options(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            result_path = root / "result.json"
            args = parse_cli_args(self._base_args(root) + ["--output-json", str(result_path), "--overwrite-result"])
        self.assertEqual(args.correlation_id, "cli-test")
        self.assertTrue(args.json)
        self.assertEqual(args.output_json, result_path)
        self.assertTrue(args.overwrite_result)

    def test_parser_rejects_invalid_option_combinations(self):
        with TemporaryDirectory() as temporary:
            with self.assertRaises(CliUsageError):
                parse_cli_args(self._base_args(Path(temporary)) + ["--overwrite-result"])
        with self.assertRaises(CliUsageError):
            parse_cli_args(["--input", "only.pdf"])

    def test_success_emits_only_one_machine_json_to_stdout_and_logs_to_stderr(self):
        with TemporaryDirectory() as temporary:
            stdout = io.StringIO()
            stderr = io.StringIO()
            code = main(
                self._base_args(Path(temporary), correlation_id="cli-success"),
                service_factory=_SuccessfulService,
                stdout=stdout,
                stderr=stderr,
            )
        lines = stdout.getvalue().splitlines()
        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, CliExitCode.SUCCESS)
        self.assertEqual(len(lines), 1)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["correlation_id"], "cli-success")
        self.assertNotIn("simulated model output", stdout.getvalue())
        self.assertIn("simulated model output", stderr.getvalue())
        self.assertIn("start correlation_id=cli-success", stderr.getvalue())
        self.assertIn("finish correlation_id=cli-success status=success exit=0", stderr.getvalue())

    def test_output_json_keeps_stdout_empty_and_refuses_overwrite_by_default(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            result_path = root / "reports" / "kết-quả.json"
            args = self._base_args(root) + ["--output-json", str(result_path)]
            stdout = io.StringIO()
            code = main(args, service_factory=_SuccessfulService, stdout=stdout, stderr=io.StringIO())
            saved = OcrResult.model_validate_json(result_path.read_text(encoding="utf-8"))

            second_stdout = io.StringIO()
            second = main(args, service_factory=_SuccessfulService, stdout=second_stdout, stderr=io.StringIO())

        self.assertEqual(code, CliExitCode.SUCCESS)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(saved.business.page1_fields.station.value, "Trạm 220 kV Việt Trì")
        self.assertEqual(second, CliExitCode.OUTPUT)
        self.assertEqual(json.loads(second_stdout.getvalue())["error"]["code"], "CLI_RESULT_EXISTS")

    def test_overwrite_result_atomically_replaces_explicit_result_file(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            result_path = root / "result.json"
            result_path.write_text("old evidence", encoding="utf-8")
            code = main(
                self._base_args(root, correlation_id="cli-overwrite")
                + ["--output-json", str(result_path), "--overwrite-result"],
                service_factory=_SuccessfulService,
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )
            result = OcrResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        self.assertEqual(code, CliExitCode.SUCCESS)
        self.assertEqual(result.correlation_id, "cli-overwrite")

    def test_invalid_request_returns_stable_cli_error_json_and_exit_2(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            stdout = io.StringIO()
            code = main(
                self._base_args(root, correlation_id="unsafe id"),
                service_factory=_SuccessfulService,
                stdout=stdout,
                stderr=io.StringIO(),
            )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, CliExitCode.USAGE_OR_REQUEST)
        self.assertEqual(payload["cli_schema_version"], "1.0")
        self.assertEqual(payload["exit_code"], 2)
        self.assertEqual(payload["error"]["code"], "CLI_REQUEST_INVALID")
        self.assertNotIn(str(root), stdout.getvalue())

    def test_missing_pdf_returns_public_failure_json_and_exit_3(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            stdout = io.StringIO()
            code = main(self._base_args(root), stdout=stdout, stderr=io.StringIO())
            result = OcrResult.model_validate_json(stdout.getvalue())
        self.assertEqual(code, CliExitCode.INPUT)
        self.assertEqual(result.error.code, ErrorCode.INPUT_NOT_FOUND)

    def test_invalid_pdf_returns_public_failure_json_and_exit_3(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "phiếu-chỉnh-định.pdf"
            source.write_bytes(b"not a PDF")
            stdout = io.StringIO()
            code = main(self._base_args(root), stdout=stdout, stderr=io.StringIO())
            result = OcrResult.model_validate_json(stdout.getvalue())
        self.assertEqual(code, CliExitCode.INPUT)
        self.assertEqual(result.error.code, ErrorCode.INVALID_PDF)

    def test_processing_failure_returns_public_failure_json_and_exit_5(self):
        with TemporaryDirectory() as temporary:
            stdout = io.StringIO()
            code = main(
                self._base_args(Path(temporary), correlation_id="cli-pipeline-fail"),
                service_factory=_ProcessingFailureService,
                stdout=stdout,
                stderr=io.StringIO(),
            )
            result = OcrResult.model_validate_json(stdout.getvalue())
        self.assertEqual(code, CliExitCode.PROCESSING)
        self.assertEqual(result.error.code, ErrorCode.INTERNAL_PIPELINE_ERROR)
        self.assertEqual(result.error.stage, ErrorStage.PIPELINE)

    def test_adapter_crash_returns_safe_exit_70_without_leaking_model_output_to_stdout(self):
        with TemporaryDirectory() as temporary:
            stdout = io.StringIO()
            stderr = io.StringIO()
            code = main(
                self._base_args(Path(temporary), correlation_id="cli-adapter-crash"),
                service_factory=_CrashingService,
                stdout=stdout,
                stderr=stderr,
            )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, CliExitCode.INTERNAL)
        self.assertEqual(payload["exit_code"], 70)
        self.assertEqual(payload["error"]["code"], "CLI_INTERNAL_ERROR")
        self.assertNotIn("model output", stdout.getvalue())
        self.assertNotIn("traceback", stdout.getvalue())
        self.assertIn("model output before crash", stderr.getvalue())

    def test_exit_code_mapping_covers_input_output_processing_and_success(self):
        success = _fixture_result(SUCCESS_FIXTURE, "cli-success-map")
        invalid_pdf = _fixture_result(FAILURE_FIXTURE, "cli-input-map")
        output_error = invalid_pdf.model_copy(
            update={"error": invalid_pdf.error.model_copy(update={"code": ErrorCode.OUTPUT_NOT_WRITABLE})}
        )
        processing_error = invalid_pdf.model_copy(
            update={"error": invalid_pdf.error.model_copy(update={"code": ErrorCode.RECOGNITION_FAILED})}
        )
        self.assertEqual(exit_code_for_result(success), CliExitCode.SUCCESS)
        self.assertEqual(exit_code_for_result(invalid_pdf), CliExitCode.INPUT)
        self.assertEqual(exit_code_for_result(output_error), CliExitCode.OUTPUT)
        self.assertEqual(exit_code_for_result(processing_error), CliExitCode.PROCESSING)

    def test_subprocess_entrypoint_success_has_clean_stdout_and_utf8_json(self):
        code = """
import json
from pathlib import Path
import runpy
import src.relay_form_ocr.cli as cli
from src.relay_form_ocr import OcrResult

fixture = Path(__import__('os').environ['OCR_CLI_SUCCESS_FIXTURE'])
class FakeService:
    def process_pdf(self, request):
        print('subprocess model log')
        payload = json.loads(fixture.read_text(encoding='utf-8'))['result']
        result = OcrResult.model_validate(payload)
        return result.model_copy(update={'correlation_id': request.correlation_id})
cli.RelayFormOcrService = FakeService
runpy.run_module('src.relay_form_ocr', run_name='__main__')
"""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = os.environ.copy()
            environment["OCR_CLI_SUCCESS_FIXTURE"] = str(SUCCESS_FIXTURE)
            environment["PYTHONIOENCODING"] = "utf-8"
            completed = subprocess.run(
                [sys.executable, "-c", code, *self._base_args(root, correlation_id="cli-subprocess")],
                cwd=REPOSITORY,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(completed.stdout.splitlines()), 1)
        self.assertEqual(payload["correlation_id"], "cli-subprocess")
        self.assertEqual(payload["business"]["page1_fields"]["station"]["value"], "Trạm 220 kV Việt Trì")
        self.assertNotIn("subprocess model log", completed.stdout)
        self.assertIn("subprocess model log", completed.stderr)

    def test_subprocess_crash_flushes_model_output_to_stderr_before_safe_exit_70(self):
        code = """
import runpy
import src.relay_form_ocr.cli as cli
class FakeService:
    def process_pdf(self, request):
        print('buffered model output before failure')
        raise RuntimeError('private traceback')
cli.RelayFormOcrService = FakeService
runpy.run_module('src.relay_form_ocr', run_name='__main__')
"""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            completed = subprocess.run(
                [sys.executable, "-c", code, *self._base_args(root, correlation_id="cli-subprocess-crash")],
                cwd=REPOSITORY,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 70)
        self.assertEqual(payload["error"]["code"], "CLI_INTERNAL_ERROR")
        self.assertNotIn("buffered model output", completed.stdout)
        self.assertNotIn("traceback", completed.stdout)
        self.assertIn("buffered model output before failure", completed.stderr)

    @unittest.skipUnless(shutil.which("powershell"), "PowerShell is required for the platform contract test")
    def test_powershell_convertfrom_json_preserves_unicode_error_text_and_path_arguments(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "dữ-liệu" / "phiếu-không-tồn-tại.pdf"
            output_root = root / "kết-quả"
            powershell = shutil.which("powershell")
            script = (
                "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
                "$env:PYTHONIOENCODING='utf-8'; "
                f"$raw=& '{sys.executable}' -m src.relay_form_ocr --input '{missing}' "
                f"--output-root '{output_root}' --correlation-id 'cli-powershell' --json 2>$null; "
                "$native=$LASTEXITCODE; $value=$raw | ConvertFrom-Json; "
                "if($native -ne 3){exit 21}; "
                "if($value.error.message -ne 'Không tìm thấy tệp PDF đầu vào.'){exit 22}; "
                "if($value.correlation_id -ne 'cli-powershell'){exit 23}; "
                "Write-Output $value.error.message"
            )
            completed = subprocess.run(
                [powershell, "-NoProfile", "-Command", script],
                cwd=REPOSITORY,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Không tìm thấy tệp PDF đầu vào.", completed.stdout)

    def test_visual_report_is_utf8_vietnamese_and_documents_streams_and_exit_codes(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "cli_review.html"
            result = _fixture_result(SUCCESS_FIXTURE, "cli-visual")
            render_cli_review(output, result)
            html = output.read_text(encoding="utf-8")
        self.assertIn('<html lang="vi">', html)
        self.assertIn("Kiểm thử trực quan CLI JSON cục bộ", html)
        self.assertIn("Tách luồng máy và luồng vận hành", html)
        self.assertIn("stdout — dữ liệu cho máy", html)
        self.assertIn("stderr — log vận hành", html)
        self.assertIn("Bảng exit code", html)
        self.assertIn("Kiểm tra Unicode trên PowerShell", html)
        for code in (0, 2, 3, 4, 5, 70):
            self.assertIn(f"<strong>{code}</strong>", html)


if __name__ == "__main__":
    unittest.main()
