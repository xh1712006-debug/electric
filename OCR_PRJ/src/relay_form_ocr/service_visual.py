"""Vietnamese visual review for the synchronous local Python API."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path

from .schemas import OcrRequest, OcrResult
from .service import RelayFormOcrService


_STATUS_VI = {
    "success": "Thành công",
    "success_with_warnings": "Thành công có cảnh báo",
    "failed": "Thất bại",
}
_REVIEW_VI = {
    "not_required": "Không cần xem xét",
    "review_required": "Cần xem xét",
}
_ROLE_VI = {
    "page1": "Trang thông tin chính",
    "page2": "Trang 2 — bỏ qua theo chính sách",
    "page3_plus": "Trang thông số chỉnh định",
}
_PAGE_STATUS_VI = {
    "completed": "Đã xử lý",
    "skipped_by_policy": "Bỏ qua theo chính sách",
    "failed": "Thất bại",
}
_STAGE_VI = {
    "validation": "kiểm tra đầu vào",
    "rendering": "kết xuất PDF",
    "detection": "phát hiện chữ",
    "recognition": "nhận dạng chữ",
    "layout": "phân tích bố cục",
    "artifact_write": "ghi tệp bằng chứng",
    "pipeline": "pipeline OCR",
}
_WARNING_MESSAGE_VI = {
    "Candidate layout inferred from OCR geometry; it is not ground truth.":
        "Bố cục ứng viên được suy ra từ hình học OCR; đây chưa phải dữ liệu chuẩn.",
}


def render_service_review(result: OcrResult, output_path: Path | str) -> Path:
    """Render one typed terminal result as a dependency-free HTML report."""

    output = Path(output_path)
    fields = result.business.page1_fields if result.business is not None else None
    populated = 0
    review_fields = 0
    if fields is not None:
        for field_name in fields.__class__.model_fields:
            field = getattr(fields, field_name)
            populated += field.value is not None
            review_fields += field.resolution_status.value == "review_required"

    page_rows = "".join(
        "<tr>"
        f"<td>{page.page_number}</td>"
        f"<td>{escape(_ROLE_VI.get(page.role.value, page.role.value))}</td>"
        f"<td>{escape(_PAGE_STATUS_VI.get(page.status.value, page.status.value))}</td>"
        f"<td>{escape(_REVIEW_VI.get(page.review_status.value, page.review_status.value))}</td>"
        f"<td>{len(page.artifact_ids)}</td>"
        "</tr>"
        for page in result.pages
    ) or '<tr><td colspan="5">Không có kết quả trang.</td></tr>'

    warning_rows = "".join(
        "<li>"
        f"<strong>{escape(warning.code)}</strong> — {escape(_WARNING_MESSAGE_VI.get(warning.message, warning.message))}"
        f" (giai đoạn: {escape(_STAGE_VI.get(warning.stage.value, warning.stage.value))}"
        f"{', trang ' + str(warning.page_number) if warning.page_number else ''})"
        "</li>"
        for warning in result.warnings
    ) or "<li>Không có cảnh báo.</li>"

    error_html = "Không có lỗi public."
    if result.error is not None:
        error_html = (
            f"<strong>{escape(result.error.code.value)}</strong> — "
            f"{escape(result.error.message)} "
            f"(giai đoạn: {escape(_STAGE_VI.get(result.error.stage.value, result.error.stage.value))}, "
            f"có thể thử lại: {'Có' if result.error.retryable else 'Không'})"
        )

    settings = len(result.business.setting_records) if result.business is not None else 0
    notes = len(result.business.note_candidates) if result.business is not None else 0
    document_name = result.document.source_name if result.document is not None else "Chưa xác định"
    confidence_legend = "".join(
        f'<span class="confidence c{level}">{label}</span>'
        for level, label in enumerate(("Rất thấp", "Thấp", "Trung bình", "Cao", "Rất cao"), start=1)
    )
    html = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kiểm thử trực quan synchronous local Python API</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f4f7fb;color:#172033}}
main{{max-width:1120px;margin:0 auto;padding:28px}}
h1{{margin:0 0 6px}} h2{{margin-top:30px}}
.subtitle{{color:#52627a;margin-bottom:22px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}}
.card{{background:white;border:1px solid #dce4ef;border-radius:12px;padding:16px;box-shadow:0 2px 8px #1720330d}}
.card span{{display:block;color:#607087;font-size:13px}} .card strong{{display:block;margin-top:6px;font-size:20px}}
.ok{{color:#087f5b}} .failed{{color:#c92a2a}}
table{{width:100%;border-collapse:collapse;background:white;border-radius:10px;overflow:hidden}}
th,td{{padding:10px 12px;border-bottom:1px solid #e7edf5;text-align:left}} th{{background:#eaf0f8}}
.panel{{background:white;border:1px solid #dce4ef;border-radius:12px;padding:16px}}
.confidence{{display:inline-block;padding:7px 10px;border-radius:18px;margin:4px;font-weight:600}}
.c1{{background:#ffe3e3}} .c2{{background:#fff0d2}} .c3{{background:#fff8c5}} .c4{{background:#dff5e5}} .c5{{background:#c9f0dc}}
code{{background:#edf2f7;padding:2px 5px;border-radius:4px}}
</style>
</head>
<body><main>
<h1>Kiểm thử trực quan synchronous local Python API</h1>
<p class="subtitle">Báo cáo typed result v1 — nội dung tiếng Việt có dấu và không chứa đường dẫn nội bộ tuyệt đối.</p>
<section class="grid">
  <div class="card"><span>Trạng thái xử lý</span><strong class="{'failed' if result.status.value == 'failed' else 'ok'}">{escape(_STATUS_VI[result.status.value])}</strong></div>
  <div class="card"><span>Trạng thái xem xét</span><strong>{escape(_REVIEW_VI[result.review_status.value])}</strong></div>
  <div class="card"><span>Tài liệu</span><strong>{escape(document_name)}</strong></div>
  <div class="card"><span>Correlation ID</span><strong>{escape(result.correlation_id)}</strong></div>
  <div class="card"><span>Trang</span><strong>{len(result.pages)}</strong></div>
  <div class="card"><span>Trường Page 1 có giá trị</span><strong>{populated}/25</strong></div>
  <div class="card"><span>Trường cần xem xét</span><strong>{review_fields}</strong></div>
  <div class="card"><span>Thông số / Lưu ý</span><strong>{settings} / {notes}</strong></div>
  <div class="card"><span>Tệp bằng chứng</span><strong>{len(result.artifact_manifest.artifacts)}</strong></div>
  <div class="card"><span>Tổng thời gian</span><strong>{result.timing.elapsed_ms:.2f} ms</strong></div>
</section>
<h2>Năm mức confidence</h2><div class="panel">{confidence_legend}</div>
<h2>Vai trò và trạng thái từng trang</h2>
<table><thead><tr><th>Trang</th><th>Vai trò</th><th>Trạng thái</th><th>Xem xét</th><th>Tệp bằng chứng</th></tr></thead><tbody>{page_rows}</tbody></table>
<h2>Cảnh báo</h2><div class="panel"><ul>{warning_rows}</ul></div>
<h2>Lỗi public</h2><div class="panel">{error_html}</div>
<h2>Ranh giới an toàn</h2>
<div class="panel">Result chỉ chứa typed business data, checksum và relative artifact path. Raw OCR, ảnh render, debug layout và stack trace không được nhúng vào public payload.</div>
<p>Schema <code>{escape(result.schema_version)}</code> · Pipeline <code>{escape(result.pipeline_version)}</code> · Workspace <code>{escape(result.artifact_manifest.workspace_id)}</code></p>
</main></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sinh báo cáo trực quan cho local Python API.")
    parser.add_argument("--result-json", type=Path, help="Đọc typed OcrResult JSON đã có.")
    parser.add_argument("--input-pdf", type=Path, help="Chạy public service với một PDF_x.")
    parser.add_argument("--output-root", type=Path, help="Output root khi chạy public service.")
    parser.add_argument("--correlation-id", default="visual-immediate-004")
    parser.add_argument("--output", type=Path, default=Path("output/local_python_api/service_review.html"))
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.result_json is not None:
        if args.input_pdf is not None or args.output_root is not None:
            raise SystemExit("--result-json không dùng cùng --input-pdf/--output-root")
        result = OcrResult.model_validate_json(args.result_json.read_text(encoding="utf-8"))
    else:
        if args.input_pdf is None or args.output_root is None:
            raise SystemExit("Cần --result-json hoặc cả --input-pdf và --output-root")
        request = OcrRequest(
            input_pdf=args.input_pdf.resolve(),
            output_root=args.output_root.resolve(),
            correlation_id=args.correlation_id,
        )
        result = RelayFormOcrService().process_pdf(request)
        result_path = args.output.with_name("public_result.json")
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    output = render_service_review(result, args.output)
    # Keep console output ASCII-safe for Windows cp1258 terminals. The HTML and
    # JSON artifacts remain UTF-8 Vietnamese with full diacritics.
    print(f"Report: {output.resolve()}")
    print(f"Status: {result.status.value}; review: {result.review_status.value}")
    return 0 if result.status.value != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["render_service_review"]
