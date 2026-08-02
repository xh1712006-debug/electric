"""Accented-Vietnamese visual review for progress, logging and stable errors."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from typing import Mapping, Sequence

from .observability import stream_logger
from .schemas import OcrRequest
from .service import RelayFormOcrService


REPOSITORY = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = REPOSITORY / "contracts" / "local_api" / "v1" / "error_catalog.json"


def _demo_progress() -> list[dict[str, object]]:
    return [
        {"sequence": 1, "stage": "validation", "event": "validation_started", "completed": 0, "total": 100, "message": "Bắt đầu kiểm tra yêu cầu OCR."},
        {"sequence": 2, "stage": "validation", "event": "validation_completed", "completed": 5, "total": 100, "message": "Yêu cầu và tài liệu đầu vào hợp lệ."},
        {"sequence": 3, "stage": "artifact_write", "event": "workspace_reserved", "completed": 10, "total": 100, "message": "Đã giữ độc quyền workspace của lời gọi."},
        {"sequence": 4, "stage": "rendering", "event": "rendering_completed", "completed": 20, "total": 100, "message": "Đã render xong các trang PDF."},
        {"sequence": 5, "stage": "detection", "event": "detection_completed", "completed": 38, "total": 100, "page_number": 1, "message": "Đã phát hiện văn bản trang 1."},
        {"sequence": 6, "stage": "recognition", "event": "recognition_completed", "completed": 55, "total": 100, "page_number": 1, "message": "Đã nhận dạng văn bản trang 1."},
        {"sequence": 7, "stage": "layout", "event": "layout_completed", "completed": 72, "total": 100, "page_number": 1, "message": "Đã phân tích bố cục trang 1."},
        {"sequence": 8, "stage": "artifact_write", "event": "artifact_manifest_finalized", "completed": 98, "total": 100, "message": "Đã hoàn tất manifest artifact."},
        {"sequence": 9, "stage": "pipeline", "event": "request_completed", "completed": 100, "total": 100, "terminal": True, "message": "Lời gọi OCR đã hoàn tất."},
    ]


def render_observability_review(
    output_path: Path | str,
    *,
    progress_events: Sequence[Mapping[str, object]],
    error_catalog: Mapping[str, object],
    log_lines: Sequence[Mapping[str, object]] = (),
) -> Path:
    output = Path(output_path)
    errors = error_catalog.get("errors") if isinstance(error_catalog.get("errors"), list) else []
    progress_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('sequence', '—')))}</td>"
        f"<td><code>{escape(str(item.get('stage', '—')))}</code></td>"
        f"<td>{escape(str(item.get('message', item.get('event', '—'))))}</td>"
        f"<td>{escape(str(item.get('page_number') if item.get('page_number') is not None else '—'))}</td>"
        f"<td><strong>{escape(str(item.get('completed', 0)))}/{escape(str(item.get('total', 100)))}</strong></td>"
        "</tr>"
        for item in progress_events
    )
    error_rows = "".join(
        "<tr>"
        f"<td><code>{escape(str(item.get('code', '—')))}</code></td>"
        f"<td>{escape(str(item.get('stage', '—')))}</td>"
        f"<td><span class=\"pill {'retry' if item.get('retryable') else 'stop'}\">{'Có' if item.get('retryable') else 'Không'}</span></td>"
        "</tr>"
        for item in errors
        if isinstance(item, Mapping)
    )
    safe_logs: Sequence[Mapping[str, object]] = log_lines or [
        {"level": "INFO", "correlation_id": "ticket-123", "stage": "validation", "event": "validation_completed"},
        {"level": "INFO", "correlation_id": "ticket-123", "stage": "recognition", "event": "recognition_completed", "page_number": 1},
        {"level": "ERROR", "correlation_id": "ticket-456", "stage": "layout", "event": "request_failed", "error_code": "LAYOUT_FAILED", "retryable": False},
    ]
    if len(safe_logs) > 10:
        safe_logs = [
            *safe_logs[:7],
            {"event": "preview_compacted", "omitted_log_lines": len(safe_logs) - 9},
            *safe_logs[-2:],
        ]
    logs = "\n".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in safe_logs)
    completed = max((int(item.get("completed", 0)) for item in progress_events), default=0)
    stages = len({str(item.get("stage")) for item in progress_events})
    html = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kiểm thử trực quan progress, logging và lỗi ổn định</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f7fb;color:#182236;font-family:Segoe UI,Arial,sans-serif}}main{{max-width:1180px;margin:auto;padding:28px}}
h1{{margin:0 0 7px}}h2{{margin-top:30px}}.sub{{color:#56657a}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}}
.card,.panel{{background:#fff;border:1px solid #dce5ef;border-radius:13px;padding:16px;box-shadow:0 2px 9px #1620330d}}.card small{{color:#66758a;display:block}}.card strong{{font-size:21px;display:block;margin-top:5px}}
.bar{{height:13px;background:#dfe8f3;border-radius:10px;overflow:hidden}}.bar i{{display:block;height:100%;width:{min(100, completed)}%;background:linear-gradient(90deg,#2878d0,#0ca678)}}
table{{width:100%;border-collapse:collapse;background:white;border-radius:12px;overflow:hidden}}th,td{{padding:10px 12px;border-bottom:1px solid #e5edf5;text-align:left}}th{{background:#eaf0f8}}
code,pre{{font-family:Consolas,monospace}}code{{background:#edf2f7;padding:2px 5px;border-radius:4px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#142033;color:#dce8f7;padding:16px;border-radius:12px}}
.pill{{padding:3px 8px;border-radius:999px;font-weight:600}}.retry{{background:#fff3bf;color:#8a5d00}}.stop{{background:#e6fcf5;color:#087f5b}}.guard{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
@media(max-width:760px){{.guard{{grid-template-columns:1fr}}table{{font-size:13px}}main{{padding:18px}}}}
</style></head><body><main>
<h1>Kiểm thử trực quan progress, logging và lỗi ổn định</h1>
<p class="sub">IMMEDIATE-007 — tiến độ tăng đơn điệu, log có correlation ID và lỗi public không lộ dữ liệu nội bộ.</p>
<section class="cards">
 <div class="card"><small>Sự kiện progress</small><strong>{len(progress_events)}</strong></div>
 <div class="card"><small>Stage đã quan sát</small><strong>{stages}</strong></div>
 <div class="card"><small>Error code ổn định</small><strong>{len(errors)}</strong></div>
 <div class="card"><small>Tiến độ cuối</small><strong>{completed}/100</strong></div>
</section>
<h2>Dòng tiến độ</h2><div class="bar"><i></i></div>
<table><thead><tr><th>#</th><th>Stage</th><th>Thông báo an toàn</th><th>Trang</th><th>Tiến độ</th></tr></thead><tbody>{progress_rows}</tbody></table>
<h2>Catalog lỗi public</h2><table><thead><tr><th>Error code</th><th>Stage</th><th>Có thể thử lại</th></tr></thead><tbody>{error_rows}</tbody></table>
<h2>Log JSON đã khử dữ liệu nhạy cảm</h2><pre>{escape(logs)}</pre>
<h2>Ba hàng rào vận hành</h2><section class="guard">
 <div class="panel"><strong>Callback không điều khiển pipeline</strong><p>Nếu callback lỗi, hệ thống ghi sự kiện và vô hiệu hóa callback; OCR vẫn tiếp tục.</p></div>
 <div class="panel"><strong>stdout luôn sạch</strong><p>CLI chỉ ghi result JSON vào stdout; progress và log vận hành đi sang stderr.</p></div>
 <div class="panel"><strong>Không lộ dữ liệu</strong><p>Log mặc định không chứa đường dẫn PDF, OCR text, exception message hoặc traceback.</p></div>
</section>
</main></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sinh báo cáo observability OCR bằng tiếng Việt.")
    parser.add_argument("--trace", type=Path, help="JSON array chứa ProgressEvent.as_dict()")
    parser.add_argument("--logs", type=Path, help="File JSONL để đọc hoặc ghi log đã khử dữ liệu nhạy cảm")
    parser.add_argument("--input-pdf", type=Path, help="Chạy public service thật và thu progress/log")
    parser.add_argument("--output-root", type=Path, help="Output root khi dùng --input-pdf")
    parser.add_argument("--correlation-id", help="Correlation ID khi dùng --input-pdf")
    parser.add_argument("--trace-output", type=Path, help="Nơi ghi progress trace của lần chạy thật")
    parser.add_argument("--result-json", type=Path, help="Nơi ghi typed result của lần chạy thật")
    parser.add_argument("--error-catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=Path("output/local_observability/observability_review.html"))
    args = parser.parse_args(argv)
    catalog = _read_json(args.error_catalog)
    if args.trace and args.input_pdf:
        raise SystemExit("Không dùng --trace cùng --input-pdf.")
    run_values = (args.input_pdf, args.output_root, args.correlation_id)
    if any(value is not None for value in run_values) and not all(value is not None for value in run_values):
        raise SystemExit("Cần đủ --input-pdf, --output-root và --correlation-id.")

    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.input_pdf:
        log_path = args.logs or output.parent / "structured_log.jsonl"
        trace_path = args.trace_output or output.parent / "progress_trace.json"
        result_path = args.result_json or output.parent / "public_result.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        captured = []
        with log_path.open("w", encoding="utf-8", newline="\n") as log_stream:
            logger = stream_logger(log_stream, name=f"relay_form_ocr.visual.{args.correlation_id}")
            result = RelayFormOcrService(logger=logger).process_pdf(
                OcrRequest(
                    input_pdf=args.input_pdf.resolve(),
                    output_root=args.output_root.resolve(),
                    correlation_id=args.correlation_id,
                ),
                progress=captured.append,
            )
        trace = [event.as_dict() for event in captured]
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        args.logs = log_path
    else:
        trace = _read_json(args.trace) if args.trace else _demo_progress()
    if not isinstance(catalog, Mapping) or not isinstance(trace, list):
        raise SystemExit("Catalog hoặc progress trace không hợp lệ.")
    logs: list[Mapping[str, object]] = []
    if args.logs:
        for line in args.logs.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if isinstance(item, Mapping):
                logs.append(item)
    output = render_observability_review(
        output,
        progress_events=[item for item in trace if isinstance(item, Mapping)],
        error_catalog=catalog,
        log_lines=logs,
    )
    print("Observability report generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["render_observability_review"]
