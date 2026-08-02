import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.layout_analysis.page1.rules import (
    DEFAULT_REGISTRY_PATH,
    FieldRuleRegistryError,
    load_field_rule_registry,
)
from src.layout_analysis.page1.schema import FIELD_SPECS


class Page1FieldRuleRegistryTests(unittest.TestCase):
    def _overlay(self, root: str, payload: dict) -> Path:
        path = Path(root) / "field_rules.user.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_default_registry_has_configurable_thresholds_and_confirmed_aliases(self):
        registry = load_field_rule_registry()

        self.assertEqual(registry.schema_version, "1.0")
        self.assertEqual(registry.scoring.auto_select_minimum, 70)
        self.assertEqual(registry.scoring.winner_margin_minimum, 15)
        self.assertEqual(sum(registry.scoring.weights.values()), 100)
        self.assertIn("Số", [rule.value for rule in registry.field("ticket_number").active_aliases])
        self.assertIn(
            "Nguyên nhân thay đổi chỉnh định",
            [rule.value for rule in registry.field("issuance_purpose").active_aliases],
        )
        self.assertIn("Phiên bản rơ-le", [rule.value for rule in registry.field("relay_version").active_aliases])

    def test_default_registry_preserves_every_existing_schema_alias(self):
        registry = load_field_rule_registry()

        for field_name, specification in FIELD_SPECS.items():
            with self.subTest(field=field_name):
                configured = {rule.value for rule in registry.field(field_name).aliases}
                self.assertTrue(set(specification["labels"]).issubset(configured))

    def test_user_overlay_appends_aliases_without_replacing_defaults(self):
        with TemporaryDirectory() as temporary:
            overlay = self._overlay(temporary, {
                "schema_version": "1.0",
                "fields": {
                    "ticket_number": {
                        "aliases": [
                            {"value": "Mã phiếu", "origin": "user", "status": "active", "created_by": "operator-a"},
                            {"value": "Số phiếu", "origin": "user", "status": "disabled", "created_by": "operator-b"}
                        ]
                    }
                }
            })
            registry = load_field_rule_registry(overlay_path=overlay)

        aliases = registry.field("ticket_number").aliases
        self.assertEqual([rule.value for rule in aliases[:3]], ["Số phiếu", "Số phiếu chỉnh định", "Số"])
        self.assertEqual(aliases[-2].value, "Mã phiếu")
        self.assertEqual(aliases[-2].created_by, "operator-a")
        self.assertEqual(aliases[-1].status, "disabled")
        self.assertIn("Số phiếu", [rule.value for rule in registry.field("ticket_number").active_aliases])

    def test_same_active_alias_is_preserved_for_multiple_canonical_fields(self):
        with TemporaryDirectory() as temporary:
            overlay = self._overlay(temporary, {
                "schema_version": "1.0",
                "fields": {
                    "relay_version": {
                        "aliases": [{"value": "Bản phát hành", "origin": "user", "created_by": "operator-a"}]
                    },
                    "software_version": {
                        "aliases": [{"value": "Bản phát hành", "origin": "user", "created_by": "operator-b"}]
                    }
                }
            })
            registry = load_field_rule_registry(overlay_path=overlay)

        self.assertEqual(
            registry.canonical_fields_for_alias("BẢN PHÁT HÀNH"),
            ("relay_version", "software_version"),
        )

    def test_user_value_rule_is_appended_with_provenance(self):
        with TemporaryDirectory() as temporary:
            overlay = self._overlay(temporary, {
                "schema_version": "1.0",
                "fields": {
                    "current_transformer_ratio": {
                        "value_rules": [{
                            "type": "unit_suffix",
                            "values": ["A", "Ampere"],
                            "required": True,
                            "origin": "user",
                            "created_by": "operator-a"
                        }]
                    }
                }
            })
            registry = load_field_rule_registry(overlay_path=overlay)

        rule = registry.field("current_transformer_ratio").value_rules[-1]
        self.assertEqual(rule["type"], "unit_suffix")
        self.assertEqual(rule["values"], ["A", "Ampere"])
        self.assertEqual(rule["created_by"], "operator-a")

    def test_overlay_can_tune_thresholds_without_changing_defaults_file(self):
        with TemporaryDirectory() as temporary:
            overlay = self._overlay(temporary, {
                "schema_version": "1.0",
                "scoring": {"auto_select_minimum": 74, "winner_margin_minimum": 18},
                "fields": {}
            })
            registry = load_field_rule_registry(overlay_path=overlay)

        self.assertEqual(registry.scoring.auto_select_minimum, 74)
        self.assertEqual(registry.scoring.winner_margin_minimum, 18)
        default_payload = json.loads(DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(default_payload["scoring"]["auto_select_minimum"], 70)

    def test_overlay_rejects_builtin_origin_unknown_field_and_replace_directive(self):
        invalid_payloads = [
            {
                "schema_version": "1.0",
                "fields": {"ticket_number": {"aliases": [{"value": "Mã", "origin": "built_in"}]}}
            },
            {
                "schema_version": "1.0",
                "fields": {"unknown_field": {"aliases": [{"value": "Mã", "origin": "user", "created_by": "x"}]}}
            },
            {
                "schema_version": "1.0",
                "fields": {"ticket_number": {"replace": []}}
            },
        ]
        with TemporaryDirectory() as temporary:
            for index, payload in enumerate(invalid_payloads):
                with self.subTest(index=index):
                    overlay = self._overlay(temporary, payload)
                    with self.assertRaises(FieldRuleRegistryError):
                        load_field_rule_registry(overlay_path=overlay)

    def test_invalid_scoring_and_malformed_json_are_rejected(self):
        with TemporaryDirectory() as temporary:
            invalid_score = self._overlay(temporary, {
                "schema_version": "1.0",
                "scoring": {"auto_select_minimum": 101},
                "fields": {}
            })
            with self.assertRaisesRegex(FieldRuleRegistryError, "between 0 and 100"):
                load_field_rule_registry(overlay_path=invalid_score)

            malformed = Path(temporary) / "malformed.json"
            malformed.write_text("{not-json", encoding="utf-8")
            with self.assertRaisesRegex(FieldRuleRegistryError, "Could not read field-rule overlay"):
                load_field_rule_registry(overlay_path=malformed)

    def test_overlay_rejects_wrong_schema_invalid_status_and_missing_provenance(self):
        invalid_payloads = [
            {
                "schema_version": "2.0",
                "fields": {}
            },
            {
                "schema_version": "1.0",
                "fields": {
                    "ticket_number": {
                        "aliases": [{"value": "Mã phiếu", "origin": "user", "status": "removed", "created_by": "x"}]
                    }
                }
            },
            {
                "schema_version": "1.0",
                "fields": {
                    "ticket_number": {
                        "aliases": [{"value": "Mã phiếu", "origin": "user"}]
                    }
                }
            },
        ]
        with TemporaryDirectory() as temporary:
            for index, payload in enumerate(invalid_payloads):
                with self.subTest(index=index):
                    overlay = self._overlay(temporary, payload)
                    with self.assertRaises(FieldRuleRegistryError):
                        load_field_rule_registry(overlay_path=overlay)


if __name__ == "__main__":
    unittest.main()
