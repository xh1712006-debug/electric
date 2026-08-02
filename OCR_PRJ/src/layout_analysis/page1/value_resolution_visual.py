"""Tạo báo cáo HTML tiếng Việt cho alias, dấu hai chấm và value rules."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .rules import load_field_rule_registry
from .value_resolution import AliasSeparatorResolver, ConfigurableValueValidator, ValueValidationResult


_STATUS_VI = {
    "passed": "Hợp lệ",
    "failed": "Không hợp lệ",
    "partial": "Hợp lệ một phần",
    "not_evaluated": "Chưa đánh giá",
}


def demo_alias_cases() -> tuple[dict[str, Any], ...]:
    return (
        {"title": "Alias ngắn có dấu hai chấm", "blocks": ["Số: A1-29-2026/E5.8/220"]},
        {"title": "Alias cụ thể được ưu tiên", "blocks": ["Phiên bản rơ-le: V6.7.0.2"]},
        {"title": "Alias dùng chung cho nhiều trường", "blocks": ["Phiên bản: V3.4"]},
        {"title": "Không nhầm với Số hiệu", "blocks": ["Số hiệu rơ-le: PCS-902-1"]},
        {"title": "Không nhận nhầm Số trang", "blocks": ["Số trang: 1/5"]},
        {"title": "Label và value tách ở hai OCR block", "blocks": ["Mục đích ban hành phiếu", "Nâng cấp trạm"]},
        {"title": "Validator bắt buộc thất bại", "blocks": ["Phiên bản rơ-le: không rõ"]},
    )


def demo_validation_cases() -> tuple[dict[str, Any], ...]:
    unit_rule = {"type": "unit_suffix", "values": ["A"], "required": True, "origin": "user"}
    return (
        {"title": "Đơn vị viết liền", "field": "demo_current", "value": "20A", "rules": [unit_rule]},
        {"title": "Đơn vị có khoảng trắng", "field": "demo_current", "value": "20 A", "rules": [unit_rule]},
        {"title": "Sai đơn vị bắt buộc", "field": "demo_current", "value": "20V", "rules": [unit_rule]},
        {"title": "Khoảng số gồm cả hai biên", "field": "demo_range", "value": "10,5", "rules": [
            {"type": "numeric_range", "minimum": 10.5, "maximum": 20, "required": True, "origin": "user"}
        ]},
        {"title": "Regex phải khớp toàn bộ", "field": "demo_code", "value": "MC-273", "rules": [
            {"type": "regex", "pattern": r"MC-\d{3}", "required": True, "origin": "user"}
        ]},
        {"title": "Enum không phân biệt dấu và hoa thường", "field": "demo_enum", "value": "ĐÓNG", "rules": [
            {"type": "enum", "values": ["đóng", "mở"], "required": True, "origin": "user"}
        ]},
    )


def _fixture(payload: Mapping[str, Any]) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    aliases = tuple({"title": item.get("title", "Ca kiểm tra alias"), "blocks": item["blocks"]} for item in payload.get("alias_cases", []))
    validations = tuple({
        "title": item.get("title", "Ca kiểm tra giá trị"),
        "field": item.get("field", "demo"),
        "value": item["value"],
        "rules": item["rules"],
    } for item in payload.get("validation_cases", []))
    return aliases, validations


def render_value_resolution_html(
    alias_cases: Sequence[Mapping[str, Any]],
    validation_cases: Sequence[Mapping[str, Any]],
    alias_resolver: AliasSeparatorResolver,
    validator: ConfigurableValueValidator,
    output_path: Path,
) -> Path:
    alias_cards: list[str] = []
    for case in alias_cases:
        blocks = tuple(str(item) for item in case["blocks"])
        candidates = alias_resolver.resolve_blocks(blocks)
        rows = []
        for candidate in candidates:
            validation = validator.validate(candidate.canonical_field, candidate.value_text)
            hard_cap = "Có" if validation.hard_constraints else "Không"
            rows.append(
                '<tr>'
                f'<td><code>{escape(candidate.canonical_field)}</code></td>'
                f'<td>{escape(candidate.alias)}</td><td>{escape(candidate.value_text or "<trống>")}</td>'
                f'<td>{"Có" if candidate.separator_present else "Không"}</td>'
                f'<td>{escape(_STATUS_VI[validation.status])}</td><td>{hard_cap}</td>'
                '</tr>'
            )
        if not rows:
            rows.append('<tr><td colspan="6" class="empty">Không tìm thấy alias hợp lệ</td></tr>')
        original = "<br>".join(escape(block) for block in blocks)
        alias_cards.append(
            '<section class="card">'
            f'<h2>{escape(str(case["title"]))}</h2><p><strong>OCR đầu vào:</strong><br>{original}</p>'
            '<table><thead><tr><th>Trường chuẩn</th><th>Alias khớp</th><th>Giá trị</th>'
            '<th>Có dấu hai chấm</th><th>Kiểm tra giá trị</th><th>Hard-cap mức 2</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></section>'
        )

    validation_rows: list[str] = []
    for case in validation_cases:
        result: ValueValidationResult = validator.validate_rules(
            str(case["field"]), str(case["value"]), tuple(case["rules"])
        )
        rules = ", ".join(item.rule_type for item in result.rules)
        reasons = ", ".join(item.reason for item in result.rules)
        validation_rows.append(
            '<tr>'
            f'<td>{escape(str(case["title"]))}</td><td>{escape(str(case["value"]))}</td>'
            f'<td>{escape(result.normalized_value)}</td><td><code>{escape(rules)}</code></td>'
            f'<td class="{result.status}">{escape(_STATUS_VI[result.status])}</td>'
            f'<td>{"Có" if result.hard_constraints else "Không"}</td><td><code>{escape(reasons)}</code></td>'
            '</tr>'
        )
    document = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Kiểm thử alias và giá trị Page 1</title><style>
body{{font:15px system-ui,sans-serif;max-width:1240px;margin:28px auto;padding:0 18px;background:#f4f6fa;color:#172033}}
.card,.validation{{background:white;border:1px solid #d9dfeb;border-radius:12px;padding:16px;margin:14px 0;overflow:auto}}
h1,h2{{margin:0 0 10px}}table{{border-collapse:collapse;width:100%;min-width:760px}}th,td{{border:1px solid #d9dfeb;padding:8px;text-align:left;vertical-align:top}}
th{{background:#edf3f8}}code{{background:#eef1f6;padding:2px 4px;border-radius:4px}}.passed{{color:#15713b;font-weight:700}}.failed{{color:#a63328;font-weight:700}}
.partial{{color:#8a5b00;font-weight:700}}.not_evaluated,.empty{{color:#657083;font-style:italic}}
</style></head><body><h1>Kiểm thử trực quan alias, dấu hai chấm và bộ kiểm tra giá trị</h1>
<p>Báo cáo hiển thị alias được nhận diện, giá trị tách ra, kết quả validator và hard-cap mức 2.</p>
{''.join(alias_cards)}
<section class="validation"><h2>Các loại bộ kiểm tra giá trị cấu hình</h2><table><thead><tr>
<th>Ca kiểm tra</th><th>Giá trị gốc</th><th>Giá trị chuẩn hóa</th><th>Rule</th>
<th>Kết quả</th><th>Hard-cap mức 2</th><th>Lý do kỹ thuật</th></tr></thead>
<tbody>{''.join(validation_rows)}</tbody></table></section></body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tạo báo cáo trực quan alias và value validators bằng tiếng Việt")
    parser.add_argument("--input", type=Path, help="Fixture JSON UTF-8 tùy chọn")
    parser.add_argument("--overlay", type=Path, help="Field-rule overlay JSON tùy chọn")
    parser.add_argument("--output", type=Path, default=Path("output/page1_value_resolution/value_resolution_review.html"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    alias_cases, validation_cases = (
        _fixture(json.loads(args.input.read_text(encoding="utf-8")))
        if args.input else (demo_alias_cases(), demo_validation_cases())
    )
    registry = load_field_rule_registry(overlay_path=args.overlay)
    alias_resolver = AliasSeparatorResolver(registry)
    validator = ConfigurableValueValidator(registry)
    output = render_value_resolution_html(
        alias_cases, validation_cases, alias_resolver, validator, args.output
    )
    print(json.dumps({
        "output": str(output),
        "alias_case_count": len(alias_cases),
        "validator_case_count": len(validation_cases),
    }, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
