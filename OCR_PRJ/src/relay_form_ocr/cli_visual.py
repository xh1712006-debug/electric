"""Vietnamese visual review for the local CLI JSON adapter."""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

from .cli import CliExitCode
from .schemas import OcrResult


_EXIT_ROWS = (
    (CliExitCode.SUCCESS, "Thành công", "Kết quả success hoặc success_with_warnings hợp lệ."),
    (CliExitCode.USAGE_OR_REQUEST, "Lỗi lệnh hoặc request", "Thiếu tham số, tổ hợp sai hoặc request không qua typed validation."),
    (CliExitCode.INPUT, "Lỗi PDF đầu vào", "Không tìm thấy file, không phải file hoặc PDF không hợp lệ."),
    (CliExitCode.OUTPUT, "Lỗi đầu ra", "Workspace, artifact hoặc file JSON kết quả không ghi được."),
    (CliExitCode.PROCESSING, "Lỗi xử lý", "Render, nhận dạng, bố cục hoặc pipeline thất bại."),
    (CliExitCode.INTERNAL, "Lỗi nội bộ adapter", "CLI không thể tạo hoặc tuần tự hóa terminal result."),
)


def render_cli_review(output_path: Path | str, result: OcrResult | None = None) -> Path:
    """Render the CLI contract and an optional real terminal result."""

    output = Path(output_path)
    exit_rows = "".join(
        "<tr>"
        f"<td><strong>{int(code)}</strong></td>"
        f"<td>{escape(title)}</td>"
        f"<td>{escape(description)}</td>"
        "</tr>"
        for code, title, description in _EXIT_ROWS
    )
    if result is None:
        real_result = "Chưa nạp kết quả OCR thật; phần contract CLI vẫn có thể kiểm tra độc lập."
        result_status = "Chưa có"
        correlation_id = "—"
    else:
        real_result = (
            f"Đã đọc và xác thực OcrResult schema {escape(result.schema_version)}; "
            f"có {len(result.pages)} trang, {len(result.warnings)} cảnh báo và "
            f"{len(result.artifact_manifest.artifacts)} artifact."
        )
        result_status = escape(result.status.value)
        correlation_id = escape(result.correlation_id)

    html = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kiểm thử trực quan CLI JSON cục bộ</title>
<style>
*{{box-sizing:border-box}} body{{margin:0;background:#f3f6fb;color:#172033;font-family:Segoe UI,Arial,sans-serif}}
main{{max-width:1120px;margin:auto;padding:28px}} h1{{margin:0 0 6px}} h2{{margin-top:30px}}
.subtitle{{color:#52627a}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:13px}}
.card,.panel{{background:#fff;border:1px solid #dbe4f0;border-radius:13px;padding:17px;box-shadow:0 2px 10px #1720330d}}
.card small{{display:block;color:#607087}} .card strong{{display:block;font-size:20px;margin-top:6px}}
.flow{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;align-items:stretch}}
.step{{padding:15px;border-radius:11px;background:#eaf2ff;border-left:4px solid #2878d0}}
.stream{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} .stdout{{border-top:4px solid #087f5b}} .stderr{{border-top:4px solid #d97706}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden}}
th,td{{padding:11px 13px;text-align:left;border-bottom:1px solid #e6edf6}} th{{background:#eaf0f8}}
code{{background:#edf2f7;padding:2px 5px;border-radius:4px}} .ok{{color:#087f5b}}
@media(max-width:760px){{.flow,.stream{{grid-template-columns:1fr}}}}
</style>
</head>
<body><main>
<h1>Kiểm thử trực quan CLI JSON cục bộ</h1>
<p class="subtitle">IMMEDIATE-005 — một PDF_x, một terminal JSON, exit code ổn định và không trộn log vào stdout.</p>
<section class="grid">
  <div class="card"><small>Entry point</small><strong><code>python -m src.relay_form_ocr</code></strong></div>
  <div class="card"><small>Định dạng</small><strong class="ok">UTF-8 JSON</strong></div>
  <div class="card"><small>Trạng thái mẫu</small><strong>{result_status}</strong></div>
  <div class="card"><small>Correlation ID</small><strong>{correlation_id}</strong></div>
</section>
<h2>Luồng gọi adapter</h2>
<section class="flow">
  <div class="step"><strong>1. Parse</strong><br>Đọc input, output root và correlation ID.</div>
  <div class="step"><strong>2. Validate</strong><br>Tạo typed <code>OcrRequest</code>.</div>
  <div class="step"><strong>3. Process</strong><br>Gọi duy nhất <code>RelayFormOcrService</code>.</div>
  <div class="step"><strong>4. Emit</strong><br>Xuất <code>OcrResult</code> và exit code.</div>
</section>
<h2>Tách luồng máy và luồng vận hành</h2>
<section class="stream">
  <div class="panel stdout"><strong>stdout — dữ liệu cho máy</strong><p>Chỉ chứa đúng một JSON khi không dùng <code>--output-json</code>. Không chứa progress, model warning hoặc log.</p></div>
  <div class="panel stderr"><strong>stderr — log vận hành</strong><p>Chứa trạng thái bắt đầu/kết thúc và mọi output phát sinh trong lúc OCR chạy.</p></div>
</section>
<h2>Bảng exit code</h2>
<table><thead><tr><th>Mã</th><th>Ý nghĩa</th><th>Điều kiện</th></tr></thead><tbody>{exit_rows}</tbody></table>
<h2>Kết quả OCR dùng để review</h2>
<div class="panel">{real_result}</div>
<h2>Kiểm tra Unicode trên PowerShell</h2>
<div class="panel">Đặt <code>[Console]::OutputEncoding = [System.Text.Encoding]::UTF8</code>, nhận stdout rồi chuyển bằng <code>ConvertFrom-Json</code>. Test tự động xác nhận tiếng Việt có dấu không bị biến dạng.</div>
</main></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sinh báo cáo tiếng Việt cho CLI JSON cục bộ.")
    parser.add_argument("--result-json", type=Path, help="Typed OcrResult JSON đã có (không bắt buộc).")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/local_cli_json/cli_review.html"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = None
    if args.result_json is not None:
        result = OcrResult.model_validate_json(args.result_json.read_text(encoding="utf-8"))
    output = render_cli_review(args.output, result)
    print(f"Report: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["render_cli_review"]
