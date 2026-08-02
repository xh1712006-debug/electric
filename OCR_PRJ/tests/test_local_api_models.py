import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pydantic import ValidationError

from src.layout_analysis.page1.schema import PAGE1_FIELD_NAMES
from src.relay_form_ocr import (
    Confidence,
    ExtractedField,
    OcrRequest,
    OcrResult,
    Page1Fields,
)
from src.relay_form_ocr.schema_export import export_json_schemas, schema_payloads
from src.relay_form_ocr.schema_visual import (
    render_schema_review_html,
    validate_contract_fixtures,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "contracts" / "local_api" / "v1" / "examples"
SCHEMAS = ROOT / "contracts" / "local_api" / "v1" / "schemas"


def fixture(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class LocalApiRequestModelTests(unittest.TestCase):
    def test_request_accepts_only_three_fields_and_uses_path_types(self):
        payload = fixture("success.json")["request"]
        request = OcrRequest.model_validate(payload)
        self.assertIsInstance(request.input_pdf, Path)
        self.assertIsInstance(request.output_root, Path)
        with self.assertRaises(ValidationError):
            OcrRequest.model_validate({**payload, "input_mode": "folder"})

    def test_request_rejects_relative_non_pdf_and_unsafe_correlation(self):
        valid = fixture("success.json")["request"]
        invalid_values = (
            {**valid, "input_pdf": "relative.pdf"},
            {**valid, "input_pdf": r"D:\management-data\P_001.png"},
            {**valid, "output_root": "relative-output"},
            {**valid, "correlation_id": "../ticket"},
            {**valid, "correlation_id": "x" * 129},
        )
        for payload in invalid_values:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                OcrRequest.model_validate(payload)


class LocalApiNestedModelTests(unittest.TestCase):
    def test_page1_model_has_exactly_25_canonical_fields(self):
        self.assertEqual(tuple(Page1Fields.model_fields), tuple(PAGE1_FIELD_NAMES))
        self.assertEqual(len(Page1Fields.model_fields), 25)

    def test_confidence_bounds_and_label_must_match(self):
        Confidence(level=3, label="medium", score=50)
        for payload in (
            {"level": 0, "label": "very_low", "score": 0},
            {"level": 6, "label": "very_high", "score": 100},
            {"level": 4, "label": "very_high", "score": 80},
            {"level": 2, "label": "low", "score": 101},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                Confidence.model_validate(payload)

    def test_not_available_field_requires_null_value_and_confidence(self):
        ExtractedField(
            value=None,
            confidence=None,
            resolution_status="not_available",
            source_page=1,
        )
        with self.assertRaises(ValidationError):
            ExtractedField(
                value="không được phép",
                confidence=None,
                resolution_status="not_available",
                source_page=1,
            )

    def test_nested_models_are_immutable_and_forbid_unknown_fields(self):
        confidence = Confidence(level=5, label="very_high", score=95)
        with self.assertRaises(ValidationError):
            confidence.score = 20
        with self.assertRaises(ValidationError):
            Confidence.model_validate({"level": 5, "label": "very_high", "score": 95, "raw": {}})


class LocalApiResultContractTests(unittest.TestCase):
    def test_all_four_v1_fixtures_validate(self):
        for path in sorted(EXAMPLES.glob("*.json")):
            with self.subTest(path=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                OcrRequest.model_validate(payload["request"])
                OcrResult.model_validate(payload["result"])

    def test_utf8_json_round_trip_preserves_vietnamese(self):
        result = OcrResult.model_validate(fixture("review_required.json")["result"])
        encoded = result.model_dump_json()
        self.assertIn("Trạm 220 kV Việt Trì", encoded)
        self.assertIn("Lưu ý", encoded)
        decoded = OcrResult.model_validate_json(encoded)
        self.assertEqual(decoded, result)
        self.assertEqual(decoded.model_dump(mode="json"), result.model_dump(mode="json"))

    def test_success_warning_and_failure_cross_field_rules(self):
        success = fixture("success.json")["result"]
        with self.assertRaises(ValidationError):
            OcrResult.model_validate({**success, "warnings": [{
                "code": "UNEXPECTED_WARNING",
                "message": "Có cảnh báo",
                "stage": "layout",
            }]})

        warning = fixture("success_with_warnings.json")["result"]
        with self.assertRaises(ValidationError):
            OcrResult.model_validate({**warning, "warnings": []})

        failure = fixture("failure.json")["result"]
        with self.assertRaises(ValidationError):
            OcrResult.model_validate({**failure, "business": success["business"]})
        with self.assertRaises(ValidationError):
            OcrResult.model_validate({**failure, "error": None})

    def test_page3_records_and_notes_cannot_bypass_review(self):
        payload = fixture("review_required.json")["result"]
        changed_record = copy.deepcopy(payload)
        changed_record["business"]["setting_records"][0]["review_status"] = "not_required"
        with self.assertRaises(ValidationError):
            OcrResult.model_validate(changed_record)

        changed_note = copy.deepcopy(payload)
        changed_note["business"]["note_candidates"][0]["review_status"] = "not_required"
        with self.assertRaises(ValidationError):
            OcrResult.model_validate(changed_note)

    def test_page_role_number_and_document_coverage_are_consistent(self):
        payload = fixture("review_required.json")["result"]
        wrong_role = copy.deepcopy(payload)
        wrong_role["pages"][2]["page_number"] = 2
        with self.assertRaises(ValidationError):
            OcrResult.model_validate(wrong_role)

        missing_page = copy.deepcopy(payload)
        missing_page["pages"] = missing_page["pages"][:-1]
        with self.assertRaises(ValidationError):
            OcrResult.model_validate(missing_page)

    def test_timing_requires_nonnegative_ordered_timezone_aware_values(self):
        payload = fixture("success.json")["result"]
        for timing in (
            {**payload["timing"], "elapsed_ms": -1},
            {**payload["timing"], "completed_at": "2026-07-30T07:59:59Z"},
            {**payload["timing"], "started_at": "2026-07-30T08:00:00"},
        ):
            with self.subTest(timing=timing), self.assertRaises(ValidationError):
                OcrResult.model_validate({**payload, "timing": timing})


class LocalApiPublicPayloadSecurityTests(unittest.TestCase):
    def test_artifact_paths_are_relative_portable_and_traversal_free(self):
        payload = fixture("success.json")["result"]
        for value in (
            "../outside.json",
            "/server/private.json",
            r"C:\server\private.json",
            r"workspace\pages\page.json",
        ):
            changed = copy.deepcopy(payload)
            changed["artifact_manifest"]["artifacts"][0]["relative_path"] = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                OcrResult.model_validate(changed)

    def test_all_artifact_references_must_exist(self):
        payload = copy.deepcopy(fixture("success.json")["result"])
        payload["business"]["evidence_artifact_ids"].append("missing-evidence")
        with self.assertRaises(ValidationError):
            OcrResult.model_validate(payload)

    def test_error_details_reject_debug_stack_and_absolute_paths(self):
        failure = fixture("failure.json")["result"]
        for details in (
            {"traceback": "ValueError: secret"},
            {"raw_ocr": ["nội dung nội bộ"]},
            {"diagnostic": r"C:\private\source.pdf"},
            {"diagnostic": "/srv/private/source.pdf"},
        ):
            changed = copy.deepcopy(failure)
            changed["error"]["details"] = details
            with self.subTest(details=details), self.assertRaises(ValidationError):
                OcrResult.model_validate(changed)

    def test_public_models_reject_unknown_raw_or_model_objects(self):
        payload = fixture("success.json")["result"]
        for key, value in (("raw_ocr", []), ("image_path", "page.png"), ("model_object", {})):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                OcrResult.model_validate({**payload, key: value})


class LocalApiJsonSchemaAndVisualTests(unittest.TestCase):
    def test_checked_in_json_schemas_match_models_deterministically(self):
        expected = schema_payloads()
        self.assertEqual(set(path.name for path in SCHEMAS.glob("*.json")), set(expected))
        for filename, payload in expected.items():
            actual = json.loads((SCHEMAS / filename).read_text(encoding="utf-8"))
            self.assertEqual(actual, payload)
            self.assertEqual(actual["$schema"], "https://json-schema.org/draft/2020-12/schema")

        with TemporaryDirectory() as temporary:
            first = export_json_schemas(Path(temporary) / "first")
            second = export_json_schemas(Path(temporary) / "second")
            self.assertEqual(
                [path.read_bytes() for path in first],
                [path.read_bytes() for path in second],
            )

    def test_every_object_schema_forbids_unknown_properties(self):
        for filename, schema in schema_payloads().items():
            objects = [schema, *schema.get("$defs", {}).values()]
            for item in objects:
                if item.get("type") == "object":
                    with self.subTest(filename=filename, title=item.get("title")):
                        self.assertFalse(item.get("additionalProperties", True))

    def test_visual_report_is_accented_vietnamese_and_all_fixtures_pass(self):
        reviews = validate_contract_fixtures(EXAMPLES)
        self.assertEqual(len(reviews), 4)
        self.assertTrue(all(item["valid"] for item in reviews))
        with TemporaryDirectory() as temporary:
            output = render_schema_review_html(reviews, Path(temporary) / "schema_review.html")
            html = output.read_text(encoding="utf-8")
        self.assertIn('<html lang="vi">', html)
        self.assertIn("Kiểm thử trực quan typed request/result/error schema", html)
        self.assertIn("Thành công có cảnh báo", html)
        self.assertIn("Cần người dùng xem xét", html)
        self.assertIn("Thất bại có kiểm soát", html)
        self.assertIn("Năm mức độ tin cậy", html)
        self.assertIn("Rất thấp", html)


if __name__ == "__main__":
    unittest.main()
