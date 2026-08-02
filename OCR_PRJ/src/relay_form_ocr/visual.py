"""Static Vietnamese review report for production orchestrator results."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from typing import Any, Mapping


_ROLE_VI = {
    "page1": "Trang bìa và thông tin quan trọng",
    "page2_skipped": "Trang 2 — bỏ qua theo chính sách",
    "page3_plus": "Trang thông số chỉnh định",
}
_STATUS_VI = {
    "completed": "Đã xử lý",
    "skipped_by_document_policy": "Đã bỏ qua theo chính sách",
}
_CONFIDENCE_VI = {
    "very_low": "Rất thấp",
    "low": "Thấp",
    "medium": "Trung bình",
    "high": "Cao",
    "very_high": "Rất cao",
}


def demo_orchestrator_result() -> dict[str, Any]:
    """Return a deterministic fixture covering all routes and confidence levels."""

    resolutions = {}
    for index, label in enumerate(_CONFIDENCE_VI, start=1):
        resolutions[f"truong_mau_{index}"] = {
            "status": "auto_selected" if index >= 4 else "review_required",
            "effective_score": round(index / 5, 2),
            "confidence": {"level": index, "label": label},
        }
    return {
        "schema_version": "1.0",
        "document": {
            "candidate_id": "demo-orchestrator",
            "name": "phieu-ro-le-mau.pdf",
            "path": "phieu-ro-le-mau.pdf",
            "page_count": 3,
            "origin": "visual_fixture",
        },
        "important_fields": {
            "ticket_number": "A1-29-2026/E5.8/220",
            "station": "Trạm 220kV Việt Trì",
        },
        "important_source_labels": {
            "ticket_number": "Số phiếu",
            "station": "Trạm",
        },
        "important_field_resolution": resolutions,
        "setting_records": [{"page_number": 3, "parameter_name": "Pickup", "value": "5", "unit": "A"}],
        "note_candidates": [{"page_number": 3, "text": "Lưu ý: Cần đối chiếu ảnh gốc."}],
        "warnings": [
            {
                "code": "page2_skipped_by_document_policy",
                "page_number": 2,
                "message": "Trang 2 được bỏ qua theo chính sách tài liệu; không chạy OCR hoặc layout.",
            },
            {
                "code": "layout_warning",
                "page_number": 3,
                "message": "Kết quả Page 3+ là ứng viên và cần người dùng xem xét.",
            },
        ],
        "pages": [
            {"page_number": 1, "page_role": "page1", "status": "completed", "warnings": []},
            {
                "page_number": 2,
                "page_role": "page2_skipped",
                "status": "skipped_by_document_policy",
                "warnings": ["Trang 2 được bỏ qua theo chính sách tài liệu."],
            },
            {
                "page_number": 3,
                "page_role": "page3_plus",
                "status": "completed",
                "warnings": ["Kết quả là ứng viên và cần xem xét."],
            },
        ],
        "artifacts": [
            {"kind": "page_result", "relative_path": "pages/page_0001.json"},
            {"kind": "extraction_result", "relative_path": "extraction.json"},
        ],
        "summary": {
            "pages": 3,
            "ocr_pages": 2,
            "skipped_pages": 1,
            "important_fields_populated": 2,
            "setting_records": 1,
            "note_candidates": 1,
            "warnings": 2,
            "elapsed_ms": 1234.5,
        },
    }


def _text(value: Any) -> str:
    return escape("—" if value is None else str(value))


def render_orchestrator_html(result: Mapping[str, Any], output_path: Path) -> Path:
    """Render a self-contained review artifact without exposing debug dependencies."""

    document = result.get("document") if isinstance(result.get("document"), Mapping) else {}
    summary = result.get("summary") if isinstance(result.get("summary"), Mapping) else {}
    pages = result.get("pages") if isinstance(result.get("pages"), list) else []
    warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
    fields = result.get("important_fields") if isinstance(result.get("important_fields"), Mapping) else {}
    labels = (
        result.get("important_source_labels")
        if isinstance(result.get("important_source_labels"), Mapping)
        else {}
    )
    resolutions = (
        result.get("important_field_resolution")
        if isinstance(result.get("important_field_resolution"), Mapping)
        else {}
    )

    page_rows = "".join(
        "<tr>"
        f"<td>{_text(page.get('page_number'))}</td>"
        f"<td>{_text(_ROLE_VI.get(str(page.get('page_role')), page.get('page_role')))}</td>"
        f"<td>{_text(_STATUS_VI.get(str(page.get('status')), page.get('status')))}</td>"
        f"<td>{_text('; '.join(str(item) for item in page.get('warnings', [])) or 'Không có')}</td>"
        "</tr>"
        for page in pages
        if isinstance(page, Mapping)
    )
    warning_items = "".join(
        f"<li><strong>{_text(item.get('code'))}</strong>"
        f"{f' · Trang {_text(item.get("page_number"))}' if item.get('page_number') else ''}: "
        f"{_text(item.get('message'))}</li>"
        for item in warnings
        if isinstance(item, Mapping)
    )

    field_rows = []
    for name, value in fields.items():
        evidence = resolutions.get(name)
        evidence = evidence if isinstance(evidence, Mapping) else {}
        confidence = evidence.get("confidence")
        confidence = confidence if isinstance(confidence, Mapping) else {}
        confidence_label = _CONFIDENCE_VI.get(str(confidence.get("label")), confidence.get("label"))
        score = evidence.get("effective_score")
        score_text = f"{float(score):.2f}" if isinstance(score, (int, float)) else "—"
        field_rows.append(
            "<tr>"
            f"<td><code>{_text(name)}</code></td><td>{_text(labels.get(name))}</td>"
            f"<td>{_text(value)}</td><td>{_text(confidence_label)}</td>"
            f"<td>{score_text}</td><td>{_text(evidence.get('status'))}</td></tr>"
        )

    confidence_cards = []
    for label, translated in _CONFIDENCE_VI.items():
        count = sum(
            1
            for evidence in resolutions.values()
            if isinstance(evidence, Mapping)
            and isinstance(evidence.get("confidence"), Mapping)
            and evidence["confidence"].get("label") == label
        )
        confidence_cards.append(
            f'<div class="confidence"><span>{escape(translated)}</span><strong>{count}</strong></div>'
        )

    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), list) else []
    artifact_rows = "".join(
        f"<tr><td>{_text(item.get('kind'))}</td><td><code>{_text(item.get('relative_path'))}</code></td></tr>"
        for item in artifacts
        if isinstance(item, Mapping)
    )

    html = f'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Kiểm thử trực quan document orchestrator</title>
<style>
:root{{--ink:#172033;--muted:#607089;--line:#d9e2ec;--brand:#0f6473;--accent:#f0a202}}
*{{box-sizing:border-box}}body{{margin:0;background:#f4f7fb;color:var(--ink);font:15px system-ui,sans-serif}}
main{{max-width:1400px;margin:32px auto;padding:0 20px}}header{{color:white;padding:28px;border-radius:18px;background:linear-gradient(125deg,#102a43,#0f6473 70%,#2c9ca6)}}
h1{{margin:0 0 8px}}h2{{margin-top:0}}.panel{{background:white;border:1px solid var(--line);border-radius:14px;padding:18px;margin:18px 0;overflow:auto}}
.metrics,.confidence-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}
.metric,.confidence{{background:#f8fafc;border:1px solid var(--line);border-radius:10px;padding:12px}}.metric strong,.confidence strong{{display:block;font-size:1.45rem;color:var(--brand)}}
table{{border-collapse:collapse;width:100%;min-width:760px}}th,td{{padding:9px;border:1px solid var(--line);text-align:left;vertical-align:top}}th{{background:#edf4f7}}
code{{background:#eef2f6;padding:2px 5px;border-radius:4px}}li{{margin:8px 0}}.warning{{border-left:5px solid var(--accent)}}
</style></head><body><main>
<header><h1>Kiểm thử trực quan document orchestrator production</h1>
<p>Tài liệu: <strong>{_text(document.get('name'))}</strong> · Nguồn: {_text(document.get('origin'))}</p></header>
<section class="panel"><h2>Tổng quan xử lý</h2><div class="metrics">
<div class="metric">Tổng số trang<strong>{_text(summary.get('pages', 0))}</strong></div>
<div class="metric">Trang đã OCR<strong>{_text(summary.get('ocr_pages', 0))}</strong></div>
<div class="metric">Trang bỏ qua<strong>{_text(summary.get('skipped_pages', 0))}</strong></div>
<div class="metric">Trường có giá trị<strong>{_text(summary.get('important_fields_populated', 0))}</strong></div>
<div class="metric">Bản ghi chỉnh định<strong>{_text(summary.get('setting_records', 0))}</strong></div>
<div class="metric">Cảnh báo<strong>{_text(summary.get('warnings', len(warnings)))}</strong></div>
</div></section>
<section class="panel"><h2>Định tuyến theo vai trò trang</h2><table><thead><tr><th>Trang</th><th>Vai trò</th><th>Trạng thái</th><th>Cảnh báo</th></tr></thead><tbody>{page_rows}</tbody></table></section>
<section class="panel warning"><h2>Cảnh báo được truyền tới kết quả cuối</h2><ul>{warning_items or '<li>Không có cảnh báo.</li>'}</ul></section>
<section class="panel"><h2>Năm mức độ tin cậy</h2><div class="confidence-grid">{''.join(confidence_cards)}</div></section>
<section class="panel"><h2>Thông tin quan trọng Page 1</h2><table><thead><tr><th>Khóa</th><th>Nhãn nguồn</th><th>Giá trị</th><th>Độ tin cậy</th><th>Điểm</th><th>Trạng thái</th></tr></thead><tbody>{''.join(field_rows) or '<tr><td colspan="6">Chưa có trường dữ liệu.</td></tr>'}</tbody></table></section>
<section class="panel"><h2>Artifact tương đối</h2><table><thead><tr><th>Loại</th><th>Đường dẫn</th></tr></thead><tbody>{artifact_rows}</tbody></table></section>
</main></body></html>'''
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sinh báo cáo trực quan document orchestrator bằng tiếng Việt")
    parser.add_argument("--input", type=Path, help="Đường dẫn extraction.json; bỏ trống để dùng fixture mẫu")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/document_orchestrator/orchestrator_review.html"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = json.loads(args.input.read_text(encoding="utf-8")) if args.input else demo_orchestrator_result()
    output = render_orchestrator_html(result, args.output)
    print(json.dumps({"output": str(output), "pages": len(result.get("pages", []))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
