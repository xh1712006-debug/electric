"""Accented-Vietnamese visual review for the typed local API contract."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .schemas import OcrRequest, OcrResult, PUBLIC_MODEL_TYPES


DEFAULT_FIXTURE_DIR = Path("contracts/local_api/v1/examples")
DEFAULT_OUTPUT = Path("output/local_api_schema/schema_review.html")

_SCENARIO_VI = {
    "success": "Thành công",
    "success_with_warnings": "Thành công có cảnh báo",
    "review_required": "Cần người dùng xem xét",
    "failure": "Thất bại có kiểm soát",
}
_STATUS_VI = {
    "success": "Thành công",
    "success_with_warnings": "Thành công có cảnh báo",
    "failed": "Thất bại",
}
_REVIEW_VI = {
    "not_required": "Không cần xem xét",
    "review_required": "Cần xem xét",
}


def validate_contract_fixtures(fixture_dir: Path = DEFAULT_FIXTURE_DIR) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for path in sorted(fixture_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        try:
            request = OcrRequest.model_validate(payload["request"])
            result = OcrResult.model_validate(payload["result"])
            reviews.append({
                "file": path.name,
                "scenario": payload.get("scenario", path.stem),
                "valid": True,
                "correlation_id": request.correlation_id,
                "status": result.status.value,
                "review_status": result.review_status.value,
                "pages": len(result.pages),
                "warnings": len(result.warnings),
                "artifacts": len(result.artifact_manifest.artifacts),
                "error": None,
            })
        except (KeyError, ValidationError, ValueError) as exc:
            reviews.append({
                "file": path.name,
                "scenario": payload.get("scenario", path.stem),
                "valid": False,
                "error": str(exc),
            })
    return reviews


def render_schema_review_html(reviews: list[dict[str, Any]], output_path: Path) -> Path:
    scenario_rows = "".join(
        "<tr>"
        f"<td><code>{escape(str(item['file']))}</code></td>"
        f"<td>{escape(_SCENARIO_VI.get(str(item['scenario']), str(item['scenario'])))}</td>"
        f"<td><span class={'pass' if item['valid'] else 'fail'}>{'Hợp lệ' if item['valid'] else 'Không hợp lệ'}</span></td>"
        f"<td>{escape(_STATUS_VI.get(str(item.get('status')), str(item.get('status', '—'))))}</td>"
        f"<td>{escape(_REVIEW_VI.get(str(item.get('review_status')), str(item.get('review_status', '—'))))}</td>"
        f"<td>{item.get('pages', '—')}</td><td>{item.get('warnings', '—')}</td>"
        f"<td>{item.get('artifacts', '—')}</td>"
        "</tr>"
        for item in reviews
    )
    model_cards = "".join(
        '<article class="model">'
        f"<h3>{escape(model.__name__)}</h3>"
        f"<strong>{len(model.model_fields)}</strong> trường trực tiếp"
        f"<p>{escape(', '.join(model.model_fields) or 'Không có trường trực tiếp')}</p>"
        "</article>"
        for model in PUBLIC_MODEL_TYPES
    )
    valid_count = sum(bool(item["valid"]) for item in reviews)
    html = f'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Kiểm thử trực quan typed schema v1</title>
<style>
:root{{--ink:#182433;--muted:#607089;--line:#d8e1ec;--brand:#0e6473;--ok:#147a42;--bad:#b3261e}}
*{{box-sizing:border-box}}body{{margin:0;background:#f4f7fb;color:var(--ink);font:15px system-ui,sans-serif}}
main{{max-width:1450px;margin:30px auto;padding:0 20px}}header{{padding:28px;border-radius:18px;color:white;background:linear-gradient(125deg,#102a43,#0e6473 68%,#2c9ca6)}}
h1{{margin:0 0 8px}}.panel{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px;margin:18px 0;overflow:auto}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}.metric,.model{{border:1px solid var(--line);border-radius:11px;padding:13px;background:#f9fbfd}}
.metric strong,.model strong{{display:block;font-size:1.55rem;color:var(--brand)}}.models{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px}}
.model h3{{margin:0 0 8px}}.model p{{color:var(--muted);overflow-wrap:anywhere}}table{{border-collapse:collapse;width:100%;min-width:900px}}th,td{{padding:9px;border:1px solid var(--line);text-align:left;vertical-align:top}}th{{background:#edf4f7}}
.pass{{color:var(--ok);font-weight:750}}.fail{{color:var(--bad);font-weight:750}}code{{background:#eef2f6;padding:2px 5px;border-radius:4px}}li{{margin:7px 0}}
</style></head><body><main>
<header><h1>Kiểm thử trực quan typed request/result/error schema</h1>
<p>Contract v1.0 · Pydantic v2 · Dữ liệu tiếng Việt được bảo toàn qua JSON UTF-8.</p></header>
<section class="panel"><h2>Tổng quan</h2><div class="summary">
<div class="metric">Fixture hợp lệ<strong>{valid_count}/{len(reviews)}</strong></div>
<div class="metric">Model public<strong>{len(PUBLIC_MODEL_TYPES)}</strong></div>
<div class="metric">Canonical Page 1 fields<strong>25</strong></div>
<div class="metric">Phiên bản schema<strong>1.0</strong></div>
</div></section>
<section class="panel"><h2>Bốn tình huống contract</h2><table><thead><tr><th>Fixture</th><th>Tình huống</th><th>Validation</th><th>Trạng thái</th><th>Xem xét</th><th>Trang</th><th>Cảnh báo</th><th>Artifact</th></tr></thead><tbody>{scenario_rows}</tbody></table></section>
<section class="panel"><h2>Danh mục typed models</h2><div class="models">{model_cards}</div></section>
<section class="panel"><h2>Biên an toàn được schema khóa</h2><ul>
<li>Request chỉ nhận đúng một đường dẫn PDF tuyệt đối, một output root tuyệt đối và correlation ID an toàn.</li>
<li>Public result từ chối field lạ, raw OCR, traceback, stack trace và đường dẫn máy chủ tuyệt đối.</li>
<li>Artifact chỉ dùng đường dẫn tương đối dạng POSIX, SHA-256 và kích thước không âm.</li>
<li>Thất bại bắt buộc có error, business bằng null và trạng thái cần xem xét.</li>
<li>Setting record và ghi chú Page 3+ luôn cần người dùng xem xét.</li>
</ul></section>
<section class="panel"><h2>Năm mức độ tin cậy</h2><p>Rất thấp (1) · Thấp (2) · Trung bình (3) · Cao (4) · Rất cao (5). Level, label và score 0–100 phải nhất quán.</p></section>
</main></body></html>'''
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sinh báo cáo typed schema bằng tiếng Việt")
    parser.add_argument("--fixture-dir", type=Path, default=DEFAULT_FIXTURE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    reviews = validate_contract_fixtures(args.fixture_dir)
    output = render_schema_review_html(reviews, args.output)
    valid = sum(bool(item["valid"]) for item in reviews)
    print(json.dumps({"output": str(output), "valid": valid, "total": len(reviews)}, ensure_ascii=False))
    return 0 if reviews and valid == len(reviews) else 1


if __name__ == "__main__":
    raise SystemExit(main())
