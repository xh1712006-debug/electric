from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.layout_analysis.page1 import (
    CandidateScoringEngine,
    ConfidenceLevel,
    SpatialCandidate,
    SpatialRelation,
    TopologyAnchorResolver,
    load_field_rule_registry,
)
from src.layout_analysis.page1.relationship_visual import demo_relationship_cases, render_relationship_html


def node(identifier, bbox, *, scale=1.0, value=None, source_cell=None):
    return SpatialCandidate(
        identifier,
        tuple(coordinate * scale for coordinate in bbox),
        page_width=1200 * scale,
        page_height=1600 * scale,
        value=value,
        source_cell=source_cell,
    )


class Page1RelationshipResolverTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_field_rule_registry()
        self.resolver = TopologyAnchorResolver(self.registry)

    def test_all_supported_spatial_relations(self):
        anchor = node("anchor", (100, 100, 200, 120))
        fixtures = {
            SpatialRelation.ABOVE: (110, 50, 190, 70),
            SpatialRelation.BELOW: (110, 150, 190, 170),
            SpatialRelation.LEFT: (20, 100, 80, 120),
            SpatialRelation.RIGHT: (220, 100, 300, 120),
            SpatialRelation.SAME_ROW: (220, 103, 300, 123),
            SpatialRelation.SAME_COLUMN: (110, 150, 190, 170),
            SpatialRelation.SAME_ROW_RIGHT: (220, 103, 300, 123),
        }
        for relation, bbox in fixtures.items():
            with self.subTest(relation=relation.value):
                evidence = self.resolver.relate(node(relation.value, bbox), anchor, relation)
                self.assertTrue(evidence.matched, evidence.as_dict())
                self.assertGreater(evidence.score, 0)

    def test_direction_and_distance_failures_are_explained(self):
        anchor = node("anchor", (100, 100, 200, 120))
        wrong_direction = self.resolver.relate(node("wrong", (110, 150, 190, 170)), anchor, "above")
        too_far = self.resolver.relate(node("far", (110, 400, 190, 420)), anchor, "below")

        self.assertFalse(wrong_direction.matched)
        self.assertEqual(wrong_direction.reason, "direction_mismatch")
        self.assertFalse(too_far.matched)
        self.assertEqual(too_far.reason, "normalized_distance_exceeded")

    def test_normalized_distance_is_stable_across_dpi_and_page_scale(self):
        results = []
        for scale in (0.5, 1.0, 2.0, 4.0):
            candidate = node("candidate", (110, 50, 190, 70), scale=scale)
            anchor = node("anchor", (100, 100, 200, 120), scale=scale)
            results.append(self.resolver.relate(candidate, anchor, "above"))

        self.assertTrue(all(item.matched for item in results))
        self.assertEqual({item.normalized_distance for item in results}, {1.5})
        self.assertEqual(len({item.score for item in results}), 1)

    def test_page_reference_anchors_ticket_above_in_right_header(self):
        ticket = node("ticket", (820, 50, 1120, 80), value="A1-29-2026/E5.8/220")
        page_reference = node("page", (920, 105, 1020, 135), value="1/5")

        resolution = self.resolver.resolve("ticket_number", ticket, {"page_reference": [page_reference]})

        self.assertTrue(resolution.eligible)
        self.assertEqual(resolution.topology_score, 1)
        self.assertGreater(resolution.anchor_score, 0)
        self.assertEqual(resolution.anchors[0].relation, SpatialRelation.ABOVE)
        self.assertEqual(resolution.anchors[0].anchor_candidate_id, "page")

    def test_ticket_context_checks_page_reference_below(self):
        ticket = node("ticket", (820, 50, 1120, 80), value="A1-29-2026/E5.8/220")
        page_reference = node("page", (920, 105, 1020, 135), value="1/5")

        resolution = self.resolver.resolve("page_reference", page_reference, {"ticket_number": [ticket]})

        self.assertTrue(resolution.eligible)
        self.assertEqual(resolution.topology_score, 1)
        self.assertGreater(resolution.anchor_score, 0)
        self.assertEqual(resolution.anchors[0].relation, SpatialRelation.BELOW)

    def test_relay_name_anchors_version_same_row_right(self):
        relay_name = node(
            "relay-name", (620, 420, 770, 450), value="SEL311L",
            source_cell="table_01:cover_row_1:right_primary",
        )
        version = node(
            "version", (880, 420, 1010, 450), value="V6.7.0.2",
            source_cell="table_01:cover_row_1:right_secondary",
        )

        resolution = self.resolver.resolve("relay_version", version, {"relay_name": [relay_name]})

        self.assertTrue(resolution.eligible)
        self.assertEqual(resolution.topology_score, 1)
        self.assertGreater(resolution.anchor_score, 0)
        self.assertEqual(resolution.anchors[0].relation, SpatialRelation.SAME_ROW_RIGHT)

    def test_wrong_table_cell_is_hard_capped_and_cannot_beat_correct_owner(self):
        relay_name = node(
            "relay-name", (620, 420, 770, 450), value="SEL311L",
            source_cell="table_01:cover_row_1:right_primary",
        )
        correct = node(
            "correct", (880, 420, 1010, 450), value="V6.7.0.2",
            source_cell="table_01:cover_row_1:right_secondary",
        )
        wrong = node(
            "wrong", (300, 420, 430, 450), value="V1",
            source_cell="table_01:cover_row_1:left",
        )
        correct_resolution = self.resolver.resolve("relay_version", correct, {"relay_name": [relay_name]})
        wrong_resolution = self.resolver.resolve("relay_version", wrong, {"relay_name": [relay_name]})
        soft_scores = {"alias": 1, "separator": 1, "value_validation": 1, "ocr_confidence": 1}

        decision = CandidateScoringEngine(self.registry).decide([
            wrong_resolution.to_field_candidate(component_scores=soft_scores),
            correct_resolution.to_field_candidate(component_scores=soft_scores),
        ])

        self.assertFalse(wrong_resolution.eligible)
        self.assertEqual(wrong_resolution.hard_constraints[0].max_confidence_level, ConfidenceLevel.LOW)
        self.assertEqual(decision.selected_candidate_id, "correct")
        scored_wrong = next(item for item in decision.candidates if item.candidate.candidate_id == "wrong")
        self.assertLess(scored_wrong.score, 40)

    def test_wrong_header_region_is_hard_capped(self):
        ticket_in_body = node("ticket-in-body", (820, 700, 1120, 730), value="A1-29-2026/E5.8/220")

        resolution = self.resolver.resolve("ticket_number", ticket_in_body, {})
        scored = CandidateScoringEngine(self.registry).score_candidate(
            resolution.to_field_candidate(component_scores={
                "alias": 1, "separator": 1, "value_validation": 1, "ocr_confidence": 1,
            })
        )

        self.assertFalse(resolution.eligible)
        self.assertEqual(resolution.topology[0].actual, "right_body")
        self.assertEqual(resolution.hard_constraints[0].max_confidence_level, ConfidenceLevel.LOW)
        self.assertLess(scored.score, 40)

    def test_missing_cell_is_not_evaluated_instead_of_false_hard_failure(self):
        candidate = node("unknown-cell", (880, 420, 1010, 450), value="V6.7")

        resolution = self.resolver.resolve("relay_version", candidate, {})

        self.assertTrue(resolution.eligible)
        self.assertEqual(resolution.topology[0].status, "not_evaluated")
        self.assertEqual(resolution.hard_constraints, ())

    def test_visual_report_contains_svg_relations_distances_and_mismatch(self):
        cases = demo_relationship_cases()
        with TemporaryDirectory() as temporary:
            output = render_relationship_html(cases, self.resolver, Path(temporary) / "review.html")
            html = output.read_text(encoding="utf-8")

        self.assertIn("<svg", html)
        self.assertIn("Ticket above page reference", html)
        self.assertIn("same_row_right", html)
        self.assertIn("normalized", html)
        self.assertIn("topology_mismatch", html)
        self.assertIn("eligible=<b>false</b>", html)


if __name__ == "__main__":
    unittest.main()
