"""Generate a dependency-free HTML review for candidate scoring decisions."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from typing import Any

from .rules import load_field_rule_registry
from .scoring import CandidateScoringEngine, FieldCandidate, HardConstraint, ScoringDecision


def _candidate(payload: dict[str, Any]) -> FieldCandidate:
    constraints = tuple(
        HardConstraint(
            reason=item["reason"],
            max_confidence_level=item.get("max_confidence_level", 2),
        )
        for item in payload.get("hard_constraints", [])
    )
    return FieldCandidate(
        candidate_id=payload["candidate_id"],
        canonical_field=payload["canonical_field"],
        value=payload.get("value"),
        component_scores=payload.get("component_scores", {}),
        hard_constraints=constraints,
    )


def demo_candidates() -> tuple[FieldCandidate, ...]:
    return (
        FieldCandidate(
            candidate_id="topology-and-anchor-winner",
            canonical_field="relay_version",
            value="V6.7.0.2",
            component_scores={
                "topology": 1.0, "anchor": 1.0, "alias": 1.0,
                "separator": 1.0, "value_validation": 1.0, "ocr_confidence": 0.95,
            },
        ),
        FieldCandidate(
            candidate_id="high-runner-up",
            canonical_field="relay_version",
            value="SEL311L",
            component_scores={
                "topology": 0.65, "anchor": 0.65, "alias": 0.65,
                "separator": 0.65, "value_validation": 0.65, "ocr_confidence": 0.65,
            },
        ),
        FieldCandidate(
            candidate_id="medium-without-separator",
            canonical_field="relay_version",
            value="V6.7",
            component_scores={
                "topology": 0.7, "anchor": 0.5, "alias": 0.7,
                "separator": 0.0, "value_validation": 0.7, "ocr_confidence": 0.9,
            },
        ),
        FieldCandidate(
            candidate_id="low-evidence",
            canonical_field="relay_version",
            value="V6",
            component_scores={name: 0.25 for name in (
                "topology", "anchor", "alias", "separator", "value_validation", "ocr_confidence"
            )},
        ),
        FieldCandidate(
            candidate_id="very-low-evidence",
            canonical_field="relay_version",
            value="unknown",
            component_scores={name: 0.05 for name in (
                "topology", "anchor", "alias", "separator", "value_validation", "ocr_confidence"
            )},
        ),
        FieldCandidate(
            candidate_id="hard-validator-failure",
            canonical_field="relay_version",
            value="not-a-version",
            component_scores={
                "topology": 1.0, "anchor": 1.0, "alias": 1.0,
                "separator": 1.0, "value_validation": 0.0, "ocr_confidence": 0.98,
            },
            hard_constraints=(HardConstraint.value_validation_failure(),),
        ),
    )


def render_scoring_html(decision: ScoringDecision, output_path: Path) -> Path:
    """Render an auditable scoring decision as one portable HTML file."""

    rows: list[str] = []
    for candidate in decision.candidates:
        parts = []
        for name, score in candidate.breakdown.items():
            width = max(0.0, min(100.0, score.signal * 100.0))
            parts.append(
                f'<div class="component"><span>{escape(name)}</span>'
                f'<div class="track"><i style="width:{width:.2f}%"></i></div>'
                f'<b>{score.points:.2f}/{score.weight:.2f}</b></div>'
            )
        constraints = ", ".join(
            escape(item.reason) + f" (cap L{int(item.max_confidence_level)})"
            for item in candidate.candidate.hard_constraints
        ) or "none"
        rows.append(
            '<section class="candidate">'
            f'<h2>{escape(candidate.candidate.candidate_id)}</h2>'
            f'<p class="value">{escape(candidate.candidate.value or "<null>")}</p>'
            f'<p><strong>Score:</strong> {candidate.score:.4f} '
            f'(raw {candidate.raw_score:.4f}) · '
            f'<strong>Confidence:</strong> L{int(candidate.confidence_level)} '
            f'{escape(candidate.confidence_level.label)} · '
            f'<strong>Hard constraints:</strong> {constraints}</p>'
            + "".join(parts)
            + "</section>"
        )
    selected = escape(decision.selected_candidate_id or "none — manual review required")
    reasons = ", ".join(escape(reason) for reason in decision.reasons)
    margin = "n/a" if decision.winner_margin is None else f"{decision.winner_margin:.4f}"
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Page-1 candidate scoring review</title><style>
body{{font:15px system-ui,sans-serif;max-width:1050px;margin:32px auto;padding:0 18px;background:#f5f7fb;color:#172033}}
header,.candidate{{background:white;border:1px solid #dce2ec;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 2px 8px #1720330c}}
h1,h2{{margin:0 0 8px}}.value{{font:600 17px ui-monospace,monospace;color:#0b5b70}}
.component{{display:grid;grid-template-columns:150px 1fr 105px;gap:12px;align-items:center;margin:8px 0}}
.track{{height:12px;background:#e8edf5;border-radius:9px;overflow:hidden}}.track i{{display:block;height:100%;background:#168aad}}
.auto_selected{{color:#147d42}}.review_required{{color:#ae3f32}}code{{background:#edf1f7;padding:2px 5px;border-radius:4px}}
</style></head><body><header><h1>Candidate scoring review</h1>
<p>Field: <code>{escape(decision.canonical_field or "none")}</code> · Status:
<strong class="{escape(decision.status)}">{escape(decision.status)}</strong></p>
<p>Selected: <code>{selected}</code> · Margin: {margin} (minimum {decision.winner_margin_minimum:g}) ·
score minimum: {decision.auto_select_minimum:g}</p><p>Reasons: {reasons}</p></header>
{''.join(rows)}</body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render Page-1 candidate scores as portable HTML")
    parser.add_argument("--input", type=Path, help="Optional UTF-8 candidate fixture JSON")
    parser.add_argument("--overlay", type=Path, help="Optional field-rule overlay JSON")
    parser.add_argument("--output", type=Path, default=Path("output/page1_scoring/scoring_review.html"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.input:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        candidates = tuple(_candidate(item) for item in payload["candidates"])
    else:
        candidates = demo_candidates()
    registry = load_field_rule_registry(overlay_path=args.overlay)
    decision = CandidateScoringEngine(registry).decide(candidates)
    rendered = render_scoring_html(decision, args.output)
    print(json.dumps({"output": str(rendered), "decision": decision.as_dict()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
