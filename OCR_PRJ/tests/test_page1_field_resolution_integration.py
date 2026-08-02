from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.layout_analysis.page1 import (
    Page1FieldResolutionEngine,
    Page1LayoutAnalysisService,
    extract_page1,
    load_field_rule_registry,
)
from src.layout_analysis.page1.field_resolution_visual import (
    demo_field_resolution_payload,
    render_field_resolution_html,
)
from src.layout_analysis.page1.field_resolution_audit import compare_field_payloads
from src.layout_analysis.page1.schema import PAGE1_FIELD_NAMES


def block(identifier, text, x1, y1, x2, y2, confidence=0.95):
    return {
        "block_id": identifier,
        "text": text,
        "bbox_pixel": [x1, y1, x2, y2],
        "polygon": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
        "recognition_score": confidence,
    }


def empty_grid():
    return {"available": False, "image_width": 1200, "image_height": 1600, "regions": []}


def cover_grid():
    return {
        "available": True,
        "image_width": 1200,
        "image_height": 1600,
        "regions": [{
            "region_id": "table_01",
            "bbox": [0, 100, 1000, 800],
            "vertical_lines": [0, 500, 800, 1000],
            "column_centres": [250, 650, 900],
            "row_bands": [[100 + row * 100, 200 + row * 100] for row in range(7)],
        }],
    }


def page(*blocks):
    return {
        "document_id": "integration",
        "page_number": 1,
        "image_path": "page-1.png",
        "block_predictions": list(blocks),
    }


class Page1FieldResolutionIntegrationTests(unittest.TestCase):
    def test_confirmed_purpose_aliases_safely_fill_a_null_field(self):
        for label in ("Mục đích ban hành phiếu", "Nguyên nhân thay đổi chỉnh định"):
            with self.subTest(label=label):
                result = extract_page1(page(
                    block("purpose", f"{label}: Cải tạo trạm", 100, 500, 700, 535),
                ), empty_grid())

                field = result["fields"]["issuance_purpose"]
                evidence = result["field_resolution"]["issuance_purpose"]
                self.assertEqual(field["text"], "Cải tạo trạm")
                self.assertEqual(field["extraction_method"], "registry_alias_auto_select")
                self.assertEqual(evidence["status"], "auto_selected")
                self.assertTrue(evidence["applied_to_null_field"])
                self.assertEqual(evidence["matched_rule"]["value"], label)
                self.assertNotIn("missing_required_field:issuance_purpose", result["warnings"])
                self.assertNotIn("purpose", {item["block_id"] for item in result["unassigned_blocks"]})

    def test_confirmed_alias_and_value_in_separate_ocr_blocks_are_integrated(self):
        result = extract_page1(page(
            block("purpose-label", "Mục đích ban hành phiếu", 100, 500, 430, 535),
            block("purpose-value", "Nâng cấp trạm", 470, 500, 700, 535),
        ), empty_grid())

        field = result["fields"]["issuance_purpose"]
        evidence = result["field_resolution"]["issuance_purpose"]
        self.assertEqual(field["text"], "Nâng cấp trạm")
        self.assertEqual(field["source_block_ids"], ["purpose-label", "purpose-value"])
        self.assertEqual(evidence["status"], "auto_selected")
        self.assertFalse(evidence["matched_rule"]["separator_present"])

    def test_short_ticket_alias_is_evidence_without_changing_direct_header_value(self):
        result = extract_page1(page(
            block("ticket", "Số: A1-29-2026/E5.8/220", 700, 40, 1120, 70),
            block("page", "Trang: 1/5", 850, 90, 1000, 120),
            block("footer", "Xác nhận của người kiểm tra", 100, 1200, 450, 1230),
        ), empty_grid())

        evidence = result["field_resolution"]["ticket_number"]
        self.assertEqual(result["fields"]["ticket_number"]["text"], "A1-29-2026/E5.8/220")
        self.assertTrue(evidence["preserved_existing_value"])
        self.assertFalse(evidence["applied_to_null_field"])
        self.assertEqual(evidence["matched_rule"]["value"], "Số")
        self.assertEqual(evidence["matched_rule"]["origin"], "user")
        self.assertEqual(evidence["anchor"]["anchor_field"], "page_reference")
        self.assertIn("topology", evidence["score_breakdown"])
        self.assertIn("confidence", evidence)
        self.assertIn("winner_margin", evidence)

    def test_relay_specific_alias_uses_anchor_and_populates_version(self):
        result = extract_page1(page(
            block("relay", "Tên rơ-le: SEL311L", 500, 300, 750, 335),
            block("version", "Phiên bản rơ-le: V6.7.0.2", 800, 300, 1120, 335),
        ), empty_grid())

        evidence = result["field_resolution"]["relay_version"]
        self.assertEqual(result["fields"]["relay_version"]["text"], "V6.7.0.2")
        self.assertEqual(evidence["status"], "auto_selected")
        self.assertEqual(evidence["matched_rule"]["value"], "Phiên bản rơ-le")
        self.assertEqual(evidence["anchor"]["anchor_field"], "relay_name")
        self.assertEqual(evidence["anchor"]["relation"], "same_row_right")

    def test_invalid_required_value_is_hard_capped_and_never_applied(self):
        result = extract_page1(page(
            block("relay", "Tên rơ-le: SEL311L", 500, 300, 750, 335),
            block("version", "Phiên bản rơ-le: không rõ", 800, 300, 1120, 335),
        ), empty_grid())

        evidence = result["field_resolution"]["relay_version"]
        leader = evidence["decision"]["candidates"][0]
        self.assertIsNone(result["fields"]["relay_version"])
        self.assertEqual(evidence["status"], "review_required")
        self.assertFalse(evidence["applied_to_null_field"])
        self.assertLess(leader["score"], 40)
        self.assertEqual(leader["confidence"]["level"], 2)
        self.assertEqual(leader["hard_cap_level"], 2)

    def test_competing_alias_candidates_require_review_and_report_margin(self):
        result = extract_page1(page(
            block("first", "Mục đích ban hành phiếu: Cải tạo trạm", 100, 500, 650, 535),
            block("second", "Nguyên nhân thay đổi chỉnh định: Thử nghiệm", 100, 570, 700, 605),
        ), empty_grid())

        evidence = result["field_resolution"]["issuance_purpose"]
        self.assertIsNone(result["fields"]["issuance_purpose"])
        self.assertEqual(evidence["status"], "review_required")
        self.assertEqual(evidence["winner_margin"], 0)
        self.assertIn("winner_margin_below_minimum", evidence["decision"]["reasons"])

    def test_structure_owned_value_is_preserved_when_alias_candidate_disagrees(self):
        result = extract_page1(page(
            block("breaker_label", "Ngăn đóng cắt:", 10, 220, 170, 250),
            block("breaker_value", "273", 210, 220, 270, 250),
            block("other", "Máy cắt: 999", 1020, 900, 1170, 930),
        ), cover_grid())

        evidence = result["field_resolution"]["circuit_breaker"]
        self.assertEqual(result["fields"]["circuit_breaker"]["text"], "273")
        self.assertEqual(result["fields"]["circuit_breaker"]["extraction_method"], "table_structure")
        self.assertTrue(evidence["preserved_existing_value"])
        self.assertFalse(evidence["applied_to_null_field"])

    def test_structure_owned_null_is_not_filled_from_an_outside_alias(self):
        result = extract_page1(page(
            block("relay_label", "Thiết bị rơ-le:", 510, 220, 620, 250),
            block("relay_value", "SEL311L", 650, 220, 750, 250),
            block("version_label", "Bản phát hành:", 810, 220, 910, 250),
            block("outside", "Phiên bản rơ-le: V9.9", 800, 900, 1120, 935),
        ), cover_grid())

        evidence = result["field_resolution"]["relay_version"]
        self.assertIsNone(result["fields"]["relay_version"])
        self.assertEqual(evidence["resolution_method"], "table_structure_null_preserved")
        self.assertEqual(evidence["status"], "review_required")
        self.assertIn("structure_owned_null_not_overridden", evidence["decision"]["reasons"])

    def test_cover_alias_without_topology_or_anchor_cannot_claim_null_field(self):
        fields = {name: None for name in PAGE1_FIELD_NAMES}
        payload = {
            "page_number": 1,
            "fields": fields,
            "source_labels": {name: None for name in PAGE1_FIELD_NAMES},
            "layout_strategy": {"cover_fields": "label_fallback"},
            "warnings": [],
            "unassigned_blocks": [],
            "summary": {"unassigned_blocks": 0},
        }
        evidence = Page1FieldResolutionEngine(load_field_rule_registry()).integrate(
            payload,
            [
                block("drawing-label", "Số hiệu bản vẽ một sợi:", 100, 500, 430, 535),
                block("unrelated", "DIGSI", 1000, 500, 1110, 535),
            ],
            empty_grid(),
        )["single_line_drawing"]

        self.assertIsNone(payload["fields"]["single_line_drawing"])
        self.assertEqual(evidence["resolution_method"], "cover_ownership_unconfirmed")
        self.assertEqual(evidence["status"], "review_required")
        self.assertIn("cover_ownership_evidence_required", evidence["decision"]["reasons"])

    def test_field_schema_and_existing_payload_sections_are_backward_compatible(self):
        result = extract_page1(page(
            block("ticket", "Số phiếu: A1-29-2026/E5.8/220", 700, 40, 1120, 70),
            block("page", "Trang: 1/5", 850, 90, 1000, 120),
            block("station", "Trạm: E5.8", 100, 140, 300, 170),
        ), empty_grid())

        fields_before_serialization = deepcopy(result["fields"])
        encoded = json.dumps(result, ensure_ascii=False)
        decoded = json.loads(encoded)
        self.assertEqual(result["schema_version"], "1.1")
        self.assertEqual(tuple(result["fields"]), PAGE1_FIELD_NAMES)
        self.assertEqual(tuple(result["source_labels"]), PAGE1_FIELD_NAMES)
        self.assertEqual(tuple(result["field_resolution"]), PAGE1_FIELD_NAMES)
        self.assertEqual(decoded["fields"], fields_before_serialization)
        self.assertEqual(result["layout_strategy"]["cover_fields"], "label_fallback")
        self.assertEqual(result["skipped_sections"], ["protection_principle_table"])

    def test_service_accepts_overlay_without_breaking_existing_constructor(self):
        with TemporaryDirectory() as temporary:
            overlay = Path(temporary) / "field-rules.json"
            overlay.write_text(json.dumps({
                "schema_version": "1.0",
                "fields": {"issuance_purpose": {"aliases": [{
                    "value": "Lý do phát hành",
                    "origin": "user",
                    "status": "active",
                    "created_by": "integration-test",
                }]}},
            }, ensure_ascii=False), encoding="utf-8")
            service = Page1LayoutAnalysisService(field_rule_overlay_path=overlay)
            regions = [{
                "index": 0,
                "text": "Lý do phát hành: Kiểm tra định kỳ",
                "polygon": [[100, 500], [700, 500], [700, 535], [100, 535]],
                "recognition_score": 0.95,
            }]
            with patch("src.layout_analysis.page1.service.detect_table_grid", return_value=empty_grid()):
                result = service.analyse_page("page.png", regions, document_id="overlay").as_dict()

        self.assertEqual(result["fields"]["issuance_purpose"]["text"], "Kiểm tra định kỳ")
        self.assertEqual(
            result["field_resolution"]["issuance_purpose"]["matched_rule"]["value"],
            "Lý do phát hành",
        )

    def test_service_rejects_overlay_and_registry_at_the_same_time(self):
        with self.assertRaisesRegex(ValueError, "not both"):
            Page1LayoutAnalysisService(
                field_rule_overlay_path="overlay.json",
                field_rule_registry=load_field_rule_registry(),
            )

    def test_visual_report_is_accented_vietnamese_and_contains_resolution_evidence(self):
        payload = demo_field_resolution_payload()
        with TemporaryDirectory() as temporary:
            output = render_field_resolution_html(
                payload,
                Path(temporary) / "field_resolution_review.html",
            )
            html = output.read_text(encoding="utf-8")

        self.assertIn('lang="vi"', html)
        self.assertIn("Kiểm thử trực quan tích hợp phân giải trường Page 1", html)
        self.assertIn("Giá trị production", html)
        self.assertIn("Độ tin cậy", html)
        self.assertIn("Winner margin", html)
        self.assertIn("Hard-cap mức 2", html)
        self.assertIn("Cần xem xét", html)
        self.assertIn("Tự động chọn", html)

    def test_real_data_audit_comparison_allows_only_additive_null_fills(self):
        before = {
            "ticket_number": {"text": "A1"},
            "issuance_purpose": None,
            "relay_version": None,
        }
        compatible = compare_field_payloads(before, {
            "ticket_number": {"text": "A1"},
            "issuance_purpose": {"text": "Cải tạo trạm"},
            "relay_version": None,
        })
        incompatible = compare_field_payloads(before, {
            "ticket_number": {"text": "A2"},
            "issuance_purpose": None,
            "relay_version": None,
        })

        self.assertTrue(compatible["compatible"])
        self.assertEqual(compatible["supplemental_fields"], {"issuance_purpose": "Cải tạo trạm"})
        self.assertFalse(incompatible["compatible"])
        self.assertEqual(incompatible["changed_existing_fields"]["ticket_number"]["before"], "A1")


if __name__ == "__main__":
    unittest.main()
