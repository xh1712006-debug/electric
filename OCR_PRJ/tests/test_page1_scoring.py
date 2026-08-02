import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.layout_analysis.page1 import (
    CandidateScoringEngine,
    ConfidenceLevel,
    FieldCandidate,
    HardConstraint,
    confidence_level_for_score,
    load_field_rule_registry,
)
from src.layout_analysis.page1.scoring_visual import demo_candidates, render_scoring_html


class Page1CandidateScoringTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_field_rule_registry()
        self.engine = CandidateScoringEngine(self.registry)

    @staticmethod
    def candidate(identifier, score=0.0, *, constraints=(), field="relay_version"):
        return FieldCandidate(
            candidate_id=identifier,
            canonical_field=field,
            value=identifier,
            component_scores={name: score for name in (
                "topology", "anchor", "alias", "separator", "value_validation", "ocr_confidence"
            )},
            hard_constraints=constraints,
        )

    def test_each_component_uses_its_configured_weight(self):
        for component, weight in self.registry.scoring.weights.items():
            with self.subTest(component=component):
                scored = self.engine.score_candidate(FieldCandidate(
                    candidate_id=component,
                    canonical_field="relay_version",
                    value="V1",
                    component_scores={component: 1.0},
                ))
                self.assertEqual(scored.breakdown[component].points, weight)
                self.assertEqual(scored.raw_score, weight)
                self.assertTrue(all(
                    item.points == 0 for name, item in scored.breakdown.items() if name != component
                ))

    def test_score_maps_to_all_five_confidence_levels(self):
        fixtures = {
            0: ConfidenceLevel.VERY_LOW,
            20: ConfidenceLevel.LOW,
            40: ConfidenceLevel.MEDIUM,
            60: ConfidenceLevel.HIGH,
            80: ConfidenceLevel.VERY_HIGH,
            100: ConfidenceLevel.VERY_HIGH,
        }
        for score, expected in fixtures.items():
            with self.subTest(score=score):
                self.assertEqual(confidence_level_for_score(score), expected)

    def test_separator_is_bonus_and_missing_separator_is_not_a_penalty(self):
        base = {"topology": 1.0, "anchor": 1.0, "alias": 1.0, "value_validation": 1.0, "ocr_confidence": 1.0}
        missing = self.engine.score_candidate(FieldCandidate(
            "missing", "relay_version", "V1", base,
        ))
        present = self.engine.score_candidate(FieldCandidate(
            "present", "relay_version", "V1", {**base, "separator": 1.0},
        ))

        self.assertEqual(missing.breakdown["separator"].points, 0)
        self.assertGreaterEqual(missing.raw_score, 0)
        self.assertEqual(present.raw_score - missing.raw_score, self.registry.scoring.weights["separator"])

    def test_hard_value_failure_caps_score_at_level_two_and_requires_review(self):
        constraint = HardConstraint.value_validation_failure("unit_suffix_mismatch")
        candidate = self.candidate("invalid", 1.0, constraints=(constraint,))

        scored = self.engine.score_candidate(candidate)
        decision = self.engine.decide([candidate])

        self.assertEqual(scored.raw_score, 100)
        self.assertLess(scored.score, 40)
        self.assertEqual(scored.confidence_level, ConfidenceLevel.LOW)
        self.assertEqual(scored.hard_cap_level, ConfidenceLevel.LOW)
        self.assertEqual(decision.status, "review_required")
        self.assertIn("leading_candidate_has_hard_constraints", decision.reasons)

    def test_exact_70_score_and_15_margin_auto_selects(self):
        decision = self.engine.decide([
            self.candidate("winner", 0.70),
            self.candidate("runner-up", 0.55),
        ])

        self.assertEqual(decision.status, "auto_selected")
        self.assertEqual(decision.selected_candidate_id, "winner")
        self.assertEqual(decision.winner_margin, 15)

    def test_below_threshold_or_margin_requires_review(self):
        below = self.engine.decide([self.candidate("winner", 0.69), self.candidate("other", 0.20)])
        narrow = self.engine.decide([self.candidate("winner", 0.80), self.candidate("other", 0.66)])

        self.assertEqual(below.status, "review_required")
        self.assertIn("below_auto_select_minimum", below.reasons)
        self.assertEqual(narrow.status, "review_required")
        self.assertIn("winner_margin_below_minimum", narrow.reasons)

    def test_overlay_thresholds_and_weights_change_decision_without_code_changes(self):
        candidate = FieldCandidate(
            "winner", "relay_version", "V1",
            {"topology": 1.0, "anchor": 1.0, "alias": 1.0, "separator": 1.0},
        )
        runner_up = self.candidate("runner-up", 0.20)
        self.assertEqual(self.engine.decide([candidate, runner_up]).status, "auto_selected")

        with TemporaryDirectory() as temporary:
            threshold_overlay = Path(temporary) / "threshold.json"
            threshold_overlay.write_text(json.dumps({
                "schema_version": "1.0",
                "scoring": {"auto_select_minimum": 81},
                "fields": {},
            }), encoding="utf-8")
            weight_overlay = Path(temporary) / "weights.json"
            weight_overlay.write_text(json.dumps({
                "schema_version": "1.0",
                "scoring": {"weights": {
                    "topology": 10, "anchor": 10, "alias": 10, "separator": 10,
                    "value_validation": 40, "ocr_confidence": 20,
                }},
                "fields": {},
            }), encoding="utf-8")
            threshold_decision = CandidateScoringEngine(
                load_field_rule_registry(overlay_path=threshold_overlay)
            ).decide([candidate, runner_up])
            weight_decision = CandidateScoringEngine(
                load_field_rule_registry(overlay_path=weight_overlay)
            ).decide([candidate, runner_up])

        self.assertEqual(threshold_decision.status, "review_required")
        self.assertIn("below_auto_select_minimum", threshold_decision.reasons)
        self.assertEqual(weight_decision.candidates[0].raw_score, 40)
        self.assertEqual(weight_decision.status, "review_required")

    def test_ties_are_deterministic_and_do_not_depend_on_input_order(self):
        alpha = self.candidate("alpha", 0.8)
        beta = self.candidate("beta", 0.8)

        first = self.engine.decide([beta, alpha])
        second = self.engine.decide([alpha, beta])

        self.assertEqual(first.leading_candidate_id, "alpha")
        self.assertEqual(second.leading_candidate_id, "alpha")
        self.assertEqual(first.status, "review_required")

    def test_visual_report_contains_decision_and_breakdown(self):
        decision = self.engine.decide(demo_candidates())
        with TemporaryDirectory() as temporary:
            output = render_scoring_html(decision, Path(temporary) / "review.html")
            html = output.read_text(encoding="utf-8")

        self.assertIn("Candidate scoring review", html)
        self.assertIn("auto_selected", html)
        self.assertIn("topology-and-anchor-winner", html)
        self.assertIn("topology", html)
        for label in ("very_low", "low", "medium", "high", "very_high"):
            with self.subTest(label=label):
                self.assertIn(label, html)

    def test_invalid_component_or_mixed_fields_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown scoring components"):
            FieldCandidate("bad", "relay_version", "V1", {"mystery": 1.0})
        with self.assertRaisesRegex(ValueError, "exactly one canonical field"):
            self.engine.decide([
                self.candidate("one", 0.8),
                self.candidate("two", 0.8, field="software_version"),
            ])


if __name__ == "__main__":
    unittest.main()
