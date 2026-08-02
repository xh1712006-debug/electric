"""Render a Vietnamese per-PDF acceptance report from persisted evidence."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


_STATE_LABELS = {
    "running": "Đang chạy",
    "passed": "Đạt acceptance",
    "failed": "Không đạt acceptance",
}
_VERDICT_LABELS = {"passed": "Đạt", "failed": "Không đạt"}
_OUTCOME_LABELS = {
    "ready_for_use": "Sẵn sàng sử dụng",
    "manual_review_required": "Bắt buộc duyệt thủ công",
    "failed": "Lỗi đúng contract",
}


def _text(value: object, fallback: str = "—") -> str:
    return fallback if value is None or value == "" else str(value)


def _duration(value: object) -> str:
    try:
        milliseconds = float(value)
    except (TypeError, ValueError):
        return "—"
    seconds = milliseconds / 1000
    if seconds < 60:
        return f"{seconds:.1f} giây"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)} phút {remainder:.0f} giây"


def _execution_row(item: Mapping[str, Any]) -> str:
    verdict = str(item.get("verdict", "failed"))
    outcome = str(item.get("consumer_outcome", "failed"))
    audit = item.get("artifact_audit") if isinstance(item.get("artifact_audit"), Mapping) else {}
    verified = audit.get("verified_artifact_count", 0)
    artifacts = item.get("artifact_count", 0)
    warnings = item.get("warning_count", 0)
    error = item.get("public_error") if isinstance(item.get("public_error"), Mapping) else None
    error_text = "—" if not error else f"{error.get('code', 'UNKNOWN')} / {error.get('stage', 'pipeline')}"
    return f"""
      <tr class="row-{escape(verdict)}">
        <td><strong>{escape(_text(item.get('display_name')))}</strong><br><code>{escape(_text(item.get('execution_id')))}</code></td>
        <td>{escape(_text(item.get('layout_family')))}</td>
        <td><span class="status status-{escape(verdict)}">{escape(_VERDICT_LABELS.get(verdict, verdict))}</span></td>
        <td>{escape(_OUTCOME_LABELS.get(outcome, outcome))}<br><span class="muted">{escape(_text(item.get('processing_status')))} / {escape(_text(item.get('review_status')))}</span></td>
        <td class="number">{int(item.get('page_count') or 0)}</td>
        <td class="number">{int(warnings or 0)}</td>
        <td>{int(verified or 0)}/{int(artifacts or 0)}<br><span class="muted">source {'bất biến' if item.get('source_unchanged') is True else 'chưa xác nhận'}</span></td>
        <td>{escape(_duration(item.get('elapsed_ms')))}</td>
        <td><code>{escape(error_text)}</code></td>
      </tr>
    """


def _family_rows(manifest: Mapping[str, Any]) -> str:
    required = list(manifest.get("required_layout_families", []))
    executions = list(manifest.get("executions", []))
    rows = []
    for family in required:
        members = [item for item in executions if item.get("layout_family") == family]
        passed = sum(item.get("verdict") == "passed" for item in members)
        pages = sum(int(item.get("page_count") or 0) for item in members)
        status = "Đã phủ" if passed else "Chưa phủ"
        css = "passed" if passed else "failed"
        rows.append(
            f"<tr><td><code>{escape(str(family))}</code></td>"
            f"<td class='number'>{passed}/{len(members)}</td>"
            f"<td class='number'>{pages}</td>"
            f"<td><span class='status status-{css}'>{status}</span></td></tr>"
        )
    return "".join(rows)


def _repeatability_rows(summary: Mapping[str, Any]) -> str:
    values = summary.get("repeatability", [])
    if not values:
        return '<p class="empty">Corpus chưa cấu hình PDF chạy lặp.</p>'
    rows = []
    for item in values:
        stable = item.get("stable") is True
        css = "passed" if stable else "failed"
        label = "Ổn định" if stable else "Không ổn định"
        digest = _text(item.get("stable_result_sha256"))
        rows.append(
            f"<tr><td><code>{escape(_text(item.get('case_id')))}</code></td>"
            f"<td class='number'>{int(item.get('attempts') or 0)}/{int(item.get('expected_attempts') or 0)}</td>"
            f"<td><span class='status status-{css}'>{label}</span></td>"
            f"<td><code>{escape(digest)}</code></td></tr>"
        )
    return '<div class="table-wrap"><table><thead><tr><th>PDF case</th><th>Lần chạy</th><th>Kết luận</th><th>Stable-result SHA-256</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>"


def render_acceptance_review(manifest: Mapping[str, Any], output: Path | str) -> Path:
    """Write one standalone UTF-8 report without embedding OCR/business text."""

    summary = manifest.get("summary") if isinstance(manifest.get("summary"), Mapping) else {}
    state = str(manifest.get("state", "running"))
    executions = list(manifest.get("executions", []))
    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), Mapping) else {}
    packages = runtime.get("packages") if isinstance(runtime.get("packages"), Mapping) else {}
    execution_rows = "".join(_execution_row(item) for item in executions)
    gpu = runtime.get("gpu") if isinstance(runtime.get("gpu"), Mapping) else None
    device_text = "CPU"
    if runtime.get("requested_device") == "gpu":
        device_text = f"GPU — {_text(gpu.get('torch_device_name') if gpu else None, 'không xác định')}"
    html = f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Acceptance từng PDF — Local OCR API</title>
  <style>
    :root {{ color-scheme:light; --ink:#182033; --muted:#667085; --line:#d8dfeb; --paper:#f5f7fb; --card:#fff; --good:#10734b; --good-bg:#eaf7f0; --bad:#a7353d; --bad-bg:#fff0f1; --review:#8a5c00; --review-bg:#fff8e5; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink); font:14px/1.5 system-ui,"Segoe UI",sans-serif; }}
    main {{ max-width:1440px; margin:auto; padding:28px 22px 52px; }}
    h1 {{ margin:0 0 6px; font-size:clamp(25px,4vw,40px); }} h2 {{ margin:30px 0 12px; font-size:20px; }}
    p {{ margin:0; }} .lead,.muted {{ color:var(--muted); }}
    .summary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; margin:22px 0; }}
    .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:15px; min-width:0; }}
    .card span {{ display:block; color:var(--muted); }} .card strong {{ display:block; margin-top:3px; font-size:24px; overflow-wrap:anywhere; }}
    .state {{ display:inline-block; margin-top:14px; padding:5px 10px; border-radius:999px; font-weight:700; background:var(--review-bg); color:var(--review); }}
    .state-passed {{ background:var(--good-bg); color:var(--good); }} .state-failed {{ background:var(--bad-bg); color:var(--bad); }}
    .table-wrap {{ overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:12px; }}
    table {{ width:100%; border-collapse:collapse; min-width:760px; }} th,td {{ padding:11px 12px; text-align:left; vertical-align:top; border-bottom:1px solid var(--line); }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.035em; }} tr:last-child td {{ border-bottom:0; }}
    .number {{ text-align:right; font-variant-numeric:tabular-nums; }} code {{ overflow-wrap:anywhere; }}
    .status {{ display:inline-block; padding:3px 8px; border-radius:999px; font-weight:700; white-space:nowrap; }}
    .status-passed {{ background:var(--good-bg); color:var(--good); }} .status-failed {{ background:var(--bad-bg); color:var(--bad); }}
    .guard {{ margin-top:24px; padding:14px 16px; background:var(--review-bg); border-left:4px solid var(--review); }}
    .runtime {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:8px 18px; }} .runtime div {{ overflow-wrap:anywhere; }}
    .empty {{ padding:16px; background:var(--card); border:1px solid var(--line); border-radius:12px; color:var(--muted); }}
    @media (max-width:700px) {{ main {{ padding:20px 14px 40px; }} .summary {{ grid-template-columns:1fr 1fr; }} }}
  </style>
</head>
<body>
<main>
  <h1>Acceptance từng PDF — Local OCR API</h1>
  <p class="lead">Kiểm chứng contract, runtime, tính lặp lại, source bất biến và artifact. Báo cáo này không phải phép đo độ chính xác OCR.</p>
  <span class="state state-{escape(state)}">{escape(_STATE_LABELS.get(state, state))}</span>
  <section class="summary" aria-label="Tổng hợp acceptance">
    <div class="card"><span>Execution hoàn tất</span><strong>{int(summary.get('completed_execution_count') or 0)}/{int(summary.get('expected_execution_count') or 0)}</strong></div>
    <div class="card"><span>Layout family đã phủ</span><strong>{int(summary.get('covered_family_count') or 0)}/{int(summary.get('required_family_count') or 0)}</strong></div>
    <div class="card"><span>Execution không đạt</span><strong>{int(summary.get('failed_execution_count') or 0)}</strong></div>
    <div class="card"><span>Thiết bị chạy</span><strong>{escape(device_text)}</strong></div>
  </section>
  <h2>Độ phủ layout family</h2>
  <div class="table-wrap"><table><thead><tr><th>Layout family</th><th>Execution đạt</th><th>Tổng trang</th><th>Độ phủ</th></tr></thead><tbody>{_family_rows(manifest)}</tbody></table></div>
  <h2>Kết quả theo từng PDF</h2>
  <div class="table-wrap"><table><thead><tr><th>PDF / execution</th><th>Layout family</th><th>Acceptance</th><th>Trạng thái consumer</th><th>Trang</th><th>Cảnh báo</th><th>Artifact</th><th>Thời gian</th><th>Lỗi public</th></tr></thead><tbody>{execution_rows}</tbody></table></div>
  <h2>Repeatability</h2>
  {_repeatability_rows(summary)}
  <h2>Runtime và phiên bản</h2>
  <section class="card runtime">
    <div><span class="muted">Run ID</span><br><code>{escape(_text(manifest.get('run_id')))}</code></div>
    <div><span class="muted">Schema / runner</span><br><code>{escape(_text(manifest.get('acceptance_schema_version')))} / {escape(_text(manifest.get('runner_version')))}</code></div>
    <div><span class="muted">Python / nền tảng</span><br>{escape(_text(runtime.get('python_version')))} · {escape(_text(runtime.get('machine')))}</div>
    <div><span class="muted">Pipeline</span><br><code>{escape(_text(executions[0].get('pipeline_version') if executions else None))}</code></div>
    <div><span class="muted">PyTorch / Paddle</span><br>{escape(_text(packages.get('torch')))} / {escape(_text(packages.get('paddlepaddle')))}</div>
    <div><span class="muted">Bắt đầu / kết thúc</span><br>{escape(_text(manifest.get('started_at_utc')))}<br>{escape(_text(manifest.get('completed_at_utc')))}</div>
  </section>
  <p class="guard"><strong>Hàng rào nghiệp vụ:</strong> <code>review_required</code>, Page 3+, Lưu ý hoặc warning vẫn bắt buộc duyệt thủ công. Acceptance đạt chỉ chứng minh caller nhận được kết quả ổn định và artifacts hợp lệ; chưa chứng minh dữ liệu OCR đúng khi chưa có ground truth.</p>
</main>
</body>
</html>
"""
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sinh báo cáo acceptance tiếng Việt.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    output = render_acceptance_review(manifest, args.output)
    print(f"Đã tạo báo cáo acceptance: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
