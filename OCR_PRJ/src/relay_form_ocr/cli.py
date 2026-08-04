"""Local JSON subprocess adapter for the synchronous relay-form OCR service."""

from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stdout
from enum import IntEnum
import inspect
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Iterator, TextIO
from uuid import uuid4

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from pydantic import ValidationError

from .observability import stream_logger
from .schemas import ErrorCode, OcrRequest, OcrResult, ProcessingStatus
from .service import RelayFormOcrService


CLI_SCHEMA_VERSION = "1.0"


class CliExitCode(IntEnum):
    """Stable process exit codes published by the local adapter."""

    SUCCESS = 0
    USAGE_OR_REQUEST = 2
    INPUT = 3
    OUTPUT = 4
    PROCESSING = 5
    INTERNAL = 70


class CliUsageError(ValueError):
    """Raised instead of allowing argparse to print non-JSON failures."""


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(
        description="Process one local PDF_x and emit the public OCR result as JSON.",
    )
    parser.add_argument("--input", required=True, type=Path, help="Path to exactly one PDF_x")
    parser.add_argument("--output-root", required=True, type=Path, help="Root for OCR artifacts")
    parser.add_argument("--correlation-id", required=True, help="Safe caller correlation identifier")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Compatibility flag; JSON is always the adapter format",
    )
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Sử dụng GPU (CUDA) để tăng tốc phát hiện và nhận dạng OCR",
    )
    parser.add_argument(
        "--stage",
        choices=["all", "header", "details"],
        default="all",
        help="Giai đoạn bóc tách: all (mặc định), header (trang 1 & 2), details (trang 3+)",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Write UTF-8 JSON to this file instead of stdout",
    )
    parser.add_argument(
        "--overwrite-result",
        action="store_true",
        help="Allow atomic replacement of an existing --output-json file",
    )
    return parser


def parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    args = build_parser().parse_args(argv)
    if args.overwrite_result and args.output_json is None:
        raise CliUsageError("--overwrite-result requires --output-json")
    return args


def _absolute(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _cli_error_payload(code: str, message: str, exit_code: CliExitCode) -> str:
    payload = {
        "cli_schema_version": CLI_SCHEMA_VERSION,
        "status": "failed",
        "exit_code": int(exit_code),
        "error": {
            "code": code,
            "message": message,
            "retryable": False,
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _write_stdout_json(payload: str, stream: TextIO) -> None:
    data = (payload + "\n").encode("utf-8")
    binary = getattr(stream, "buffer", None)
    if binary is not None:
        binary.write(data)
        binary.flush()
    else:
        stream.write(data.decode("utf-8"))
        stream.flush()


def _log(stream: TextIO, message: str) -> None:
    # Adapter logs deliberately stay ASCII-safe for legacy Windows consoles.
    stream.write(f"relay_form_ocr: {message}\n")
    stream.flush()


@contextmanager
def isolate_machine_stdout(stdout: TextIO, stderr: TextIO) -> Iterator[None]:
    """Route Python and native fd-level service output to stderr temporarily."""

    try:
        stdout.flush()
        stderr.flush()
        stdout_fd = stdout.fileno()
        stderr_fd = stderr.fileno()
        saved_stdout_fd = os.dup(stdout_fd)
    except (AttributeError, OSError, ValueError):
        with redirect_stdout(stderr):
            yield
        return

    try:
        os.dup2(stderr_fd, stdout_fd)
        yield
    finally:
        try:
            stdout.flush()
        finally:
            os.dup2(saved_stdout_fd, stdout_fd)
            os.close(saved_stdout_fd)


def _write_result_file(path: Path, payload: str, *, overwrite: bool) -> None:
    target = _absolute(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise FileExistsError("result file already exists")
    if target.is_dir():
        raise IsADirectoryError("result path is a directory")

    text = payload + "\n"
    if not overwrite:
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        return

    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


_INPUT_ERRORS = {
    ErrorCode.INVALID_REQUEST,
    ErrorCode.INPUT_NOT_FOUND,
    ErrorCode.INPUT_NOT_FILE,
    ErrorCode.UNSUPPORTED_INPUT_KIND,
    ErrorCode.INVALID_PDF,
}
_OUTPUT_ERRORS = {
    ErrorCode.OUTPUT_NOT_WRITABLE,
    ErrorCode.ARTIFACT_WRITE_FAILED,
}


def exit_code_for_result(result: OcrResult) -> CliExitCode:
    if result.status != ProcessingStatus.FAILED:
        return CliExitCode.SUCCESS
    if result.error is None:
        return CliExitCode.INTERNAL
    if result.error.code in _INPUT_ERRORS:
        return CliExitCode.INPUT
    if result.error.code in _OUTPUT_ERRORS:
        return CliExitCode.OUTPUT
    return CliExitCode.PROCESSING


ServiceFactory = Callable[[], RelayFormOcrService]


def main(
    argv: list[str] | None = None,
    *,
    service_factory: ServiceFactory | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    machine_stdout = stdout if stdout is not None else sys.stdout
    log_stream = stderr if stderr is not None else sys.stderr

    try:
        args = parse_cli_args(argv)
    except CliUsageError:
        code = CliExitCode.USAGE_OR_REQUEST
        _log(log_stream, "invalid command-line arguments")
        _write_stdout_json(
            _cli_error_payload("CLI_USAGE_ERROR", "Invalid command-line arguments.", code),
            machine_stdout,
        )
        return int(code)

    input_pdf = _absolute(args.input)
    output_root = _absolute(args.output_root)
    output_json = _absolute(args.output_json) if args.output_json is not None else None
    if output_json is not None and output_json == input_pdf:
        code = CliExitCode.USAGE_OR_REQUEST
        _log(log_stream, "result path must differ from input PDF")
        _write_stdout_json(
            _cli_error_payload("CLI_INVALID_COMBINATION", "Result path must differ from input PDF.", code),
            machine_stdout,
        )
        return int(code)
    if output_json is not None and output_json.exists() and not args.overwrite_result:
        code = CliExitCode.OUTPUT
        _log(log_stream, "result file exists; refusing to overwrite")
        _write_stdout_json(
            _cli_error_payload("CLI_RESULT_EXISTS", "Result file already exists.", code),
            machine_stdout,
        )
        return int(code)

    try:
        request = OcrRequest(
            input_pdf=input_pdf,
            output_root=output_root,
            correlation_id=args.correlation_id,
        )
    except ValidationError:
        code = CliExitCode.USAGE_OR_REQUEST
        _log(log_stream, "request validation failed")
        _write_stdout_json(
            _cli_error_payload("CLI_REQUEST_INVALID", "OCR request validation failed.", code),
            machine_stdout,
        )
        return int(code)

    _log(log_stream, f"start correlation_id={request.correlation_id}")
    if getattr(args, "stage", "all") in ("header", "details"):
        from .orchestrator import DocumentOcrOrchestrator, PdfCandidate
        from src.pdf_form_splitter.pdf_io import pdf_page_count

        if not input_pdf.exists():
            code = CliExitCode.INPUT
            _log(log_stream, "input PDF not found")
            _write_stdout_json(
                _cli_error_payload("INPUT_NOT_FOUND", "Không tìm thấy tệp PDF đầu vào.", code),
                machine_stdout,
            )
            return int(code)

        try:
            page_count = pdf_page_count(input_pdf)
        except Exception:
            code = CliExitCode.INPUT
            _log(log_stream, "invalid PDF input")
            _write_stdout_json(
                _cli_error_payload("INVALID_PDF", "Không thể đọc tệp PDF đầu vào.", code),
                machine_stdout,
            )
            return int(code)

        candidate = PdfCandidate(
            candidate_id=f"doc_{request.correlation_id}",
            name=input_pdf.name,
            path=str(input_pdf),
            page_count=page_count,
            origin="cli",
        )
        orchestrator = DocumentOcrOrchestrator(use_gpu=args.gpu)
        workspace_dir = output_root / request.correlation_id

        def _cli_progress(curr: int, total: int, msg: str) -> None:
            _log(log_stream, f"progress: trang {curr}/{total} - {msg}")

        try:
            with isolate_machine_stdout(machine_stdout, log_stream):
                raw_res = orchestrator.extract_pdf_x(candidate, workspace_dir, stage=args.stage, progress=_cli_progress)

            if args.stage == "header":
                p1_fields = {}
                for k, v in raw_res.get("important_fields", {}).items():
                    p1_fields[k] = {"value": v}

                payload_dict = {
                    "stage": "header",
                    "status": "success",
                    "correlation_id": request.correlation_id,
                    "business": {
                        "page1_fields": p1_fields,
                        "important_source_labels": raw_res.get("important_source_labels", {}),
                        "important_field_resolution": raw_res.get("important_field_resolution", {}),
                    },
                    "pages": raw_res.get("pages", []),
                    "warnings": raw_res.get("warnings", []),
                    "summary": raw_res.get("summary", {}),
                }
            else:  # details
                payload_dict = {
                    "stage": "details",
                    "status": "success",
                    "correlation_id": request.correlation_id,
                    "business": {
                        "setting_records": raw_res.get("setting_records", []),
                        "note_candidates": raw_res.get("note_candidates", []),
                    },
                    "pages": raw_res.get("pages", []),
                    "warnings": raw_res.get("warnings", []),
                    "summary": raw_res.get("summary", {}),
                }
            payload = json.dumps(payload_dict, ensure_ascii=False, indent=2)
            code = CliExitCode.SUCCESS
        except Exception as exc:
            code = CliExitCode.PROCESSING
            _log(log_stream, f"stage {args.stage} extraction failed: {exc}")
            _write_stdout_json(
                _cli_error_payload("PROCESSING_FAILED", f"Lỗi bóc tách giai đoạn {args.stage}: {str(exc)}", code),
                machine_stdout,
            )
            return int(code)
    else:
        if service_factory is None:
            service_logger = stream_logger(
                log_stream,
                name=f"relay_form_ocr.cli.{request.correlation_id}",
            )
            try:
                service_parameters = inspect.signature(RelayFormOcrService).parameters.values()
                accepts_logger = any(
                    parameter.name == "logger" or parameter.kind == inspect.Parameter.VAR_KEYWORD
                    for parameter in service_parameters
                )
                accepts_gpu = any(
                    parameter.name == "use_gpu" or parameter.kind == inspect.Parameter.VAR_KEYWORD
                    for parameter in service_parameters
                )
            except (TypeError, ValueError):
                accepts_logger = False
                accepts_gpu = False

            def _create_service() -> RelayFormOcrService:
                kwargs: dict[str, Any] = {}
                if accepts_logger:
                    kwargs["logger"] = service_logger
                if accepts_gpu:
                    kwargs["use_gpu"] = args.gpu
                return RelayFormOcrService(**kwargs)

            factory = _create_service
        else:
            factory = service_factory
        try:
            with isolate_machine_stdout(machine_stdout, log_stream):
                result = factory().process_pdf(request)
            if not isinstance(result, OcrResult):
                raise TypeError("service did not return OcrResult")
            payload = result.model_dump_json()
        except Exception:
            code = CliExitCode.INTERNAL
            _log(log_stream, "internal adapter failure")
            _write_stdout_json(
                _cli_error_payload("CLI_INTERNAL_ERROR", "The local CLI adapter failed.", code),
                machine_stdout,
            )
            return int(code)

        code = exit_code_for_result(result)
    if output_json is None:
        _write_stdout_json(payload, machine_stdout)
    else:
        try:
            _write_result_file(output_json, payload, overwrite=args.overwrite_result)
        except (OSError, ValueError):
            code = CliExitCode.OUTPUT
            _log(log_stream, "could not write result JSON")
            _write_stdout_json(
                _cli_error_payload("CLI_RESULT_WRITE_FAILED", "Could not write result JSON.", code),
                machine_stdout,
            )
            return int(code)

    # Ghi log kết thúc — chỉ nhánh `all` mới có biến `result`
    if getattr(args, "stage", "all") not in ("header", "details"):
        _log(log_stream, f"finish correlation_id={request.correlation_id} status={result.status.value} exit={int(code)}")
    else:
        _log(log_stream, f"finish correlation_id={request.correlation_id} stage={args.stage} exit={int(code)}")
    return int(code)


__all__ = [
    "CLI_SCHEMA_VERSION",
    "CliExitCode",
    "CliUsageError",
    "build_parser",
    "exit_code_for_result",
    "isolate_machine_stdout",
    "main",
    "parse_cli_args",
]
