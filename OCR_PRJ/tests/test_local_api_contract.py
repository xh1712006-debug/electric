"""Contract, boundary and visual tests for IMMEDIATE-001."""

from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from contextlib import redirect_stdout

from scripts.local_api_contract_review import (
    load_contract,
    main,
    render_contract_html,
    validate_contract,
    validate_example,
)
from src.layout_analysis.page1.schema import PAGE1_FIELD_NAMES


class LocalApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest, cls.examples = load_contract()
        cls.by_scenario = {item["scenario"]: item for item in cls.examples}

    def test_manifest_locks_confirmed_interface_and_single_pdf_scope(self):
        self.assertEqual(self.manifest["contract_id"], "ocr_prj.local_pdf.v1")
        self.assertEqual(self.manifest["schema_version"], "1.0")
        self.assertEqual(self.manifest["interface"]["primary"], "python")
        self.assertEqual(self.manifest["interface"]["cli_adapter"], "required")
        self.assertEqual(self.manifest["request"]["input_kind"], "single_pdf_x")
        self.assertTrue(self.manifest["policies"]["synchronous_terminal_result"])
        self.assertFalse(self.manifest["policies"]["pdf_a_supported"])

    def test_exactly_four_required_scenarios_exist_and_validate(self):
        self.assertEqual(
            set(self.by_scenario),
            {"success", "success_with_warnings", "review_required", "failure"},
        )
        self.assertEqual(validate_contract(self.manifest, self.examples), {
            item["example_id"]: [] for item in self.examples
        })

    def test_successful_examples_keep_all_25_canonical_page1_fields(self):
        for scenario in ("success", "success_with_warnings", "review_required"):
            with self.subTest(scenario=scenario):
                fields = self.by_scenario[scenario]["result"]["business"]["page1_fields"]
                self.assertEqual(tuple(fields), PAGE1_FIELD_NAMES)

    def test_utf8_examples_round_trip_without_losing_vietnamese_text(self):
        encoded = json.dumps(self.by_scenario["review_required"], ensure_ascii=False)
        restored = json.loads(encoded)
        self.assertIn("Trạm 220 kV Việt Trì", encoded)
        self.assertIn("Lưu ý", encoded)
        self.assertEqual(restored, self.by_scenario["review_required"])

    def test_request_rejects_missing_required_field(self):
        example = deepcopy(self.by_scenario["success"])
        del example["request"]["correlation_id"]
        errors = validate_example(example, self.manifest)
        self.assertTrue(any("request thiếu field" in error for error in errors))

    def test_request_rejects_multiple_inputs(self):
        example = deepcopy(self.by_scenario["success"])
        example["request"]["input_pdf"] = ["D:\\data\\P_001.pdf", "D:\\data\\P_002.pdf"]
        errors = validate_example(example, self.manifest)
        self.assertTrue(any("một absolute .pdf path" in error for error in errors))

    def test_request_rejects_folder_and_pdf_a_mode(self):
        folder = deepcopy(self.by_scenario["success"])
        folder["request"]["input_pdf"] = "D:\\management-data\\incoming"
        self.assertTrue(validate_example(folder, self.manifest))

        pdf_a = deepcopy(self.by_scenario["success"])
        pdf_a["request"]["input_mode"] = "pdf_a"
        errors = validate_example(pdf_a, self.manifest)
        self.assertTrue(any("field ngoài contract" in error for error in errors))

    def test_request_rejects_unsafe_correlation_id(self):
        example = deepcopy(self.by_scenario["success"])
        example["request"]["correlation_id"] = "../phiếu 001"
        errors = validate_example(example, self.manifest)
        self.assertTrue(any("correlation_id" in error for error in errors))

    def test_status_warning_and_error_invariants_are_enforced(self):
        success = deepcopy(self.by_scenario["success"])
        success["result"]["warnings"].append({"code": "X"})
        self.assertTrue(any("status=success" in error for error in validate_example(success, self.manifest)))

        warning = deepcopy(self.by_scenario["success_with_warnings"])
        warning["result"]["warnings"] = []
        self.assertTrue(any("ít nhất một warning" in error for error in validate_example(warning, self.manifest)))

        failure = deepcopy(self.by_scenario["failure"])
        failure["result"]["business"] = {}
        self.assertTrue(any("business=null" in error for error in validate_example(failure, self.manifest)))

    def test_public_result_rejects_debug_payload_and_absolute_internal_path(self):
        example = deepcopy(self.by_scenario["success"])
        example["result"]["pages"][0]["image_path"] = "C:\\temp\\page.png"
        errors = validate_example(example, self.manifest)
        self.assertTrue(any("forbidden key" in error for error in errors))
        self.assertTrue(any("absolute path" in error for error in errors))

    def test_public_result_rejects_stack_trace(self):
        example = deepcopy(self.by_scenario["failure"])
        example["result"]["error"]["stack_trace"] = "Traceback: internal.py:10"
        errors = validate_example(example, self.manifest)
        self.assertTrue(any("stack_trace" in error for error in errors))

    def test_artifact_manifest_rejects_escape_and_missing_reference(self):
        example = deepcopy(self.by_scenario["success"])
        example["result"]["artifact_manifest"]["artifacts"][0]["relative_path"] = "../escape.json"
        errors = validate_example(example, self.manifest)
        self.assertTrue(any("tương đối dưới output_root" in error for error in errors))

        windows_escape = deepcopy(self.by_scenario["success"])
        windows_escape["result"]["artifact_manifest"]["artifacts"][0]["relative_path"] = "run\\..\\escape.json"
        errors = validate_example(windows_escape, self.manifest)
        self.assertTrue(any("tương đối dưới output_root" in error for error in errors))

        missing = deepcopy(self.by_scenario["success"])
        missing["result"]["artifact_manifest"]["artifacts"] = []
        errors = validate_example(missing, self.manifest)
        self.assertTrue(any("artifact references không tồn tại" in error for error in errors))

    def test_page3_business_data_is_always_review_required(self):
        example = deepcopy(self.by_scenario["review_required"])
        example["result"]["business"]["setting_records"][0]["review_status"] = "not_required"
        errors = validate_example(example, self.manifest)
        self.assertTrue(any("setting_records[0]" in error for error in errors))

    def test_top_level_review_status_cannot_hide_review_candidates(self):
        example = deepcopy(self.by_scenario["review_required"])
        example["scenario"] = "success"
        example["result"]["review_status"] = "not_required"
        errors = validate_example(example, self.manifest)
        self.assertTrue(any("result.review_status" in error for error in errors))

    def test_visual_renderer_is_accented_vietnamese_and_shows_all_cases(self):
        html = render_contract_html(self.manifest, self.examples)
        self.assertIn('lang="vi"', html)
        self.assertIn("Rà soát contract local API v1", html)
        self.assertIn("Thành công có cảnh báo", html)
        self.assertIn("Cần người kiểm tra", html)
        self.assertIn("Thất bại có kiểm soát", html)
        self.assertIn("Tất cả hợp lệ", html)

    def test_visual_cli_writes_a_valid_utf8_report(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "contract_review.html"
            with redirect_stdout(io.StringIO()):
                exit_code = main(["--output", str(output)])
            self.assertEqual(exit_code, 0)
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("Ranh giới an toàn", rendered)
            self.assertIn("4/4", rendered)


if __name__ == "__main__":
    unittest.main()
