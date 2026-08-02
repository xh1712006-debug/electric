"""Render topology/anchor resolution evidence as dependency-free HTML/SVG."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .relationships import SpatialCandidate, SpatialResolution, TopologyAnchorResolver
from .rules import load_field_rule_registry


def _node(payload: Mapping[str, Any]) -> SpatialCandidate:
    return SpatialCandidate(
        candidate_id=str(payload["candidate_id"]),
        bbox=tuple(payload["bbox"]),
        page_width=float(payload["page_width"]),
        page_height=float(payload["page_height"]),
        value=payload.get("value"),
        source_cell=payload.get("source_cell"),
    )


def demo_relationship_cases() -> tuple[dict[str, Any], ...]:
    page = {"page_width": 1200, "page_height": 1600}
    ticket = SpatialCandidate("ticket", (820, 50, 1120, 80), **page, value="A1-29-2026/E5.8/220")
    page_reference = SpatialCandidate("page-reference", (920, 105, 1020, 135), **page, value="1/5")
    relay_name = SpatialCandidate(
        "relay-name", (620, 420, 770, 450), **page, value="SEL311L",
        source_cell="table_01:cover_row_1:right_primary",
    )
    relay_version = SpatialCandidate(
        "relay-version", (880, 420, 1010, 450), **page, value="V6.7.0.2",
        source_cell="table_01:cover_row_1:right_secondary",
    )
    wrong_version = SpatialCandidate(
        "wrong-cell-version", (300, 420, 430, 450), **page, value="V1",
        source_cell="table_01:cover_row_1:left",
    )
    return (
        {"title": "Ticket above page reference", "canonical_field": "ticket_number", "candidate": ticket,
         "anchors": {"page_reference": (page_reference,)}},
        {"title": "Page reference below ticket", "canonical_field": "page_reference", "candidate": page_reference,
         "anchors": {"ticket_number": (ticket,)}},
        {"title": "Relay version same row and right", "canonical_field": "relay_version", "candidate": relay_version,
         "anchors": {"relay_name": (relay_name,)}},
        {"title": "Wrong Table-01 ownership", "canonical_field": "relay_version", "candidate": wrong_version,
         "anchors": {"relay_name": (relay_name,)}},
    )


def _fixture_cases(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    cases = []
    for index, item in enumerate(payload["cases"]):
        cases.append({
            "title": item.get("title", f"Case {index + 1}"),
            "canonical_field": item["canonical_field"],
            "candidate": _node(item["candidate"]),
            "anchors": {
                name: tuple(_node(anchor) for anchor in values)
                for name, values in item.get("anchors", {}).items()
            },
        })
    return tuple(cases)


def render_relationship_html(
    cases: Sequence[Mapping[str, Any]],
    resolver: TopologyAnchorResolver,
    output_path: Path,
) -> Path:
    panels: list[str] = []
    for case in cases:
        candidate: SpatialCandidate = case["candidate"]
        anchors: Mapping[str, Sequence[SpatialCandidate]] = case.get("anchors", {})
        resolution: SpatialResolution = resolver.resolve(case["canonical_field"], candidate, anchors)
        scale_x = 420 / candidate.page_width
        scale_y = 480 / candidate.page_height

        def rect(node: SpatialCandidate, css: str, label: str) -> str:
            x1, y1, x2, y2 = node.bbox
            return (
                f'<rect class="{css}" x="{x1 * scale_x:.2f}" y="{y1 * scale_y:.2f}" '
                f'width="{(x2 - x1) * scale_x:.2f}" height="{(y2 - y1) * scale_y:.2f}"/>'
                f'<text x="{x1 * scale_x:.2f}" y="{max(12, y1 * scale_y - 4):.2f}">{escape(label)}</text>'
            )

        shapes = [rect(candidate, "candidate good" if resolution.eligible else "candidate bad", candidate.candidate_id)]
        for field, nodes in anchors.items():
            for anchor in nodes:
                shapes.append(rect(anchor, "anchor", f"{field}: {anchor.candidate_id}"))
                cx, cy = candidate.center
                ax, ay = anchor.center
                shapes.append(
                    f'<line x1="{cx * scale_x:.2f}" y1="{cy * scale_y:.2f}" '
                    f'x2="{ax * scale_x:.2f}" y2="{ay * scale_y:.2f}"/>'
                )
        topology = "; ".join(f"{item.expected}={item.status}" for item in resolution.topology) or "none"
        anchor_text = "; ".join(
            f"{item.relation.value}: {item.reason}, normalized distance={item.relation_evidence.normalized_distance:.4f}"
            if item.relation_evidence else f"{item.relation.value}: {item.reason}"
            for item in resolution.anchors
        ) or "none"
        constraints = ", ".join(item.reason for item in resolution.hard_constraints) or "none"
        panels.append(
            '<section class="panel">'
            f'<h2>{escape(str(case["title"]))}</h2>'
            f'<p><code>{escape(str(case["canonical_field"]))}</code> · eligible=<b>{str(resolution.eligible).lower()}</b> · '
            f'topology={resolution.topology_score:.4f} · anchor={resolution.anchor_score:.4f}</p>'
            f'<svg viewBox="0 0 420 480" role="img" aria-label="{escape(str(case["title"]))}">'
            '<rect class="page" x="1" y="1" width="418" height="478"/>' + "".join(shapes) + '</svg>'
            f'<p><strong>Topology:</strong> {escape(topology)}</p>'
            f'<p><strong>Anchor:</strong> {escape(anchor_text)}</p>'
            f'<p><strong>Hard constraints:</strong> {escape(constraints)}</p>'
            '</section>'
        )
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Page-1 topology and anchor review</title><style>
body{{font:15px system-ui,sans-serif;max-width:1120px;margin:28px auto;padding:0 18px;background:#f4f6fa;color:#182033}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(470px,1fr));gap:16px}}.panel{{background:#fff;border:1px solid #d8deea;border-radius:12px;padding:16px}}
h1,h2{{margin:0 0 10px}}svg{{width:100%;height:330px;background:#fafbfe}}.page{{fill:#fff;stroke:#aab4c5}}
rect.candidate{{stroke-width:2}}rect.good{{fill:#b7ebc6;stroke:#18733d}}rect.bad{{fill:#ffd0ca;stroke:#a63228}}
rect.anchor{{fill:#b9dcff;stroke:#23639d;stroke-width:2}}line{{stroke:#7b4dc2;stroke-width:2;stroke-dasharray:5 4}}text{{font:11px system-ui;fill:#182033}}
code{{background:#eef2f8;padding:2px 5px;border-radius:4px}}
</style></head><body><h1>Page-1 topology and anchor review</h1>
<p>Green candidates are eligible; red candidates have a topology hard cap. Blue boxes are anchors.</p>
<div class="grid">{''.join(panels)}</div></body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render Page-1 topology/anchor evidence as HTML/SVG")
    parser.add_argument("--input", type=Path, help="Optional UTF-8 relationship fixture JSON")
    parser.add_argument("--overlay", type=Path, help="Optional field-rule overlay JSON")
    parser.add_argument("--output", type=Path, default=Path("output/page1_relationships/relationship_review.html"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases = _fixture_cases(json.loads(args.input.read_text(encoding="utf-8"))) if args.input else demo_relationship_cases()
    resolver = TopologyAnchorResolver(load_field_rule_registry(overlay_path=args.overlay))
    output = render_relationship_html(cases, resolver, args.output)
    decisions = [
        resolver.resolve(case["canonical_field"], case["candidate"], case.get("anchors", {})).as_dict()
        for case in cases
    ]
    print(json.dumps({"output": str(output), "cases": decisions}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
