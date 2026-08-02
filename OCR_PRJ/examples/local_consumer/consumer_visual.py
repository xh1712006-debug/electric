"""Render an accented-Vietnamese review for sanitized consumer summaries."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


_OUTCOME_LABELS = {
    "ready_for_use": "Sẵn sàng sử dụng",
    "manual_review_required": "Bắt buộc duyệt thủ công",
    "failed": "OCR thất bại",
    "consumer_failure": "Consumer từ chối kết quả",
}


def _demo_summaries() -> list[dict[str, Any]]:
    base = {
        "consumer_schema_version": "1.0",
        "schema_version": "1.0",
        "pipeline_version": "0.7.0",
        "page_count": 3,
        "warning_count": 0,
        "artifact_count": 8,
        "manifest_audit": {
            "available": True,
            "source_unchanged": True,
            "verified_artifact_count": 8,
            "all_verified": True,
        },
        "progress": {"event_count": 24, "terminal_count": 1, "final_completed": 100, "final_total": 100},
        "public_error": None,
        "consumer_error": None,
    }
    return [
        {**base, "correlation_id": "demo-ready", "outcome": "ready_for_use", "processing_status": "success", "review_status": "not_required"},
        {**base, "correlation_id": "demo-review", "outcome": "manual_review_required", "processing_status": "success_with_warnings", "review_status": "review_required", "warning_count": 2},
        {**base, "correlation_id": "demo-failed", "outcome": "failed", "processing_status": "failed", "review_status": "review_required", "artifact_count": 2, "public_error": {"code": "DETECTION_FAILED", "stage": "detection", "retryable": True}},
    ]


def _load_summaries(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return _demo_summaries()
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload if isinstance(payload, list) else [payload]
    if not values or not all(isinstance(item, dict) for item in values):
        raise ValueError("summary phải là object hoặc danh sách object")
    return values


def _scenario(summary: Mapping[str, Any]) -> str:
    outcome = str(summary.get("outcome", "consumer_failure"))
    audit = summary.get("manifest_audit") if isinstance(summary.get("manifest_audit"), Mapping) else {}
    progress = summary.get("progress") if isinstance(summary.get("progress"), Mapping) else {}
    public_error = summary.get("public_error") if isinstance(summary.get("public_error"), Mapping) else {}
    error_text = "—"
    if public_error:
        retry = "có thể thử lại" if public_error.get("retryable") else "không tự thử lại"
        error_text = f"{public_error.get('code', 'UNKNOWN')} · {public_error.get('stage', 'pipeline')} · {retry}"
    audit_text = (
        f"{audit.get('verified_artifact_count', 0)}/{summary.get('artifact_count', 0)} artifact"
        if audit.get("available")
        else "Không có artifact để kiểm kê"
    )
    return f"""
      <article class="scenario scenario-{escape(outcome)}">
        <div class="scenario-head">
          <div><span class="status-mark" aria-hidden="true"></span><strong>{escape(_OUTCOME_LABELS.get(outcome, outcome))}</strong></div>
          <code>{escape(str(summary.get('correlation_id', 'không-có-id')))}</code>
        </div>
        <dl>
          <div><dt>Xử lý / duyệt</dt><dd>{escape(str(summary.get('processing_status', '—')))} / {escape(str(summary.get('review_status', '—')))}</dd></div>
          <div><dt>Trang / cảnh báo</dt><dd>{int(summary.get('page_count', 0))} / {int(summary.get('warning_count', 0))}</dd></div>
          <div><dt>Manifest</dt><dd>{escape(audit_text)}</dd></div>
          <div><dt>Source bất biến</dt><dd>{'Đã xác nhận' if audit.get('source_unchanged') is True else 'Không có bằng chứng'}</dd></div>
          <div><dt>Progress</dt><dd>{progress.get('event_count', 0)} events · terminal {progress.get('terminal_count', 0)} · {progress.get('final_completed', '—')}/{progress.get('final_total', '—')}</dd></div>
          <div><dt>Lỗi public</dt><dd>{escape(error_text)}</dd></div>
        </dl>
      </article>
    """


def render_consumer_review(summaries: Sequence[Mapping[str, Any]], output: Path) -> Path:
    rows = "".join(_scenario(item) for item in summaries)
    html = f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kiểm thử trực quan consumer local OCR</title>
  <style>
    :root {{ color-scheme: light; --ink:#172033; --muted:#5a6578; --line:#d8deea; --paper:#f5f7fb; --card:#fff; --good:#137a50; --review:#9a6500; --bad:#b13b42; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:var(--paper); font:15px/1.55 system-ui,"Segoe UI",sans-serif; }}
    main {{ max-width:1180px; margin:auto; padding:28px 22px 48px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(24px,4vw,38px); }}
    h2 {{ margin:30px 0 12px; font-size:20px; }}
    .lead {{ margin:0; color:var(--muted); max-width:850px; }}
    .flow {{ display:grid; grid-template-columns:repeat(5,1fr); gap:10px; margin-top:24px; }}
    .step {{ position:relative; padding:14px; background:var(--card); border:1px solid var(--line); border-radius:12px; }}
    .step b {{ display:block; }} .step span {{ color:var(--muted); font-size:13px; }}
    .scenarios {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(270px,1fr)); gap:14px; }}
    .scenario {{ background:var(--card); border:1px solid var(--line); border-top:4px solid var(--good); border-radius:12px; padding:16px; min-width:0; }}
    .scenario-manual_review_required {{ border-top-color:var(--review); }}
    .scenario-failed,.scenario-consumer_failure {{ border-top-color:var(--bad); }}
    .scenario-head {{ display:flex; justify-content:space-between; gap:10px; align-items:flex-start; flex-wrap:wrap; }}
    .status-mark {{ display:inline-block; width:10px; height:10px; border-radius:50%; background:var(--good); margin-right:8px; }}
    .scenario-manual_review_required .status-mark {{ background:var(--review); }}
    .scenario-failed .status-mark,.scenario-consumer_failure .status-mark {{ background:var(--bad); }}
    code {{ overflow-wrap:anywhere; }}
    dl {{ margin:14px 0 0; }} dl div {{ display:grid; grid-template-columns:120px 1fr; gap:10px; padding:8px 0; border-top:1px solid var(--line); }}
    dt {{ color:var(--muted); }} dd {{ margin:0; overflow-wrap:anywhere; }}
    .guard {{ border-left:4px solid var(--review); padding:12px 16px; background:var(--card); }}
    @media (max-width:760px) {{ .flow {{ grid-template-columns:1fr; }} dl div {{ grid-template-columns:1fr; gap:2px; }} }}
  </style>
</head>
<body>
<main>
  <h1>Kiểm thử trực quan consumer local OCR</h1>
  <p class="lead">Consumer chỉ sử dụng public contract, kiểm tra schema và artifact trước khi quyết định. Kết quả cần duyệt không bao giờ được coi là dữ liệu đã phê duyệt.</p>
  <section class="flow" aria-label="Luồng kiểm tra consumer">
    <div class="step"><b>1. Gọi API</b><span>Một PDF_x và correlation ID</span></div>
    <div class="step"><b>2. Kiểm tra schema</b><span>OcrResult v1 hợp lệ</span></div>
    <div class="step"><b>3. Đọc manifest</b><span>Relative path và source bất biến</span></div>
    <div class="step"><b>4. Kiểm tra checksum</b><span>Mọi artifact khớp metadata</span></div>
    <div class="step"><b>5. Áp dụng review gate</b><span>Sẵn sàng, duyệt tay hoặc từ chối</span></div>
  </section>
  <h2>Kịch bản quyết định</h2>
  <section class="scenarios">{rows}</section>
  <h2>Hàng rào an toàn</h2>
  <p class="guard"><strong>Không auto-approve:</strong> Page 3+, Lưu ý, warning hoặc <code>review_required</code> luôn chuyển sang duyệt thủ công. Schema, manifest hay checksum sai khiến consumer từ chối toàn bộ kết quả.</p>
</main>
</body>
</html>
"""
    target = output.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sinh báo cáo consumer bằng tiếng Việt.")
    parser.add_argument("--summary", type=Path, help="Summary JSON của consumer; bỏ qua để dùng demo.")
    parser.add_argument("--output", type=Path, default=Path("output/local_consumer/consumer_review.html"))
    args = parser.parse_args(argv)
    output = render_consumer_review(_load_summaries(args.summary), args.output)
    print(f"Da tao bao cao consumer: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
