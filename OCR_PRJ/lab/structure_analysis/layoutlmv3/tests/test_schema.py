import unittest

from lab.structure_analysis.layoutlmv3.schema import LABELS, validate_bio_sequence


class SchemaTests(unittest.TestCase):
    def test_expected_generic_schema_has_13_labels(self) -> None:
        self.assertEqual(len(LABELS), 13)
        self.assertIn("B-PARAM_VALUE", LABELS)
        self.assertNotIn("PCS9611_FIELD_1", LABELS)

    def test_bio_validator_rejects_orphan_i(self) -> None:
        errors = validate_bio_sequence(["O", "I-PARAM_NAME"])
        self.assertEqual(len(errors), 1)

    def test_bio_validator_accepts_wrapped_entity(self) -> None:
        errors = validate_bio_sequence(
            ["B-PARAM_VALUE", "I-PARAM_VALUE", "I-PARAM_VALUE"]
        )
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
