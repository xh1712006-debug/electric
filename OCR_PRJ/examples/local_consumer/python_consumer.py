"""Reference management-system consumer using only the public Python API."""

from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Iterator, Sequence, TextIO
from uuid import uuid4

from src.relay_form_ocr import (
    OcrRequest,
    OcrResult,
    ProcessingStatus,
    RelayFormOcrService,
    ReviewStatus,
)


CONSUMER_SCHEMA_VERSION = "1.0"
EXIT_READY = 0
EXIT_INVALID_REQUEST = 2
EXIT_REVIEW_REQUIRED = 10
EXIT_OCR_FAILED = 20
EXIT_CONSUMER_FAILURE = 21


class ConsumerIntegrityError(RuntimeError):
    """Raised when public result or physical artifacts fail consumer checks."""


@dataclass(frozen=True, slots=True)
class ConsumerRun:
    result: OcrResult
    summary: dict[str, Any]
    exit_code: int


@contextmanager
def isolate_consumer_stdout(stdout: TextIO, stderr: TextIO) -> Iterator[None]:
    """Route Python and native model output away from the summary stream."""

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
        with redirect_stdout(stderr):
            yield
    finally:
        try:
            stdout.flush()
            stderr.flush()
        finally:
            os.dup2(saved_stdout_fd, stdout_fd)
            os.close(saved_stdout_fd)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_artifact_path(output_root: Path, relative_path: str) -> Path:
    if "\\" in relative_path:
        raise ConsumerIntegrityError("artifact_path_not_portable")
    portable = PurePosixPath(relative_path)
    if portable.is_absolute() or not portable.parts or any(
        part in {"", ".", ".."} for part in portable.parts
    ):
        raise ConsumerIntegrityError("artifact_path_not_relative")
    root = output_root.resolve()
    candidate = root.joinpath(*portable.parts).resolve()
    try:
        common = Path(os.path.commonpath((str(root), str(candidate))))
    except ValueError as exc:
        raise ConsumerIntegrityError("artifact_path_outside_output_root") from exc
    if os.path.normcase(str(common)) != os.path.normcase(str(root)):
        raise ConsumerIntegrityError("artifact_path_outside_output_root")
    return candidate


def audit_artifact_manifest(result: OcrResult, output_root: Path) -> dict[str, Any]:
    """Verify every public artifact and read the physical manifest without private imports."""

    artifacts = list(result.artifact_manifest.artifacts)
    if not artifacts:
        return {
            "available": False,
            "workspace_id_match": True,
            "status_match": True,
            "source_unchanged": None,
            "declared_payload_count": 0,
            "public_artifact_count": 0,
            "verified_artifact_count": 0,
            "all_verified": True,
        }

    verified = 0
    for artifact in artifacts:
        path = _safe_artifact_path(output_root, artifact.relative_path)
        if not path.is_file() or path.is_symlink():
            raise ConsumerIntegrityError("artifact_missing_or_not_regular")
        if path.stat().st_size != artifact.size_bytes:
            raise ConsumerIntegrityError("artifact_size_mismatch")
        if _sha256(path) != artifact.sha256:
            raise ConsumerIntegrityError("artifact_checksum_mismatch")
        verified += 1

    manifest_artifacts = [item for item in artifacts if item.kind == "artifact_manifest"]
    if len(manifest_artifacts) != 1:
        raise ConsumerIntegrityError("physical_manifest_count_invalid")
    manifest_path = _safe_artifact_path(output_root, manifest_artifacts[0].relative_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConsumerIntegrityError("physical_manifest_unreadable") from exc
    if not isinstance(manifest, dict) or set(manifest) != {
        "manifest_schema_version",
        "workspace_id",
        "status",
        "source",
        "artifacts",
    }:
        raise ConsumerIntegrityError("physical_manifest_shape_invalid")

    expected_status = "failed" if result.status == ProcessingStatus.FAILED else "completed"
    workspace_match = manifest.get("workspace_id") == result.artifact_manifest.workspace_id
    status_match = manifest.get("status") == expected_status
    source = manifest.get("source")
    source_unchanged = source.get("unchanged") if isinstance(source, dict) else None
    declared = manifest.get("artifacts")
    if not workspace_match:
        raise ConsumerIntegrityError("physical_manifest_workspace_mismatch")
    if not status_match:
        raise ConsumerIntegrityError("physical_manifest_status_mismatch")
    if source_unchanged is not True:
        raise ConsumerIntegrityError("source_immutability_not_confirmed")
    if not isinstance(declared, list):
        raise ConsumerIntegrityError("physical_manifest_artifacts_invalid")

    expected_payload = [
        item.model_dump(mode="json") for item in artifacts if item.kind != "artifact_manifest"
    ]
    if declared != expected_payload:
        raise ConsumerIntegrityError("physical_manifest_public_result_mismatch")
    return {
        "available": True,
        "workspace_id_match": workspace_match,
        "status_match": status_match,
        "source_unchanged": source_unchanged,
        "declared_payload_count": len(declared),
        "public_artifact_count": len(artifacts),
        "verified_artifact_count": verified,
        "all_verified": True,
    }


def _progress_summary(events: Sequence[Any]) -> dict[str, Any]:
    terminal = [event for event in events if getattr(event, "terminal", False)]
    final = events[-1] if events else None
    return {
        "event_count": len(events),
        "terminal_count": len(terminal),
        "final_completed": getattr(final, "completed", None),
        "final_total": getattr(final, "total", None),
    }


def _public_error(result: OcrResult) -> dict[str, Any] | None:
    if result.error is None:
        return None
    return {
        "code": result.error.code.value,
        "stage": result.error.stage.value,
        "retryable": result.error.retryable,
    }


def _summary(
    result: OcrResult,
    *,
    outcome: str,
    manifest_audit: dict[str, Any],
    progress: dict[str, Any],
    consumer_error: str | None = None,
) -> dict[str, Any]:
    return {
        "consumer_schema_version": CONSUMER_SCHEMA_VERSION,
        "correlation_id": result.correlation_id,
        "schema_version": result.schema_version,
        "pipeline_version": result.pipeline_version,
        "outcome": outcome,
        "processing_status": result.status.value,
        "review_status": result.review_status.value,
        "page_count": result.document.page_count if result.document is not None else len(result.pages),
        "warning_count": len(result.warnings),
        "artifact_count": len(result.artifact_manifest.artifacts),
        "manifest_audit": manifest_audit,
        "progress": progress,
        "public_error": _public_error(result),
        "consumer_error": consumer_error,
    }


def consume_document(
    request: OcrRequest,
    *,
    service: RelayFormOcrService | None = None,
) -> ConsumerRun:
    """Call the public service, validate v1 and apply a conservative review gate."""

    events: list[Any] = []
    runtime = service or RelayFormOcrService()
    result = runtime.process_pdf(request, progress=events.append)
    if not isinstance(result, OcrResult):
        raise ConsumerIntegrityError("service_did_not_return_ocr_result")
    result = OcrResult.model_validate_json(result.model_dump_json())
    progress = _progress_summary(events)
    try:
        manifest_audit = audit_artifact_manifest(result, request.output_root)
    except ConsumerIntegrityError as exc:
        summary = _summary(
            result,
            outcome="consumer_failure",
            manifest_audit={"available": bool(result.artifact_manifest.artifacts), "all_verified": False},
            progress=progress,
            consumer_error=str(exc),
        )
        return ConsumerRun(result=result, summary=summary, exit_code=EXIT_CONSUMER_FAILURE)

    if result.status == ProcessingStatus.FAILED:
        outcome = "failed"
        exit_code = EXIT_OCR_FAILED
    elif result.review_status == ReviewStatus.REVIEW_REQUIRED:
        outcome = "manual_review_required"
        exit_code = EXIT_REVIEW_REQUIRED
    else:
        outcome = "ready_for_use"
        exit_code = EXIT_READY
    return ConsumerRun(
        result=result,
        summary=_summary(
            result,
            outcome=outcome,
            manifest_audit=manifest_audit,
            progress=progress,
        ),
        exit_code=exit_code,
    )


def _write_summary(path: Path, payload: dict[str, Any], *, overwrite: bool) -> None:
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise ConsumerIntegrityError("summary_file_exists")
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _invalid_request_summary(correlation_id: str | None) -> dict[str, Any]:
    return {
        "consumer_schema_version": CONSUMER_SCHEMA_VERSION,
        "correlation_id": correlation_id,
        "outcome": "consumer_failure",
        "consumer_error": "invalid_consumer_request",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Consumer mẫu cho local OCR API v1.")
    parser.add_argument("--input", required=True, type=Path, help="Đường dẫn tới một PDF_x.")
    parser.add_argument("--output-root", required=True, type=Path, help="Root chứa workspace OCR.")
    parser.add_argument("--correlation-id", required=True, help="Mã tương quan duy nhất.")
    parser.add_argument("--summary-json", type=Path, help="Tùy chọn lưu summary UTF-8.")
    parser.add_argument("--overwrite-summary", action="store_true", help="Cho phép ghi đè summary.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        request = OcrRequest(
            input_pdf=args.input.resolve(),
            output_root=args.output_root.resolve(),
            correlation_id=args.correlation_id,
        )
    except Exception:
        payload = _invalid_request_summary(getattr(args, "correlation_id", None))
        code = EXIT_INVALID_REQUEST
    else:
        try:
            with isolate_consumer_stdout(sys.stdout, sys.stderr):
                run = consume_document(request)
            payload = run.summary
            code = run.exit_code
            if args.summary_json is not None:
                _write_summary(args.summary_json, payload, overwrite=args.overwrite_summary)
        except Exception:
            payload = {
                "consumer_schema_version": CONSUMER_SCHEMA_VERSION,
                "correlation_id": request.correlation_id,
                "outcome": "consumer_failure",
                "consumer_error": "consumer_runtime_failure",
            }
            code = EXIT_CONSUMER_FAILURE
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
