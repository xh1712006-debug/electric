"""Validate and render the locked local API v1 handoff."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import re
from typing import Any, Sequence

from examples.local_consumer.python_consumer import CONSUMER_SCHEMA_VERSION
from src.relay_form_ocr import OcrRequest, OcrResult, PIPELINE_VERSION
from src.relay_form_ocr.cli import CLI_SCHEMA_VERSION
from src.relay_form_ocr.schema_export import schema_payloads
from src.relay_form_ocr.schemas import SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "contracts/local_api/v1/release_manifest.json"
DEFAULT_OUTPUT = ROOT / "output/local_api_handoff/handoff_review.html"
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


class HandoffValidationError(ValueError):
    """Raised when the checked-in v1 handoff is internally inconsistent."""


def load_release_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise HandoffValidationError("release manifest phải là JSON object")
    return payload


def _relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise HandoffValidationError(f"đường dẫn release không an toàn: {value}")
    return ROOT / path


def _markdown_link_errors(document: Path) -> list[str]:
    errors: list[str] = []
    text = document.read_text(encoding="utf-8")
    for raw_target in LINK_PATTERN.findall(text):
        target = raw_target.strip().strip("<>")
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        target = target.split("#", 1)[0]
        if not target:
            continue
        resolved = (document.parent / target).resolve()
        try:
            resolved.relative_to(ROOT)
        except ValueError:
            errors.append(f"{document.name}: link thoát repository: {raw_target}")
            continue
        if not resolved.exists():
            errors.append(f"{document.name}: link không tồn tại: {raw_target}")
    return errors


def validate_release(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_versions = {
        "local_api_version": "1.0",
        "schema_version": SCHEMA_VERSION,
        "cli_schema_version": CLI_SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
    }
    for key, expected in expected_versions.items():
        if manifest.get(key) != expected:
            errors.append(f"{key} phải là {expected!r}")
    if manifest.get("release_id") != "ocr_prj.local_api.v1":
        errors.append("release_id không đúng local API v1")
    if manifest.get("release_status") != "scope_locked":
        errors.append("release_status phải là scope_locked")
    if not manifest.get("source_checkout_mode"):
        errors.append("handoff phải công bố source_checkout_mode")
    if CONSUMER_SCHEMA_VERSION != SCHEMA_VERSION:
        errors.append("consumer schema không khớp result schema")

    contract_path = ROOT / "contracts/local_api/v1/contract_manifest.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("contract_id") != "ocr_prj.local_pdf.v1":
        errors.append("contract_id không đúng")
    if contract.get("schema_version") != manifest.get("schema_version"):
        errors.append("contract schema không khớp release manifest")

    public_module = __import__("src.relay_form_ocr", fromlist=["*"])
    for symbol in manifest.get("public_python_imports", []):
        if not isinstance(symbol, str) or not hasattr(public_module, symbol):
            errors.append(f"public import không tồn tại: {symbol!r}")

    for category in ("documentation", "schemas", "fixtures"):
        values = manifest.get(category)
        if not isinstance(values, list) or not values:
            errors.append(f"{category} phải là danh sách không rỗng")
            continue
        for value in values:
            if not isinstance(value, str):
                errors.append(f"{category} chứa đường dẫn không hợp lệ")
                continue
            try:
                path = _relative_path(value)
            except HandoffValidationError as exc:
                errors.append(str(exc))
                continue
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"file handoff thiếu hoặc rỗng: {value}")

    tracked_schemas = manifest.get("schemas", [])
    expected_schema_payloads = schema_payloads()
    for value in tracked_schemas:
        path = _relative_path(value)
        if path.is_file():
            expected = expected_schema_payloads.get(path.name)
            actual = json.loads(path.read_text(encoding="utf-8"))
            if expected is None or actual != expected:
                errors.append(f"JSON Schema lệch typed model: {value}")

    for value in manifest.get("fixtures", []):
        path = _relative_path(value)
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        try:
            OcrRequest.model_validate(payload["request"])
            OcrResult.model_validate(payload["result"])
        except Exception as exc:  # Pydantic supplies the detailed cause to the test log.
            errors.append(f"fixture không validate: {value}: {type(exc).__name__}")

    docs = [_relative_path(value) for value in manifest.get("documentation", [])]
    for document in docs:
        if document.is_file():
            errors.extend(_markdown_link_errors(document))

    required_doc_tokens = {
        "README.md": ["Local API v1", "API.md", "init.ps1"],
        "API.md": ["RelayFormOcrService", "OcrRequest", "review_required", "PYTHONPATH"],
        "ARCHITECTURE.md": ["Trust boundary", "Page 3+", "0.7.0"],
        "session-handoff.md": ["IMMEDIATE-010", "PLAN-001", "249/249"],
    }
    for name, tokens in required_doc_tokens.items():
        path = ROOT / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in text:
                errors.append(f"{name} thiếu nội dung bắt buộc: {token}")

    summary = manifest.get("acceptance_summary", {})
    if summary.get("passed_executions") != 10 or summary.get("layout_families") != 8:
        errors.append("acceptance summary không khóa bằng chứng 10 executions/8 families")
    if summary.get("accuracy_claimed") is not False:
        errors.append("release không được tuyên bố OCR accuracy")
    if not all(summary.get(key) is True for key in (
        "repeatability_stable",
        "workspace_collision_free",
        "sources_unchanged",
        "full_artifact_audit",
    )):
        errors.append("acceptance safety evidence chưa đầy đủ")
    if not str(manifest.get("next_task", "")).startswith("PLAN-001"):
        errors.append("task tiếp theo phải là PLAN-001")
    return errors


def render_handoff_html(manifest: dict[str, Any], output: Path) -> Path:
    errors = validate_release(manifest)
    summary = manifest["acceptance_summary"]
    scope_rows = "".join(f"<li>{escape(str(item))}</li>" for item in manifest["supported_scope"])
    limitation_rows = "".join(f"<li>{escape(str(item))}</li>" for item in manifest["limitations"])
    docs = "".join(
        f"<tr><td><code>{escape(path)}</code></td><td>Đã khóa</td></tr>"
        for path in manifest["documentation"]
    )
    state = "Hợp lệ" if not errors else "Không hợp lệ"
    state_class = "ok" if not errors else "bad"
    error_section = "" if not errors else (
        "<section><h2>Lỗi xác minh</h2><ul>"
        + "".join(f"<li>{escape(item)}</li>" for item in errors)
        + "</ul></section>"
    )
    html = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bàn giao Local API v1</title>
<style>
:root{{--ink:#182033;--muted:#667085;--line:#d8dfeb;--paper:#f4f7fb;--card:#fff;--good:#08734a;--good-bg:#e9f8f0;--bad:#a22f3d;--bad-bg:#fff0f2;--accent:#2457c5}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,"Segoe UI",sans-serif}}
main{{max-width:1160px;margin:auto;padding:32px 20px 48px}} h1{{margin:0;font-size:clamp(28px,5vw,45px)}} h2{{margin:0 0 12px;font-size:21px}} p{{margin:8px 0}} .muted{{color:var(--muted)}}
.state{{display:inline-block;margin-top:14px;padding:6px 11px;border-radius:999px;font-weight:700}} .ok{{color:var(--good);background:var(--good-bg)}} .bad{{color:var(--bad);background:var(--bad-bg)}}
.cards{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:24px 0}} .card,section{{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:17px}}
.card span{{display:block;color:var(--muted)}} .card strong{{font-size:24px}} .grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0}} ul{{margin:0;padding-left:21px}}
.table-wrap{{overflow-x:auto;border:1px solid var(--line);border-radius:12px}} table{{border-collapse:collapse;width:100%;min-width:620px;background:var(--card)}} th,td{{padding:11px 13px;text-align:left;border-bottom:1px solid var(--line)}} th{{color:var(--muted);font-size:12px;text-transform:uppercase}} tr:last-child td{{border-bottom:0}}
.guard{{border-left:4px solid var(--accent)}} code{{overflow-wrap:anywhere}} @media(max-width:720px){{.cards,.grid{{grid-template-columns:1fr 1fr}}}} @media(max-width:440px){{main{{padding:22px 12px 36px}}.cards,.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body><main>
<header><p class="muted">IMMEDIATE-010 · Phạm vi đã khóa</p><h1>Bàn giao Local API v1</h1><span class="state {state_class}">{state}</span><p>API <code>{escape(manifest['local_api_version'])}</code> · Schema <code>{escape(manifest['schema_version'])}</code> · CLI <code>{escape(manifest['cli_schema_version'])}</code> · Pipeline <code>{escape(manifest['pipeline_version'])}</code></p></header>
<div class="cards"><div class="card"><span>Họ bố cục</span><strong>{summary['layout_families']}</strong></div><div class="card"><span>Lượt chạy đạt</span><strong>{summary['passed_executions']}/10</strong></div><div class="card"><span>Trang PDF thật</span><strong>{summary['real_pages']}</strong></div><div class="card"><span>Tệp kết quả đã kiểm tra</span><strong>{summary['public_artifacts']}</strong></div></div>
<div class="grid"><section><h2>Phạm vi hỗ trợ</h2><ul>{scope_rows}</ul></section><section><h2>Giới hạn đã công bố</h2><ul>{limitation_rows}</ul></section></div>
<section><h2>Tài liệu bàn giao</h2><div class="table-wrap"><table><thead><tr><th>File</th><th>Trạng thái</th></tr></thead><tbody>{docs}</tbody></table></div></section>
<section class="guard"><h2>Hàng rào sử dụng dữ liệu</h2><p>Page 3+ và phần Lưu ý luôn cần người duyệt. Acceptance xác nhận contract, repeatability, source/artifact safety; <strong>không phải phép đo độ chính xác OCR</strong> khi chưa có ground truth.</p><p>Task tiếp theo: <strong>{escape(manifest['next_task'])}</strong>.</p></section>
{error_section}
</main></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8", newline="\n")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Xác minh và sinh handoff Local API v1 bằng tiếng Việt.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = load_release_manifest(args.manifest)
    errors = validate_release(manifest)
    if not args.check_only:
        render_handoff_html(manifest, args.output)
    print(json.dumps({
        "release_id": manifest.get("release_id"),
        "valid": not errors,
        "error_count": len(errors),
        "report": None if args.check_only else str(args.output),
    }, ensure_ascii=True, separators=(",", ":")))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
