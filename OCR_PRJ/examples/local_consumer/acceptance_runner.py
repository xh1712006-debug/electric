"""Portable per-PDF acceptance runner built only on the public OCR API."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence
from uuid import uuid4

from src.relay_form_ocr import (
    ErrorCode,
    OcrRequest,
    OcrResult,
    ProcessingStatus,
    RelayFormOcrService,
)

from .python_consumer import (
    CONSUMER_SCHEMA_VERSION,
    ConsumerRun,
    _safe_artifact_path,
    audit_artifact_manifest,
    consume_document,
    isolate_consumer_stdout,
)


ACCEPTANCE_SCHEMA_VERSION = "1.0"
RUNNER_VERSION = "1.0.0"
EXIT_ACCEPTANCE_FAILED = 30
EXIT_EVIDENCE_INVALID = 31
EXIT_GPU_UNAVAILABLE = 40
_SAFE_ID = re.compile(r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$")
_CORRUPT_CASE_ID = "invalid-corrupt-pdf"


class AcceptanceConfigurationError(ValueError):
    """Raised before an acceptance workspace is created."""


class AcceptanceEvidenceError(ValueError):
    """Raised when a copied evidence bundle is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class AcceptanceCase:
    case_id: str
    layout_family: str
    display_name: str
    input_pdf: str
    repeat: int


@dataclass(frozen=True, slots=True)
class AcceptanceCorpus:
    suite_id: str
    description: str
    required_layout_families: tuple[str, ...]
    cases: tuple[AcceptanceCase, ...]
    source_sha256: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _portable_pdf(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise AcceptanceConfigurationError(f"{field} phải là đường dẫn POSIX tương đối")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise AcceptanceConfigurationError(f"{field} không được thoát khỏi input root")
    if path.suffix.casefold() != ".pdf":
        raise AcceptanceConfigurationError(f"{field} phải có đuôi .pdf")
    return path.as_posix()


def _identifier(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise AcceptanceConfigurationError(
            f"{field} chỉ nhận chữ thường ASCII, số, '-' hoặc '_'"
        )
    return value


def load_corpus(path: Path | str) -> AcceptanceCorpus:
    """Load the portable corpus without resolving inputs against the repository."""

    source = Path(path).resolve()
    try:
        raw = source.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcceptanceConfigurationError("Không đọc được corpus JSON UTF-8") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "acceptance_schema_version",
        "suite_id",
        "description",
        "required_layout_families",
        "cases",
    }:
        raise AcceptanceConfigurationError("Corpus phải có đúng các field v1")
    if payload["acceptance_schema_version"] != ACCEPTANCE_SCHEMA_VERSION:
        raise AcceptanceConfigurationError("acceptance_schema_version không được hỗ trợ")
    suite_id = _identifier(payload["suite_id"], field="suite_id")
    description = payload["description"]
    if not isinstance(description, str) or not description.strip():
        raise AcceptanceConfigurationError("description không được rỗng")
    families = payload["required_layout_families"]
    if not isinstance(families, list) or not families:
        raise AcceptanceConfigurationError("required_layout_families phải là danh sách")
    required = tuple(_identifier(item, field="layout_family") for item in families)
    if len(required) != len(set(required)):
        raise AcceptanceConfigurationError("required_layout_families không được trùng")
    values = payload["cases"]
    if not isinstance(values, list) or not values:
        raise AcceptanceConfigurationError("cases phải là danh sách không rỗng")
    cases: list[AcceptanceCase] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict) or set(item) != {
            "case_id",
            "layout_family",
            "display_name",
            "input_pdf",
            "repeat",
        }:
            raise AcceptanceConfigurationError(f"cases[{index}] không đúng schema v1")
        case_id = _identifier(item["case_id"], field=f"cases[{index}].case_id")
        family = _identifier(item["layout_family"], field=f"cases[{index}].layout_family")
        display_name = item["display_name"]
        repeat = item["repeat"]
        if family not in required:
            raise AcceptanceConfigurationError(f"case {case_id} dùng layout family chưa khai báo")
        if not isinstance(display_name, str) or not display_name.strip():
            raise AcceptanceConfigurationError(f"case {case_id} thiếu display_name")
        if not isinstance(repeat, int) or isinstance(repeat, bool) or not 1 <= repeat <= 5:
            raise AcceptanceConfigurationError(f"case {case_id} repeat phải nằm trong 1..5")
        cases.append(
            AcceptanceCase(
                case_id=case_id,
                layout_family=family,
                display_name=display_name.strip(),
                input_pdf=_portable_pdf(item["input_pdf"], field=f"cases[{index}].input_pdf"),
                repeat=repeat,
            )
        )
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise AcceptanceConfigurationError("case_id không được trùng")
    uncovered = set(required) - {case.layout_family for case in cases}
    if uncovered:
        raise AcceptanceConfigurationError(
            "Chưa có PDF cho layout family: " + ", ".join(sorted(uncovered))
        )
    return AcceptanceCorpus(
        suite_id=suite_id,
        description=description.strip(),
        required_layout_families=required,
        cases=tuple(cases),
        source_sha256=hashlib.sha256(raw).hexdigest(),
    )


def resolve_inputs(corpus: AcceptanceCorpus, input_root: Path | str) -> dict[str, Path]:
    root = Path(input_root).resolve()
    if not root.is_dir():
        raise AcceptanceConfigurationError("input root không tồn tại hoặc không phải thư mục")
    resolved: dict[str, Path] = {}
    for case in corpus.cases:
        candidate = root.joinpath(*PurePosixPath(case.input_pdf).parts).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise AcceptanceConfigurationError(f"case {case.case_id} thoát khỏi input root") from exc
        if not candidate.is_file() or candidate.is_symlink():
            raise AcceptanceConfigurationError(f"Thiếu PDF regular file cho case {case.case_id}")
        resolved[case.case_id] = candidate
    return resolved


def probe_runtime(device: str) -> dict[str, Any]:
    """Record reproducible runtime facts and fail closed for an unusable GPU stack."""

    if device not in {"cpu", "gpu"}:
        raise AcceptanceConfigurationError("device phải là cpu hoặc gpu")
    packages = {}
    for name in ("pydantic", "paddleocr", "paddlepaddle", "torch", "vietocr"):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    result: dict[str, Any] = {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "requested_device": device,
        "packages": packages,
        "gpu": None,
    }
    if device == "cpu":
        return result
    try:
        import torch  # PyTorch must be imported before Paddle on Windows.

        torch_available = bool(torch.cuda.is_available())
        torch_count = int(torch.cuda.device_count()) if torch_available else 0
        torch_name = torch.cuda.get_device_name(0) if torch_count else None
        import paddle

        paddle_cuda = bool(paddle.is_compiled_with_cuda())
        paddle_count = int(paddle.device.cuda.device_count()) if paddle_cuda else 0
    except Exception as exc:
        raise AcceptanceConfigurationError("Không khởi tạo được CUDA preflight") from exc
    result["gpu"] = {
        "torch_cuda_available": torch_available,
        "torch_device_count": torch_count,
        "torch_device_name": torch_name,
        "paddle_cuda_build": paddle_cuda,
        "paddle_device_count": paddle_count,
    }
    if not torch_available or torch_count < 1 or not paddle_cuda or paddle_count < 1:
        raise AcceptanceConfigurationError(
            "GPU mode cần đồng thời PyTorch CUDA và PaddlePaddle CUDA hoạt động"
        )
    return result


def _repository_revision() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
            text=True, encoding="utf-8", check=True, timeout=10,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, capture_output=True,
            text=True, encoding="utf-8", check=True, timeout=10,
        ).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}
    return {"commit": commit, "dirty": dirty}


def build_execution_plan(corpus: AcceptanceCorpus, run_id: str) -> list[dict[str, Any]]:
    run_id = _identifier(run_id, field="run_id")
    plan = []
    for case in corpus.cases:
        for attempt in range(1, case.repeat + 1):
            correlation = f"{run_id}-{case.case_id}-r{attempt:02d}"
            if len(correlation) > 128:
                raise AcceptanceConfigurationError("correlation ID sinh ra dài quá 128 ký tự")
            plan.append({
                "execution_id": f"{case.case_id}-r{attempt:02d}",
                "case_id": case.case_id,
                "layout_family": case.layout_family,
                "display_name": case.display_name,
                "input_pdf": case.input_pdf,
                "attempt": attempt,
                "expected": "processed",
                "correlation_id": correlation,
            })
    plan.append({
        "execution_id": f"{_CORRUPT_CASE_ID}-r01",
        "case_id": _CORRUPT_CASE_ID,
        "layout_family": "failure-contract",
        "display_name": "PDF hỏng — kiểm tra contract lỗi",
        "input_pdf": "generated/corrupt.pdf",
        "attempt": 1,
        "expected": "invalid_pdf",
        "correlation_id": f"{run_id}-{_CORRUPT_CASE_ID}-r01",
    })
    return plan


def _stable_result(result: OcrResult) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    for key in ("correlation_id", "timing", "artifact_manifest"):
        payload.pop(key, None)
    return payload


def _relative_file(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _persist_run_evidence(
    suite_root: Path,
    artifact_root: Path,
    execution_id: str,
    run: ConsumerRun,
) -> dict[str, Any]:
    result_path = suite_root / "results" / f"{execution_id}.ocr_result.json"
    summary_path = suite_root / "summaries" / f"{execution_id}.summary.json"
    _atomic_json(result_path, run.result.model_dump(mode="json"))
    _atomic_json(summary_path, run.summary)
    evidence: dict[str, Any] = {
        "result_file": _relative_file(suite_root, result_path),
        "result_sha256": _sha256(result_path),
        "summary_file": _relative_file(suite_root, summary_path),
        "summary_sha256": _sha256(summary_path),
        "physical_manifest_file": None,
        "physical_manifest_sha256": None,
    }
    physical = [
        item for item in run.result.artifact_manifest.artifacts
        if item.kind == "artifact_manifest"
    ]
    if len(physical) == 1:
        source = _safe_artifact_path(artifact_root, physical[0].relative_path)
        target = suite_root / "physical_manifests" / f"{execution_id}.artifact_manifest.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        evidence["physical_manifest_file"] = _relative_file(suite_root, target)
        evidence["physical_manifest_sha256"] = _sha256(target)
    return evidence


def _execution_record(
    planned: Mapping[str, Any],
    source: Path,
    artifact_root: Path,
    suite_root: Path,
    service: RelayFormOcrService,
) -> dict[str, Any]:
    source_before = _sha256(source)
    started_at = _utc_now()
    started_clock = time.perf_counter()
    request = OcrRequest(
        input_pdf=source.resolve(),
        output_root=artifact_root.resolve(),
        correlation_id=str(planned["correlation_id"]),
    )
    try:
        run = consume_document(request, service=service)
    except Exception:
        return {
            **dict(planned),
            "started_at_utc": started_at,
            "completed_at_utc": _utc_now(),
            "elapsed_ms": round((time.perf_counter() - started_clock) * 1000, 3),
            "verdict": "failed",
            "reason": "consumer_runtime_failure",
            "source_sha256_before": source_before,
            "source_sha256_after": _sha256(source),
            "source_unchanged": source_before == _sha256(source),
            "runner_error": "consumer_runtime_failure",
        }
    source_after = _sha256(source)
    evidence = _persist_run_evidence(
        suite_root, artifact_root, str(planned["execution_id"]), run
    )
    expected = planned["expected"]
    audit = run.summary.get("manifest_audit", {})
    if expected == "invalid_pdf":
        passed = (
            run.result.status == ProcessingStatus.FAILED
            and run.result.error is not None
            and run.result.error.code == ErrorCode.INVALID_PDF
            and run.result.error.retryable is False
            and source_before == source_after
        )
        reason = "invalid_pdf_contract_confirmed" if passed else "invalid_pdf_contract_mismatch"
    else:
        passed = (
            run.result.status != ProcessingStatus.FAILED
            and audit.get("all_verified") is True
            and audit.get("source_unchanged") is True
            and source_before == source_after
        )
        reason = "contract_artifacts_and_source_valid" if passed else "processed_acceptance_failed"
    warnings = [
        {"code": item.code, "page_number": item.page_number, "message": item.message}
        for item in run.result.warnings
    ]
    return {
        **dict(planned),
        "started_at_utc": started_at,
        "completed_at_utc": _utc_now(),
        "elapsed_ms": round((time.perf_counter() - started_clock) * 1000, 3),
        "pipeline_elapsed_ms": run.result.timing.elapsed_ms,
        "verdict": "passed" if passed else "failed",
        "reason": reason,
        "consumer_exit_code": run.exit_code,
        "consumer_outcome": run.summary["outcome"],
        "schema_version": run.result.schema_version,
        "pipeline_version": run.result.pipeline_version,
        "processing_status": run.result.status.value,
        "review_status": run.result.review_status.value,
        "page_count": run.summary["page_count"],
        "warning_count": len(warnings),
        "warnings": warnings,
        "artifact_count": run.summary["artifact_count"],
        "artifact_audit": audit,
        "progress": run.summary["progress"],
        "public_error": run.summary["public_error"],
        "workspace_id": run.result.artifact_manifest.workspace_id,
        "source_sha256_before": source_before,
        "source_sha256_after": source_after,
        "source_unchanged": source_before == source_after,
        "stable_result_sha256": _json_sha256(_stable_result(run.result)),
        **evidence,
    }


def _derive_summary(manifest: Mapping[str, Any]) -> dict[str, Any]:
    records = list(manifest.get("executions", []))
    plan = list(manifest.get("execution_plan", []))
    completed_ids = {item.get("execution_id") for item in records}
    plan_ids = {item.get("execution_id") for item in plan}
    execution_failures = [item["execution_id"] for item in records if item.get("verdict") != "passed"]
    repeatability = []
    for case_id in sorted({item["case_id"] for item in plan if item["expected"] == "processed"}):
        planned = [item for item in plan if item["case_id"] == case_id]
        if len(planned) < 2:
            continue
        actual = [item for item in records if item.get("case_id") == case_id]
        hashes = [item.get("stable_result_sha256") for item in actual if item.get("verdict") == "passed"]
        stable = len(actual) == len(planned) and len(hashes) == len(planned) and len(set(hashes)) == 1
        repeatability.append({
            "case_id": case_id,
            "attempts": len(actual),
            "expected_attempts": len(planned),
            "stable": stable,
            "stable_result_sha256": hashes[0] if stable else None,
        })
    required = set(manifest.get("required_layout_families", []))
    covered = {
        item["layout_family"] for item in records
        if item.get("expected") == "processed" and item.get("verdict") == "passed"
    }
    workspace_ids = [
        item.get("workspace_id") for item in records
        if item.get("expected") == "processed" and item.get("workspace_id")
    ]
    complete = completed_ids == plan_ids and len(records) == len(plan)
    repeatable = all(item["stable"] for item in repeatability)
    collision_free = len(workspace_ids) == len(set(workspace_ids))
    passed = (
        complete and not execution_failures and required <= covered
        and repeatable and collision_free
    )
    return {
        "expected_execution_count": len(plan),
        "completed_execution_count": len(records),
        "passed_execution_count": sum(item.get("verdict") == "passed" for item in records),
        "failed_execution_count": len(execution_failures),
        "execution_failures": execution_failures,
        "required_family_count": len(required),
        "covered_family_count": len(required & covered),
        "missing_layout_families": sorted(required - covered),
        "repeatability": repeatability,
        "repeatability_passed": repeatable,
        "workspace_collision_free": collision_free,
        "acceptance_passed": passed,
    }


def run_acceptance_suite(
    corpus: AcceptanceCorpus,
    *,
    input_root: Path | str,
    output_root: Path | str,
    run_id: str,
    device: str = "cpu",
    resume: bool = False,
    service: RelayFormOcrService | None = None,
    runtime: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Run or resume one portable acceptance suite and persist evidence after every PDF."""

    run_id = _identifier(run_id, field="run_id")
    inputs = resolve_inputs(corpus, input_root)
    plan = build_execution_plan(corpus, run_id)
    root = Path(output_root).resolve()
    suite_root = root / run_id
    manifest_path = suite_root / "acceptance_manifest.json"
    if suite_root.exists() and not resume:
        raise AcceptanceConfigurationError("suite output đã tồn tại; dùng --resume hoặc run ID mới")
    if resume:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AcceptanceConfigurationError("Không đọc được manifest để resume") from exc
        if (
            manifest.get("run_id") != run_id
            or manifest.get("suite_id") != corpus.suite_id
            or manifest.get("corpus_sha256") != corpus.source_sha256
            or manifest.get("requested_device") != device
        ):
            raise AcceptanceConfigurationError("Manifest resume không khớp run/corpus/device")
    else:
        suite_root.mkdir(parents=True)
        manifest = {
            "acceptance_schema_version": ACCEPTANCE_SCHEMA_VERSION,
            "runner_version": RUNNER_VERSION,
            "consumer_schema_version": CONSUMER_SCHEMA_VERSION,
            "suite_id": corpus.suite_id,
            "run_id": run_id,
            "description": corpus.description,
            "state": "running",
            "started_at_utc": _utc_now(),
            "completed_at_utc": None,
            "requested_device": device,
            "runtime": dict(runtime or probe_runtime(device)),
            "repository": _repository_revision(),
            "corpus_sha256": corpus.source_sha256,
            "required_layout_families": list(corpus.required_layout_families),
            "command_contract": {
                "module": "examples.local_consumer.acceptance_runner",
                "subcommand": "run",
                "runner_version": RUNNER_VERSION,
            },
            "execution_plan": plan,
            "executions": [],
            "summary": {},
        }
        manifest["summary"] = _derive_summary(manifest)
        _atomic_json(manifest_path, manifest)
    artifact_root = suite_root / "ocr-artifacts"
    artifact_root.mkdir(exist_ok=True)
    generated = suite_root / "generated" / "corrupt.pdf"
    if not generated.exists():
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_bytes(b"%PDF-1.7\n% intentionally corrupt acceptance fixture\n")
    runtime_service = service or RelayFormOcrService(use_gpu=device == "gpu")
    completed = {item["execution_id"] for item in manifest["executions"]}
    for planned in plan:
        if planned["execution_id"] in completed:
            continue
        source = generated if planned["expected"] == "invalid_pdf" else inputs[planned["case_id"]]
        record = _execution_record(planned, source, artifact_root, suite_root, runtime_service)
        manifest["executions"].append(record)
        manifest["summary"] = _derive_summary(manifest)
        _atomic_json(manifest_path, manifest)
    manifest["summary"] = _derive_summary(manifest)
    manifest["state"] = "passed" if manifest["summary"]["acceptance_passed"] else "failed"
    manifest["completed_at_utc"] = _utc_now()
    _atomic_json(manifest_path, manifest)
    return manifest, manifest_path


def _safe_evidence_file(root: Path, relative_path: object) -> Path:
    if not isinstance(relative_path, str) or "\\" in relative_path:
        raise AcceptanceEvidenceError("Evidence path không portable")
    path = PurePosixPath(relative_path)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise AcceptanceEvidenceError("Evidence path không nằm trong bundle")
    target = root.joinpath(*path.parts).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise AcceptanceEvidenceError("Evidence path thoát khỏi bundle") from exc
    if not target.is_file() or target.is_symlink():
        raise AcceptanceEvidenceError("Thiếu evidence regular file")
    return target


def verify_acceptance_evidence(
    manifest_path: Path | str, *, full_artifact_audit: bool = False
) -> dict[str, Any]:
    """Validate a copied compact bundle; optionally rehash every OCR artifact."""

    path = Path(manifest_path).resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcceptanceEvidenceError("Không đọc được acceptance manifest") from exc
    if manifest.get("acceptance_schema_version") != ACCEPTANCE_SCHEMA_VERSION:
        raise AcceptanceEvidenceError("Acceptance manifest version không được hỗ trợ")
    root = path.parent
    verified = 0
    for record in manifest.get("executions", []):
        result_path = _safe_evidence_file(root, record.get("result_file"))
        summary_path = _safe_evidence_file(root, record.get("summary_file"))
        if _sha256(result_path) != record.get("result_sha256"):
            raise AcceptanceEvidenceError("Result evidence checksum mismatch")
        if _sha256(summary_path) != record.get("summary_sha256"):
            raise AcceptanceEvidenceError("Summary evidence checksum mismatch")
        result = OcrResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if result.correlation_id != record.get("correlation_id"):
            raise AcceptanceEvidenceError("Correlation ID evidence mismatch")
        if summary.get("correlation_id") != result.correlation_id:
            raise AcceptanceEvidenceError("Consumer summary correlation mismatch")
        physical_path = record.get("physical_manifest_file")
        if physical_path is not None:
            physical = _safe_evidence_file(root, physical_path)
            if _sha256(physical) != record.get("physical_manifest_sha256"):
                raise AcceptanceEvidenceError("Physical manifest checksum mismatch")
            physical_payload = json.loads(physical.read_text(encoding="utf-8"))
            if physical_payload.get("source", {}).get("unchanged") is not True:
                raise AcceptanceEvidenceError("Physical manifest không xác nhận source bất biến")
        if full_artifact_audit and result.artifact_manifest.artifacts:
            audit_artifact_manifest(result, root / "ocr-artifacts")
        verified += 1
    derived = _derive_summary(manifest)
    if derived != manifest.get("summary"):
        raise AcceptanceEvidenceError("Aggregate summary không khớp execution evidence")
    return {
        "acceptance_schema_version": ACCEPTANCE_SCHEMA_VERSION,
        "run_id": manifest.get("run_id"),
        "state": manifest.get("state"),
        "verified_execution_count": verified,
        "full_artifact_audit": full_artifact_audit,
        "acceptance_passed": derived["acceptance_passed"],
    }


def _plan_payload(corpus: AcceptanceCorpus, inputs: Mapping[str, Path], device: str) -> dict[str, Any]:
    return {
        "acceptance_schema_version": ACCEPTANCE_SCHEMA_VERSION,
        "suite_id": corpus.suite_id,
        "requested_device": device,
        "case_count": len(corpus.cases),
        "layout_family_count": len(corpus.required_layout_families),
        "real_pdf_execution_count": sum(case.repeat for case in corpus.cases),
        "failure_execution_count": 1,
        "all_inputs_available": len(inputs) == len(corpus.cases),
        "runtime": probe_runtime(device),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Acceptance per-PDF cho local OCR API v1.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="Kiểm tra corpus/runtime mà không chạy OCR.")
    run = subparsers.add_parser("run", help="Chạy hoặc resume acceptance OCR thật.")
    verify = subparsers.add_parser("verify", help="Xác minh evidence đã chép từ máy chạy.")
    for command in (plan, run):
        command.add_argument("--corpus", required=True, type=Path)
        command.add_argument("--input-root", required=True, type=Path)
        command.add_argument("--device", choices=("cpu", "gpu"), default="cpu")
    run.add_argument("--output-root", required=True, type=Path)
    run.add_argument("--run-id", required=True)
    run.add_argument("--resume", action="store_true")
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--full-artifact-audit", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "verify":
            payload = verify_acceptance_evidence(
                args.manifest, full_artifact_audit=args.full_artifact_audit
            )
            code = 0 if payload["acceptance_passed"] else EXIT_ACCEPTANCE_FAILED
        else:
            corpus = load_corpus(args.corpus)
            inputs = resolve_inputs(corpus, args.input_root)
            if args.command == "plan":
                payload = _plan_payload(corpus, inputs, args.device)
                code = 0
            else:
                runtime = probe_runtime(args.device)
                with isolate_consumer_stdout(sys.stdout, sys.stderr):
                    manifest, manifest_path = run_acceptance_suite(
                        corpus,
                        input_root=args.input_root,
                        output_root=args.output_root,
                        run_id=args.run_id,
                        device=args.device,
                        resume=args.resume,
                        runtime=runtime,
                    )
                from .acceptance_visual import render_acceptance_review

                report = render_acceptance_review(
                    manifest, manifest_path.parent / "acceptance_review.html"
                )
                payload = {
                    "acceptance_schema_version": ACCEPTANCE_SCHEMA_VERSION,
                    "run_id": manifest["run_id"],
                    "state": manifest["state"],
                    "acceptance_passed": manifest["summary"]["acceptance_passed"],
                    "completed_execution_count": manifest["summary"]["completed_execution_count"],
                    "manifest": manifest_path.name,
                    "report": report.name,
                }
                code = 0 if payload["acceptance_passed"] else EXIT_ACCEPTANCE_FAILED
    except AcceptanceConfigurationError as exc:
        payload = {
            "acceptance_schema_version": ACCEPTANCE_SCHEMA_VERSION,
            "state": "configuration_error",
            "error": str(exc),
        }
        code = EXIT_GPU_UNAVAILABLE if "GPU" in str(exc) or "CUDA" in str(exc) else 2
    except AcceptanceEvidenceError as exc:
        payload = {
            "acceptance_schema_version": ACCEPTANCE_SCHEMA_VERSION,
            "state": "evidence_invalid",
            "error": str(exc),
        }
        code = EXIT_EVIDENCE_INVALID
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
