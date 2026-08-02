import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.layout_analysis.page1 import (
    AliasSeparatorResolver,
    CandidateScoringEngine,
    ConfidenceLevel,
    ConfigurableValueValidator,
    ValueRuleConfigurationError,
    load_field_rule_registry,
    split_label_value,
)
from src.layout_analysis.page1.value_resolution_visual import (
    demo_alias_cases,
    demo_validation_cases,
    render_value_resolution_html,
)


class Page1ValueResolutionTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_field_rule_registry()
        self.aliases = AliasSeparatorResolver(self.registry)
        self.validator = ConfigurableValueValidator(self.registry)

    def assert_rule(self, rule, value, expected, *, field="demo"):
        result = self.validator.validate_rules(field, value, [rule])
        self.assertEqual(result.status, expected)
        return result

    def test_all_required_validator_types(self):
        fixtures = (
            ({"type": "unit_suffix", "values": ["A"], "required": True}, "20 A", "passed"),
            ({"type": "endswith", "value": "kV", "required": True}, "220 kV", "passed"),
            ({"type": "startswith", "values": ["MC"], "required": True}, "MC 273", "passed"),
            ({"type": "regex", "pattern": r"MC-\d{3}", "required": True}, "MC-273", "passed"),
            ({"type": "enum", "values": ["Đóng", "Mở"], "required": True}, "ĐÓNG", "passed"),
            ({"type": "numeric", "required": True}, "10,5", "passed"),
            ({"type": "numeric_range", "minimum": 10.5, "maximum": 20, "required": True}, "20", "passed"),
            ({"type": "version", "required": True}, "V6.7.0.2", "passed"),
            ({"type": "ticket_number", "required": True}, "A1-29-2026/E5.8/220", "passed"),
        )
        for rule, value, expected in fixtures:
            with self.subTest(rule=rule["type"]):
                self.assert_rule(rule, value, expected)

    def test_existing_year_and_page_reference_rules_remain_supported(self):
        self.assertEqual(self.validator.validate("installation_year", "2026").status, "passed")
        self.assertEqual(self.validator.validate("page_reference", "1 / 5").status, "passed")
        self.assertEqual(self.validator.validate("page_reference", "7/5").status, "failed")

    def test_invalid_rule_configuration_is_rejected_early(self):
        invalid = (
            {"type": "unknown", "required": True},
            {"type": "regex", "pattern": "[", "required": True},
            {"type": "enum", "values": [], "required": True},
            {"type": "numeric_range", "minimum": 20, "maximum": 10},
            {"type": "unit_suffix", "value": "A", "values": ["A"]},
            {"type": "numeric", "unexpected": True},
        )
        for rule in invalid:
            with self.subTest(rule=rule):
                with self.assertRaises(ValueRuleConfigurationError):
                    self.validator.validate_rules("demo", "20", [rule])

    def test_regex_uses_fullmatch_not_partial_search(self):
        rule = {"type": "regex", "pattern": r"MC-\d{3}", "required": True}
        self.assert_rule(rule, "MC-273", "passed")
        result = self.assert_rule(rule, "Mã MC-273 lỗi", "failed")
        self.assertEqual(result.hard_constraints[0].max_confidence_level, ConfidenceLevel.LOW)

    def test_ampe_separator_normalization_and_wrong_unit_hard_cap(self):
        rule = {"type": "unit_suffix", "values": ["A"], "required": True}
        compact = split_label_value("Ampe: 20A")
        spaced = split_label_value("Ampe: 20 A")
        wrong = split_label_value("Ampe: 20V")

        compact_result = self.validator.validate_rules("current", compact.value_text, [rule])
        spaced_result = self.validator.validate_rules("current", spaced.value_text, [rule])
        wrong_result = self.validator.validate_rules("current", wrong.value_text, [rule])

        self.assertEqual(compact_result.normalized_value, "20A")
        self.assertEqual(spaced_result.normalized_value, "20A")
        self.assertEqual(wrong_result.status, "failed")
        self.assertEqual(wrong_result.hard_constraints[0].max_confidence_level, ConfidenceLevel.LOW)

    def test_short_so_alias_does_not_steal_longer_or_unrelated_labels(self):
        ticket = self.aliases.resolve_text("Số: A1-29-2026/E5.8/220")
        relay_serial = self.aliases.resolve_text("Số hiệu rơ-le: PCS-902-1")

        self.assertEqual({item.canonical_field for item in ticket}, {"ticket_number"})
        self.assertEqual({item.canonical_field for item in relay_serial}, {"relay_serial"})
        self.assertEqual(self.aliases.resolve_text("Số trang: 1/5"), ())
        self.assertEqual(self.aliases.resolve_text("Số lượng: 3"), ())

    def test_longest_specific_alias_wins_at_the_same_position(self):
        candidates = self.aliases.resolve_text("Phiên bản rơ-le: V6.7")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].canonical_field, "relay_version")
        self.assertEqual(candidates[0].alias, "Phiên bản rơ-le")

    def test_shared_alias_returns_every_canonical_field_independent_of_order(self):
        forward = self.aliases.resolve_text("Phiên bản: V3.4")
        reverse = tuple(reversed(forward))

        self.assertEqual(
            {item.canonical_field for item in forward},
            {"relay_version", "software_version"},
        )
        self.assertEqual(
            {item.canonical_field for item in reverse},
            {"relay_version", "software_version"},
        )

    def test_every_active_registry_alias_is_evaluated(self):
        for field_name, field in self.registry.fields.items():
            for alias in field.active_aliases:
                with self.subTest(field=field_name, alias=alias.value):
                    matches = self.aliases.resolve_text(f"{alias.value}: X1")
                    self.assertIn(field_name, {item.canonical_field for item in matches})

    def test_colon_bonus_missing_colon_and_split_ocr_blocks(self):
        with_colon = self.aliases.resolve_text("Mục đích ban hành phiếu: Nâng cấp trạm")
        split_blocks = self.aliases.resolve_blocks(["Mục đích ban hành", "phiếu", "Nâng cấp trạm"])
        full_width = self.aliases.resolve_text("Phiên bản rơ-le：V2.1")

        self.assertEqual(with_colon[0].separator_score, 1)
        self.assertEqual(split_blocks[0].separator_score, 0)
        self.assertEqual(split_blocks[0].value_text, "Nâng cấp trạm")
        self.assertEqual(split_blocks[0].source_block_indices, (0, 1, 2))
        self.assertEqual(full_width[0].separator, "：")

    def test_required_validator_failure_flows_into_scoring_hard_cap(self):
        candidate = self.aliases.resolve_text("Phiên bản rơ-le: không rõ")[0]
        validation = self.validator.validate(candidate.canonical_field, candidate.value_text)
        field_candidate = candidate.to_field_candidate(
            validation,
            component_scores={"topology": 1, "anchor": 1, "ocr_confidence": 1},
        )

        scored = CandidateScoringEngine(self.registry).score_candidate(field_candidate)

        self.assertEqual(validation.status, "failed")
        self.assertLess(scored.score, 40)
        self.assertEqual(scored.confidence_level, ConfidenceLevel.LOW)

    def test_disabled_overlay_alias_is_not_evaluated(self):
        with TemporaryDirectory() as temporary:
            overlay = Path(temporary) / "overlay.json"
            overlay.write_text(json.dumps({
                "schema_version": "1.0",
                "fields": {"ticket_number": {"aliases": [{
                    "value": "Mã phiếu", "origin": "user", "status": "disabled", "created_by": "test"
                }]}}
            }, ensure_ascii=False), encoding="utf-8")
            resolver = AliasSeparatorResolver(load_field_rule_registry(overlay_path=overlay))

        self.assertEqual(resolver.resolve_text("Mã phiếu: A1-29-2026/E5.8/220"), ())

    def test_visual_report_uses_accented_vietnamese_and_exposes_hard_caps(self):
        with TemporaryDirectory() as temporary:
            output = render_value_resolution_html(
                demo_alias_cases(), demo_validation_cases(), self.aliases, self.validator,
                Path(temporary) / "review.html",
            )
            html = output.read_text(encoding="utf-8")

        self.assertIn('lang="vi"', html)
        self.assertIn("Kiểm thử trực quan alias, dấu hai chấm", html)
        self.assertIn("Không tìm thấy alias hợp lệ", html)
        self.assertIn("Giá trị chuẩn hóa", html)
        self.assertIn("Hard-cap mức 2", html)
        self.assertIn("Không hợp lệ", html)


if __name__ == "__main__":
    unittest.main()
