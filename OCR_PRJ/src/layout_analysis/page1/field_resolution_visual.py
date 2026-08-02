"""Báo cáo HTML tiếng Việt cho field-resolution evidence Page 1."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from typing import Any, Mapping

from .extractor import extract_page1


_STATUS_VI = {
    "auto_selected": "Tự động chọn",
    "review_required": "Cần xem xét",
    "not_configured": "Chưa cấu hình",
}
_CONFIDENCE_VI = {
    "very_low": "Rất thấp",
    "low": "Thấp",
    "medium": "Trung bình",
    "high": "Cao",
    "very_high": "Rất cao",
}


def _block(identifier: str, text: str, bbox: tuple[int, int, int, int], confidence: float = 0.95) -> dict[str, Any]:
    return {
        "block_id": identifier,
        "text": text,
        "bbox_pixel": list(bbox),
        "recognition_score": confidence,
    }


def demo_field_resolution_payload() -> dict[str, Any]:
    """Build a deterministic visual fixture through the production extractor."""

    blocks = [
        _block("ticket", "Số: A1-29-2026/E5.8/220", (700, 40, 1120, 70)),
        _block("page", "Trang: 1/5", (850, 90, 1000, 120)),
        _block("station", "Trạm: 220kV Việt Trì", (100, 160, 420, 195)),
        _block("relay", "Tên rơ-le: SEL311L", (500, 300, 750, 335)),
        _block("invalid-version", "Phiên bản rơ-le: không rõ", (800, 300, 1120, 335)),
        _block("purpose", "Mục đích ban hành phiếu: Cải tạo trạm", (100, 500, 700, 535)),
        _block("footer", "Xác nhận của người kiểm tra", (100, 1200, 450, 1230)),
    ]
    return extract_page1(
        {
            "document_id": "demo-field-resolution",
            "page_number": 1,
            "image_path": "demo-page-1.png",
            "block_predictions": blocks,
        },
        {"available": False, "image_width": 1200, "image_height": 1600, "regions": []},
    )


def render_field_resolution_html(payload: Mapping[str, Any], output_path: Path) -> Path:
    fields = payload.get("fields")
    resolutions = payload.get("field_resolution")
    if not isinstance(fields, Mapping) or not isinstance(resolutions, Mapping):
        raise ValueError("Payload phải có fields và field_resolution.")

    rows: list[str] = []
    details: list[str] = []
    for field_name, evidence_value in resolutions.items():
        if not isinstance(evidence_value, Mapping):
            continue
        evidence = evidence_value
        field = fields.get(field_name)
        value = field.get("text") if isinstance(field, Mapping) else None
        status = str(evidence.get("status", "not_configured"))
        confidence = evidence.get("confidence")
        confidence_label = (
            _CONFIDENCE_VI.get(str(confidence.get("label")), str(confidence.get("label")))
            if isinstance(confidence, Mapping) else "—"
        )
        rule = evidence.get("matched_rule")
        rule_text = "—"
        if isinstance(rule, Mapping):
            rule_text = str(rule.get("value") or rule.get("expected") or rule.get("type") or "—")
        anchor = evidence.get("anchor")
        anchor_text = "—"
        if isinstance(anchor, Mapping):
            anchor_text = f"{anchor.get('anchor_field')} / {anchor.get('relation')}"
        score = evidence.get("effective_score")
        score_text = f"{float(score):.2f}" if isinstance(score, (int, float)) else "—"
        margin = evidence.get("winner_margin")
        margin_text = f"{float(margin):.2f}" if isinstance(margin, (int, float)) else "—"
        rows.append(
            f'<tr class="{escape(status)}">'
            f'<td><code>{escape(str(field_name))}</code></td>'
            f'<td>{escape(str(value)) if value is not None else "<em>null</em>"}</td>'
            f'<td>{escape(str(evidence.get("resolution_method", "—")))}</td>'
            f'<td>{escape(rule_text)}</td><td>{escape(anchor_text)}</td>'
            f'<td>{score_text}</td><td>{escape(confidence_label)}</td><td>{margin_text}</td>'
            f'<td>{escape(_STATUS_VI.get(status, status))}</td></tr>'
        )
        decision = evidence.get("decision")
        breakdown = evidence.get("score_breakdown")
        reasons = decision.get("reasons", []) if isinstance(decision, Mapping) else []
        breakdown_rows = ""
        if isinstance(breakdown, Mapping):
            breakdown_rows = "".join(
                '<tr>'
                f'<td><code>{escape(str(component))}</code></td>'
                f'<td>{float(item.get("signal", 0)):.4f}</td>'
                f'<td>{float(item.get("weight", 0)):.2f}</td>'
                f'<td>{float(item.get("points", 0)):.4f}</td></tr>'
                for component, item in breakdown.items()
                if isinstance(item, Mapping)
            )
        hard_cap = False
        if isinstance(decision, Mapping):
            hard_cap = any(
                candidate.get("hard_cap_level") is not None
                for candidate in decision.get("candidates", [])
                if isinstance(candidate, Mapping)
            )
        details.append(
            '<details class="card">'
            f'<summary><code>{escape(str(field_name))}</code> — '
            f'{escape(_STATUS_VI.get(status, status))}</summary>'
            f'<p><strong>Lý do quyết định:</strong> {escape(", ".join(str(item) for item in reasons) or "Không có")}</p>'
            f'<p><strong>Hard-cap mức 2:</strong> {"Có" if hard_cap else "Không"}</p>'
            '<table><thead><tr><th>Thành phần</th><th>Tín hiệu</th><th>Trọng số</th><th>Điểm</th></tr></thead>'
            f'<tbody>{breakdown_rows or "<tr><td colspan=\"4\">Chưa có score breakdown</td></tr>"}</tbody></table>'
            '</details>'
        )

    document = f'''<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Kiểm thử tích hợp field resolution Page 1</title>
<style>
body{{font:15px system-ui,sans-serif;max-width:1500px;margin:28px auto;padding:0 18px;background:#f4f6fa;color:#172033}}
.panel,.card{{background:#fff;border:1px solid #d9dfeb;border-radius:12px;padding:16px;margin:14px 0;overflow:auto}}
table{{border-collapse:collapse;width:100%;min-width:1050px}}th,td{{border:1px solid #d9dfeb;padding:8px;text-align:left;vertical-align:top}}
th{{background:#edf3f8}}code{{background:#eef1f6;padding:2px 4px;border-radius:4px}}
.auto_selected td:last-child{{color:#15713b;font-weight:700}}.review_required td:last-child{{color:#a63328;font-weight:700}}
summary{{cursor:pointer;font-weight:700}}em{{color:#657083}}
</style></head><body>
<h1>Kiểm thử trực quan tích hợp phân giải trường Page 1</h1>
<p>Báo cáo đối chiếu giá trị production với alias, topology, anchor, validator, điểm số, độ tin cậy và winner margin.</p>
<section class="panel"><h2>Tổng hợp quyết định</h2><table><thead><tr>
<th>Trường chuẩn</th><th>Giá trị production</th><th>Phương thức</th><th>Rule khớp</th><th>Anchor</th>
<th>Điểm hiệu lực</th><th>Độ tin cậy</th><th>Winner margin</th><th>Trạng thái</th>
</tr></thead><tbody>{''.join(rows)}</tbody></table></section>
<h2>Chi tiết score breakdown và hard-cap</h2>{''.join(details)}
</body></html>'''
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tạo báo cáo field-resolution Page 1 bằng tiếng Việt")
    parser.add_argument("--input", type=Path, help="page1_layout.json đã có field_resolution")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/page1_field_resolution/field_resolution_review.html"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = (
        json.loads(args.input.read_text(encoding="utf-8"))
        if args.input else demo_field_resolution_payload()
    )
    output = render_field_resolution_html(payload, args.output)
    print(json.dumps({
        "output": str(output),
        "field_count": len(payload.get("field_resolution", {})),
    }, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
