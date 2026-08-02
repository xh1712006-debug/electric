"""Validate local API v1 examples and render an accented-Vietnamese review."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Any, Iterable, Mapping, Sequence

from src.layout_analysis.page1.schema import PAGE1_FIELD_NAMES


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT_ROOT = REPOSITORY_ROOT / "contracts" / "local_api" / "v1"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "output" / "local_api_contract" / "contract_review.html"
CONFIDENCE_LABELS = {
    1: "very_low",
    2: "low",
    3: "medium",
    4: "high",
    5: "very_high",
}
FORBIDDEN_PUBLIC_KEYS = {
    "detection",
    "image_path",
    "input_pdf",
    "output_pdf",
    "output_root",
    "raw_ocr",
    "recognition",
    "session_state",
    "stack_trace",
    "streamlit_state",
    "traceback",
}
SCENARIO_LABELS = {
    "success": "Thành công",
    "success_with_warnings": "Thành công có cảnh báo",
    "review_required": "Cần người kiểm tra",
    "failure": "Thất bại có kiểm soát",
}
STATUS_LABELS = {
    "success": "Thành công",
    "success_with_warnings": "Thành công có cảnh báo",
    "failed": "Thất bại",
}
REVIEW_LABELS = {
    "not_required": "Không yêu cầu xem xét",
    "review_required": "Cần xem xét",
}


def load_contract(contract_root: Path | str = DEFAULT_CONTRACT_ROOT) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = Path(contract_root)
    manifest = json.loads((root / "contract_manifest.json").read_text(encoding="utf-8"))
    examples = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / "examples").glob("*.json"))
    ]
    return manifest, examples


def _absolute_path(value: str) -> bool:
    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute()


def _walk(value: Any, path: str = "result") -> Iterable[tuple[str, str | None, Any]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield child_path, str(key), child
            yield from _walk(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            yield child_path, None, child
            yield from _walk(child, child_path)


def _validate_request(request: Any, manifest: Mapping[str, Any], errors: list[str]) -> None:
    if not isinstance(request, Mapping):
        errors.append("request phải là object")
        return
    policy = manifest["request"]
    allowed = set(policy["allowed_fields"])
    actual = set(request)
    missing = set(policy["required_fields"]) - actual
    unexpected = actual - allowed
    if missing:
        errors.append(f"request thiếu field: {sorted(missing)}")
    if unexpected:
        errors.append(f"request có field ngoài contract: {sorted(unexpected)}")
    input_pdf = request.get("input_pdf")
    if not isinstance(input_pdf, str) or not _absolute_path(input_pdf) or Path(input_pdf).suffix.lower() != ".pdf":
        errors.append("input_pdf phải là một absolute .pdf path")
    output_root = request.get("output_root")
    if not isinstance(output_root, str) or not _absolute_path(output_root):
        errors.append("output_root phải là absolute path")
    correlation_id = request.get("correlation_id")
    if not isinstance(correlation_id, str) or re.fullmatch(policy["correlation_id_pattern"], correlation_id) is None:
        errors.append("correlation_id không đúng pattern v1")


def _validate_confidence(value: Any, path: str, errors: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        errors.append(f"{path} phải là object hoặc null")
        return
    level = value.get("level")
    label = value.get("label")
    score = value.get("score")
    if level not in CONFIDENCE_LABELS or CONFIDENCE_LABELS.get(level) != label:
        errors.append(f"{path} có level/label không khớp")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= float(score) <= 100:
        errors.append(f"{path}.score phải nằm trong 0..100")


def _validate_business(business: Any, manifest: Mapping[str, Any], errors: list[str]) -> set[str]:
    if not isinstance(business, Mapping):
        errors.append("business phải là object khi result thành công")
        return set()
    required_business = {"page1_fields", "setting_records", "note_candidates", "evidence_artifact_ids"}
    if not required_business.issubset(business):
        errors.append(f"business thiếu {sorted(required_business - set(business))}")
    fields = business.get("page1_fields")
    if not isinstance(fields, Mapping):
        errors.append("business.page1_fields phải là object")
    else:
        actual = set(fields)
        expected = set(PAGE1_FIELD_NAMES)
        if actual != expected:
            errors.append(
                "page1_fields phải có đúng 25 canonical keys; "
                f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
            )
        allowed_resolution = set(manifest["enums"]["field_resolution_status"])
        for name, field in fields.items():
            path = f"business.page1_fields.{name}"
            if not isinstance(field, Mapping):
                errors.append(f"{path} phải là object")
                continue
            required = {"value", "confidence", "resolution_status", "source_page"}
            if not required.issubset(field):
                errors.append(f"{path} thiếu {sorted(required - set(field))}")
                continue
            if field["value"] is not None and not isinstance(field["value"], str):
                errors.append(f"{path}.value phải là string hoặc null")
            if field["resolution_status"] not in allowed_resolution:
                errors.append(f"{path}.resolution_status không hợp lệ")
            if field["source_page"] is not None and (
                isinstance(field["source_page"], bool)
                or not isinstance(field["source_page"], int)
                or field["source_page"] < 1
            ):
                errors.append(f"{path}.source_page phải là số trang dương hoặc null")
            _validate_confidence(field["confidence"], f"{path}.confidence", errors)

    for index, record in enumerate(business.get("setting_records", [])):
        if not isinstance(record, Mapping) or record.get("review_status") != "review_required":
            errors.append(f"business.setting_records[{index}] phải review_required")
    for index, note in enumerate(business.get("note_candidates", [])):
        if not isinstance(note, Mapping) or note.get("review_status") != "review_required":
            errors.append(f"business.note_candidates[{index}] phải review_required")
    evidence_ids = business.get("evidence_artifact_ids")
    if not isinstance(evidence_ids, list) or not all(isinstance(item, str) for item in evidence_ids):
        errors.append("business.evidence_artifact_ids phải là list string")
        return set()
    return set(evidence_ids)


def _validate_result(
    result: Any,
    request: Mapping[str, Any],
    scenario: Any,
    manifest: Mapping[str, Any],
    errors: list[str],
) -> None:
    if not isinstance(result, Mapping):
        errors.append("result phải là object")
        return
    required = set(manifest["result"]["required_fields"])
    missing = required - set(result)
    if missing:
        errors.append(f"result thiếu field: {sorted(missing)}")
        return
    if result["schema_version"] != manifest["schema_version"]:
        errors.append("schema_version không khớp contract manifest")
    if not isinstance(result["pipeline_version"], str) or not result["pipeline_version"].strip():
        errors.append("pipeline_version phải là non-empty string")
    if result["correlation_id"] != request.get("correlation_id"):
        errors.append("result.correlation_id không khớp request")
    status = result["status"]
    review_status = result["review_status"]
    if status not in manifest["enums"]["status"]:
        errors.append("result.status không hợp lệ")
    if review_status not in manifest["enums"]["review_status"]:
        errors.append("result.review_status không hợp lệ")
    expected_scenario = {
        "success": ("success", "not_required"),
        "success_with_warnings": ("success_with_warnings", "not_required"),
        "review_required": ("success", "review_required"),
        "failure": ("failed", "review_required"),
    }.get(scenario)
    if expected_scenario != (status, review_status):
        errors.append("scenario không khớp status/review_status")

    warnings = result["warnings"]
    if not isinstance(warnings, list):
        errors.append("warnings phải là list")
        warnings = []
    for index, warning in enumerate(warnings):
        if not isinstance(warning, Mapping):
            errors.append(f"warnings[{index}] phải là object")
            continue
        required_warning = {"code", "message", "stage"}
        if not required_warning.issubset(warning):
            errors.append(f"warnings[{index}] thiếu {sorted(required_warning - set(warning))}")
        if not isinstance(warning.get("code"), str) or not warning.get("code"):
            errors.append(f"warnings[{index}].code không hợp lệ")
        if not isinstance(warning.get("message"), str) or not warning.get("message"):
            errors.append(f"warnings[{index}].message không hợp lệ")
        if warning.get("stage") not in manifest["enums"]["error_stage"]:
            errors.append(f"warnings[{index}].stage không hợp lệ")
        page_number = warning.get("page_number")
        if page_number is not None and (
            isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1
        ):
            errors.append(f"warnings[{index}].page_number không hợp lệ")
    if status == "success" and warnings:
        errors.append("status=success không được có warnings")
    if status == "success_with_warnings" and not warnings:
        errors.append("success_with_warnings phải có ít nhất một warning")
    if status == "failed":
        if result["business"] is not None:
            errors.append("failed result phải có business=null")
        error = result["error"]
        if not isinstance(error, Mapping):
            errors.append("failed result phải có error object")
        else:
            required_error = {"code", "message", "stage", "retryable", "details"}
            if not required_error.issubset(error):
                errors.append(f"error thiếu {sorted(required_error - set(error))}")
            if error.get("code") not in manifest["enums"]["error_code"]:
                errors.append("error.code không thuộc catalog v1")
            if error.get("stage") not in manifest["enums"]["error_stage"]:
                errors.append("error.stage không hợp lệ")
            if not isinstance(error.get("message"), str) or not error.get("message"):
                errors.append("error.message không hợp lệ")
            if not isinstance(error.get("retryable"), bool):
                errors.append("error.retryable phải là boolean")
        evidence_ids: set[str] = set()
    else:
        if result["error"] is not None:
            errors.append("successful result phải có error=null")
        evidence_ids = _validate_business(result["business"], manifest, errors)

    pages = result["pages"]
    if not isinstance(pages, list):
        errors.append("pages phải là list")
        pages = []
    page_artifact_ids: set[str] = set()
    for index, page in enumerate(pages):
        if not isinstance(page, Mapping):
            errors.append(f"pages[{index}] phải là object")
            continue
        required_page = {"page_number", "role", "status", "review_status", "artifact_ids"}
        if not required_page.issubset(page):
            errors.append(f"pages[{index}] thiếu {sorted(required_page - set(page))}")
        if page.get("role") not in manifest["enums"]["page_role"]:
            errors.append(f"pages[{index}].role không hợp lệ")
        if page.get("status") not in manifest["enums"]["page_status"]:
            errors.append(f"pages[{index}].status không hợp lệ")
        if page.get("review_status") not in manifest["enums"]["review_status"]:
            errors.append(f"pages[{index}].review_status không hợp lệ")
        if not isinstance(page.get("artifact_ids"), list) or not all(
            isinstance(item, str) for item in page.get("artifact_ids", [])
        ):
            errors.append(f"pages[{index}].artifact_ids phải là list string")
        page_artifact_ids.update(item for item in page.get("artifact_ids", []) if isinstance(item, str))

    document = result["document"]
    if document is not None:
        if not isinstance(document, Mapping):
            errors.append("document phải là object hoặc null")
        else:
            required_document = {"document_id", "source_name", "source_sha256", "page_count"}
            if not required_document.issubset(document):
                errors.append(f"document thiếu {sorted(required_document - set(document))}")
            digest = document.get("source_sha256")
            if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                errors.append("document.source_sha256 phải là lowercase SHA-256")
            if document.get("page_count") != len(pages):
                errors.append("document.page_count phải bằng số phần tử pages")

    timing = result["timing"]
    if not isinstance(timing, Mapping) or not {"started_at", "completed_at", "elapsed_ms", "stage_ms"}.issubset(timing):
        errors.append("timing thiếu terminal timing fields")
    elif (
        isinstance(timing["elapsed_ms"], bool)
        or not isinstance(timing["elapsed_ms"], (int, float))
        or timing["elapsed_ms"] < 0
        or not isinstance(timing["stage_ms"], Mapping)
    ):
        errors.append("timing elapsed/stage values không hợp lệ")

    artifact_manifest = result["artifact_manifest"]
    artifact_ids: set[str] = set()
    if not isinstance(artifact_manifest, Mapping) or not isinstance(artifact_manifest.get("artifacts"), list):
        errors.append("artifact_manifest không hợp lệ")
    else:
        for index, artifact in enumerate(artifact_manifest["artifacts"]):
            path = f"artifact_manifest.artifacts[{index}]"
            if not isinstance(artifact, Mapping):
                errors.append(f"{path} phải là object")
                continue
            identifier = artifact.get("artifact_id")
            required_artifact = {
                "artifact_id", "kind", "relative_path", "media_type", "sha256", "size_bytes"
            }
            if not required_artifact.issubset(artifact):
                errors.append(f"{path} thiếu {sorted(required_artifact - set(artifact))}")
            if not isinstance(identifier, str) or not identifier:
                errors.append(f"{path}.artifact_id không hợp lệ")
            elif identifier in artifact_ids:
                errors.append(f"{path}.artifact_id bị trùng")
            else:
                artifact_ids.add(identifier)
            relative = artifact.get("relative_path")
            if (
                not isinstance(relative, str)
                or _absolute_path(relative)
                or ".." in PurePosixPath(relative).parts
                or ".." in PureWindowsPath(relative).parts
            ):
                errors.append(f"{path}.relative_path phải nằm tương đối dưới output_root")
            digest = artifact.get("sha256")
            if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                errors.append(f"{path}.sha256 không hợp lệ")
            size = artifact.get("size_bytes")
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                errors.append(f"{path}.size_bytes không hợp lệ")
    missing_artifacts = (evidence_ids | page_artifact_ids) - artifact_ids
    if missing_artifacts:
        errors.append(f"artifact references không tồn tại: {sorted(missing_artifacts)}")

    if status != "failed" and isinstance(result.get("business"), Mapping):
        business = result["business"]
        page1_fields = business.get("page1_fields", {})
        requires_review = (
            any(
                isinstance(field, Mapping) and field.get("resolution_status") == "review_required"
                for field in page1_fields.values()
            )
            if isinstance(page1_fields, Mapping)
            else False
        )
        requires_review = (
            requires_review
            or bool(business.get("setting_records"))
            or bool(business.get("note_candidates"))
        )
        if requires_review and review_status != "review_required":
            errors.append("business có candidate cần review nhưng result.review_status không yêu cầu review")

    for path, key, value in _walk(result):
        if key in FORBIDDEN_PUBLIC_KEYS and ".stage_ms." not in path:
            errors.append(f"public result chứa forbidden key: {path}")
        if isinstance(value, str) and _absolute_path(value):
            errors.append(f"public result chứa absolute path: {path}")


def validate_example(example: Any, manifest: Mapping[str, Any]) -> list[str]:
    """Return human-readable contract violations for one example."""

    errors: list[str] = []
    if not isinstance(example, Mapping):
        return ["example phải là object"]
    if example.get("scenario") not in manifest["example_scenarios"]:
        errors.append("scenario không thuộc bốn acceptance cases")
    request = example.get("request")
    _validate_request(request, manifest, errors)
    if isinstance(request, Mapping):
        _validate_result(example.get("result"), request, example.get("scenario"), manifest, errors)
    return errors


def validate_contract(
    manifest: Mapping[str, Any], examples: Sequence[Mapping[str, Any]]
) -> dict[str, list[str]]:
    """Validate scenario coverage and every contract example."""

    results = {
        str(example.get("example_id", f"example-{index}")): validate_example(example, manifest)
        for index, example in enumerate(examples)
    }
    actual = {example.get("scenario") for example in examples}
    expected = set(manifest["example_scenarios"])
    if actual != expected:
        results["scenario-coverage"] = [
            f"Thiếu={sorted(expected - actual)}, thừa={sorted(actual - expected)}"
        ]
    return results


def render_contract_html(
    manifest: Mapping[str, Any], examples: Sequence[Mapping[str, Any]]
) -> str:
    """Render a dependency-free Vietnamese contract review page."""

    validation = validate_contract(manifest, examples)
    rows = []
    cards = []
    for example in examples:
        result = example["result"]
        business = result.get("business") or {}
        fields = business.get("page1_fields", {})
        populated = sum(field.get("value") is not None for field in fields.values())
        records = len(business.get("setting_records", []))
        issues = validation.get(example["example_id"], [])
        rows.append(
            "<tr>"
            f"<td>{escape(SCENARIO_LABELS[example['scenario']])}</td>"
            f"<td><code>{escape(result['status'])}</code><br>{escape(STATUS_LABELS[result['status']])}</td>"
            f"<td><code>{escape(result['review_status'])}</code><br>{escape(REVIEW_LABELS[result['review_status']])}</td>"
            f"<td>{populated}/25</td><td>{records}</td><td>{len(result['warnings'])}</td>"
            f"<td class={'ok' if not issues else 'bad'}>{'Hợp lệ' if not issues else escape('; '.join(issues))}</td>"
            "</tr>"
        )
        artifact_paths = [item["relative_path"] for item in result["artifact_manifest"]["artifacts"]]
        error = result.get("error")
        cards.append(
            "<article>"
            f"<h3>{escape(SCENARIO_LABELS[example['scenario']])}</h3>"
            f"<p><strong>Correlation ID:</strong> <code>{escape(result['correlation_id'])}</code></p>"
            f"<p><strong>Kết quả:</strong> {escape(STATUS_LABELS[result['status']])}; "
            f"<strong>review:</strong> {escape(REVIEW_LABELS[result['review_status']])}.</p>"
            f"<p><strong>Artifact tương đối:</strong> {escape(', '.join(artifact_paths) or 'Không có')}.</p>"
            + (
                f"<p class=bad><strong>Lỗi public:</strong> {escape(error['code'])} — {escape(error['message'])}</p>"
                if error else "<p class=ok><strong>Error:</strong> null — không có lỗi xử lý.</p>"
            )
            + "</article>"
        )
    all_valid = not any(validation.values())
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Rà soát contract local API v1</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f3f6fa;color:#172033}}
header{{background:#173a63;color:white;padding:28px 5vw}}main{{max-width:1180px;margin:auto;padding:24px}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:18px 0}}
.metric,article{{background:white;border:1px solid #d8e0ea;border-radius:10px;padding:16px;box-shadow:0 2px 7px #20304012}}
table{{width:100%;border-collapse:collapse;background:white}}th,td{{padding:10px;border:1px solid #d8e0ea;text-align:left;vertical-align:top}}
th{{background:#e8eef6}}code{{background:#eef2f7;padding:2px 5px;border-radius:4px}}.ok{{color:#13733c;font-weight:700}}.bad{{color:#a12622;font-weight:700}}
.policy{{background:#fff8dc;border-left:5px solid #d99b18;padding:14px 18px}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-top:18px}}
</style></head><body><header><h1>Rà soát contract local API v1</h1>
<p>Một PDF_x mỗi lần gọi · Python là interface chuẩn · JSON/CLI bảo đảm tích hợp đa runtime</p></header><main>
<div class="summary"><div class="metric"><strong>Contract</strong><br><code>{escape(str(manifest['contract_id']))}</code></div>
<div class="metric"><strong>Schema version</strong><br>{escape(str(manifest['schema_version']))}</div>
<div class="metric"><strong>Acceptance cases</strong><br>{len(examples)}/4</div>
<div class="metric"><strong>Validation</strong><br><span class={'ok' if all_valid else 'bad'}>{'Tất cả hợp lệ' if all_valid else 'Có lỗi cần sửa'}</span></div></div>
<section class="policy"><strong>Ranh giới an toàn:</strong> result không chứa absolute internal path, raw OCR, Streamlit state hoặc stack trace. Page 3+ luôn cần người kiểm tra; failure không trả business data.</section>
<h2>Bốn trạng thái mẫu</h2><table><thead><tr><th>Tình huống</th><th>Processing status</th><th>Review status</th><th>Field có giá trị</th><th>Setting candidate</th><th>Cảnh báo</th><th>Contract check</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table><div class="cards">{''.join(cards)}</div>
<h2>Lifecycle đồng bộ</h2><p>Validate request → xác nhận một PDF_x → render/OCR/layout → tổng hợp business và review → ghi artifact tương đối → trả một terminal result.</p>
</main></body></html>"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kiểm tra và sinh HTML contract local API v1.")
    parser.add_argument("--contract-root", type=Path, default=DEFAULT_CONTRACT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest, examples = load_contract(args.contract_root)
    validation = validate_contract(manifest, examples)
    failures = {key: value for key, value in validation.items() if value}
    if failures:
        print(json.dumps({"valid": False, "errors": failures}, ensure_ascii=True))
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_contract_html(manifest, examples), encoding="utf-8")
    print(json.dumps({"valid": True, "examples": len(examples), "output": str(args.output)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
