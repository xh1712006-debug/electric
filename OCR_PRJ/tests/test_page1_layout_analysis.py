import unittest
from unittest.mock import patch

from src.layout_analysis.page1 import Page1LayoutAnalysisService, extract_page1


def block(identifier, text, x1, y1, x2, y2, confidence=0.9):
    return {"block_id": identifier, "text": text, "bbox_pixel": [x1, y1, x2, y2], "recognition_score": confidence}


def cover_grid():
    return {"available": True, "regions": [{
        "region_id": "table_01",
        "bbox": [0, 100, 1000, 800],
        "vertical_lines": [0, 500, 800, 1000],
        "column_centres": [250, 650, 900],
        "row_bands": [[100 + row * 100, 200 + row * 100] for row in range(7)],
    }]}


class Page1ExtractorTests(unittest.TestCase):
    def test_anchor_fields_and_page_reference(self):
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("a", "Số phiếu:", 700, 40, 800, 60), block("b", "A1-29-2026/E5.8/220", 900, 40, 1150, 60),
            block("c", "Trang:", 700, 70, 800, 90), block("d", "1 / 5", 900, 70, 960, 90),
            block("e", "Trạm: 220kV HOÀNH BỒ (E5.8)", 400, 120, 850, 150),
            block("f", "Mục đích ban hành phiếu chỉnh định:", 100, 500, 500, 525), block("g", "Cải tạo trạm", 550, 500, 800, 525),
            block("h", "Yêu cầu của Trung tâm Điều độ:", 100, 550, 500, 575), block("i", "Xem chi tiết các lưu ý", 550, 550, 900, 575),
        ]}
        result = extract_page1(page, {"regions": []})
        self.assertEqual(result["fields"]["ticket_number"]["text"], "A1-29-2026/E5.8/220")
        self.assertEqual(result["fields"]["page_number"]["text"], "1")
        self.assertEqual(result["fields"]["total_pages"]["text"], "5")
        self.assertEqual(result["fields"]["station"]["text"], "220kV HOÀNH BỒ (E5.8)")
        self.assertEqual(result["fields"]["issuance_purpose"]["text"], "Cải tạo trạm")

    def test_page_reference_label_is_dynamic_not_a_fixed_vocabulary(self):
        for label in ("Page", "Tờ", "Leaf marker"):
            with self.subTest(label=label):
                page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
                    block("ticket", "A1-29-2026/E5.8/220", 900, 40, 1150, 60),
                    block("page", f"{label}: 1/7", 880, 70, 1080, 95),
                    block("bottom", "Yêu cầu của Trung tâm Điều độ:", 100, 500, 500, 525),
                ]}
                result = extract_page1(page, {"regions": []})
                self.assertEqual(result["fields"]["page_reference"]["text"], "1/7")
                self.assertEqual(result["fields"]["page_reference"]["matched_label"], label)
                self.assertEqual(result["fields"]["total_pages"]["text"], "7")
                self.assertNotIn("missing_required_field:page_reference", result["warnings"])

    def test_dynamic_label_geometry_handles_page_number_without_total(self):
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("ticket", "A1-29-2026/E5.8/220", 900, 40, 1150, 60),
            block("unknown_label", "Document leaf:", 700, 70, 820, 95),
            block("page", "1", 900, 70, 940, 95),
            block("bottom", "Yêu cầu của Trung tâm Điều độ:", 100, 500, 500, 525),
        ]}
        result = extract_page1(page, {"regions": []})
        self.assertEqual(result["fields"]["page_reference"]["text"], "1")
        self.assertEqual(result["fields"]["page_reference"]["matched_label"], "Document leaf")
        self.assertIsNone(result["fields"]["total_pages"])
        self.assertIn("invalid_page_reference", result["warnings"])

    def test_missing_fields_are_null_and_required_fields_warn(self):
        result = extract_page1(
            {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": []},
            {"regions": []},
        )
        self.assertTrue(all(value is None for value in result["fields"].values()))
        self.assertIn("missing_required_field:ticket_number", result["warnings"])

    def test_protection_table_is_explicitly_skipped(self):
        region = {"region_id": "table_02", "bbox": [0, 100, 600, 400],
                  "vertical_lines": [0, 100, 200, 300, 400, 500, 600],
                  "column_centres": [50, 150, 250, 350, 450, 550],
                  "row_bands": [[100, 160], [160, 220], [220, 280], [280, 340]]}
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("a", "Chức năng", 10, 110, 90, 145), block("b", "Cấp bảo vệ", 110, 110, 190, 145), block("c", "Giá trị", 210, 110, 290, 145),
            block("d", "67/67 (N)", 10, 170, 90, 200), block("e", "I>>", 110, 170, 190, 200), block("f", "42.0 A", 210, 170, 290, 200),
            block("g", "0.3 s", 310, 170, 390, 200), block("h", "Cắt MC 175", 510, 170, 590, 200),
            block("i", "I>", 110, 230, 190, 260), block("j", "8.7 A", 210, 230, 290, 260), block("k", "3.0 s", 310, 230, 390, 260),
        ]}
        result = extract_page1(page, {"regions": [region]})
        self.assertEqual(result["protection_records"], [])
        self.assertIn("protection_principle_table", result["skipped_sections"])

    def test_embedded_version_labels_are_split_without_grid_dividers(self):
        region = {"region_id": "table_01", "bbox": [0, 100, 1000, 260],
                  "vertical_lines": [0, 500, 1000], "column_centres": [250, 750],
                  "row_bands": [[100, 180], [180, 260]]}
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("rn", "Tên rơ-le:", 520, 120, 640, 145),
            block("rv", "PCS-902 Phiên bản: V2.1", 650, 120, 940, 145),
            block("sn", "Phần mềm:", 520, 200, 640, 225),
            block("sv", "PCSExplorer Phiên bản: V3.4", 650, 200, 950, 225),
        ]}
        result = extract_page1(page, {"regions": [region]})
        self.assertEqual(result["fields"]["relay_name"]["text"], "PCS-902")
        self.assertEqual(result["fields"]["relay_version"]["text"], "V2.1")
        self.assertEqual(result["fields"]["software"]["text"], "PCSExplorer")
        self.assertEqual(result["fields"]["software_version"]["text"], "V3.4")
        self.assertLessEqual(
            max(box[2] for box in result["fields"]["relay_name"]["source_bboxes"]),
            min(box[0] for box in result["fields"]["relay_version"]["source_bboxes"]),
        )

    def test_split_alias_lines_and_equivalent_manufacturer_label(self):
        region = {"region_id": "table_01", "bbox": [0, 100, 1000, 300],
                  "vertical_lines": [0, 500, 1000], "column_centres": [250, 750],
                  "row_bands": [[100, 200], [200, 300]]}
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("ct1", "Tỷ số/ chỉ danh biến", 10, 115, 210, 140),
            block("ct2", "dòng điện:", 10, 140, 120, 165),
            block("ctv", "1500/5A (TI272)", 250, 120, 430, 150),
            block("maker", "Nhà sản xuất: AREVA", 520, 220, 820, 250),
        ]}
        result = extract_page1(page, {"regions": [region]})
        self.assertEqual(result["fields"]["current_transformer_ratio"]["text"], "1500/5A (TI272)")
        self.assertEqual(result["fields"]["manufacturer"]["text"], "AREVA")

    def test_wide_bad_page_ocr_does_not_consume_ticket_number(self):
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("tl", "Số phiếu:", 700, 40, 800, 60),
            block("tv", "A1-24-2026/E5.8/220", 900, 40, 1150, 60),
            block("pl", "Trang:", 700, 70, 800, 90),
            block("pv", "1", 900, 70, 930, 90),
            block("bad", "Trang: 777/02018", 820, 50, 1080, 110),
            block("bottom", "Yêu cầu của Trung tâm Điều độ:", 100, 500, 500, 525),
        ]}
        result = extract_page1(page, {"regions": []})
        self.assertEqual(result["fields"]["ticket_number"]["text"], "A1-24-2026/E5.8/220")
        self.assertEqual(result["fields"]["page_reference"]["text"], "1")
        self.assertEqual(result["fields"]["page_number"]["text"], "1")
        self.assertIsNone(result["fields"]["total_pages"])

    def test_short_inline_noise_does_not_hide_neighbouring_multiline_value(self):
        region = {"region_id": "table_01", "bbox": [0, 100, 1000, 220],
                  "vertical_lines": [0, 500, 1000], "column_centres": [250, 750],
                  "row_bands": [[100, 220]]}
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("label", "Kiểu bảo vệ: I", 520, 120, 680, 145),
            block("value1", "Bảo vệ khoảng cách 21/21N", 700, 120, 950, 145),
            block("value2", "(kèm 25/79, 67/67N, FR)", 700, 150, 950, 175),
        ]}
        result = extract_page1(page, {"regions": [region]})
        self.assertEqual(result["fields"]["protection_type"]["text"], "Bảo vệ khoảng cách 21/21N (kèm 25/79, 67/67N, FR)")

    def test_complete_inline_value_still_collects_lower_lines_in_same_cell(self):
        region = {"region_id": "table_01", "bbox": [0, 100, 1000, 220],
                  "vertical_lines": [0, 500, 1000], "column_centres": [250, 750],
                  "row_bands": [[100, 220]]}
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("line1", "Kiểu bảo vệ: Bảo vệ khoảng cách 21/21N", 520, 120, 950, 145),
            block("line2", "(kèm 25/79, 67/67N, FR)", 700, 150, 950, 175),
        ]}
        result = extract_page1(page, {"regions": [region]})
        self.assertEqual(result["fields"]["protection_type"]["text"], "Bảo vệ khoảng cách 21/21N (kèm 25/79, 67/67N, FR)")

    def test_borderless_multiline_protection_stops_at_next_logical_row(self):
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("mixed", "Đd 273 Việt Trì - 271 T500 Việt Trì Kiểu bảo vệ:", 490, 492, 1212, 538),
            block("value1", "Bảo vệ khoảng cách-21/21(N)", 1214, 489, 1565, 528),
            block("noise", "1", 1202, 506, 1215, 519, confidence=0.1),
            block("value2", "(kèm 51N, 85, FR)", 1220, 528, 1442, 562),
            block("next_label", "Tên rơ-le:", 1044, 584, 1173, 618),
            block("next_value", "7SA522", 1220, 582, 1323, 618),
        ]}
        result = extract_page1(page, {"available": False, "regions": []})
        self.assertEqual(
            result["fields"]["protection_type"]["text"],
            "Bảo vệ khoảng cách-21/21(N) (kèm 51N, 85, FR)",
        )
        self.assertNotIn("7SA522", result["fields"]["protection_type"]["text"])

    def test_borderless_generic_field_collects_two_lines_but_not_next_row(self):
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("label", "Thiết bị được bảo vệ:", 100, 100, 290, 130),
            block("line1", "Đường dây 273 - 271", 320, 100, 620, 128),
            block("line2", "(AC520 - 18.9 km)", 320, 132, 560, 160),
            block("next_label", "Máy cắt:", 100, 175, 220, 205),
            block("next_value", "200", 320, 175, 380, 205),
        ]}
        result = extract_page1(page, {"available": False, "regions": []})
        self.assertEqual(
            result["fields"]["protected_equipment"]["text"],
            "Đường dây 273 - 271 (AC520 - 18.9 km)",
        )
        self.assertNotIn("200", result["fields"]["protected_equipment"]["text"])

    def test_field_name_inside_value_does_not_steal_cell_ownership(self):
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("equipment_label", "Thiết bị được bảo vệ:", 100, 100, 290, 130),
            block("equipment_value", "Máy cắt liên lạc 220kV", 320, 100, 650, 130),
            block("breaker_label", "Máy cắt:", 100, 175, 220, 205),
            block("breaker_value", "273", 320, 175, 380, 205),
        ]}

        result = extract_page1(page, {"available": False, "regions": []})

        self.assertEqual(result["fields"]["protected_equipment"]["text"], "Máy cắt liên lạc 220kV")
        self.assertEqual(result["fields"]["circuit_breaker"]["text"], "273")

    def test_company_table_topology_owns_fields_when_labels_are_unseen(self):
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("equipment_label", "Đối tượng đang được bảo hộ:", 10, 120, 170, 150),
            block("equipment_value", "Máy cắt liên lạc 220kV", 210, 120, 450, 150),
            block("protection_label", "Phương thức bảo vệ:", 510, 120, 650, 150),
            block("protection_value", "So lệch thanh cái", 700, 120, 950, 150),
            block("breaker_label", "Ngăn đóng cắt:", 10, 220, 170, 250),
            block("breaker_value", "273", 210, 220, 270, 250),
            block("relay_label", "Thiết bị rơ-le:", 510, 220, 620, 250),
            block("relay_value", "SEL311L", 650, 220, 750, 250),
            block("version_label", "Bản phát hành:", 810, 220, 910, 250),
        ]}

        result = extract_page1(page, cover_grid())

        self.assertEqual(result["layout_strategy"]["cover_fields"], "table_structure")
        self.assertEqual(result["fields"]["protected_equipment"]["text"], "Máy cắt liên lạc 220kV")
        self.assertEqual(result["fields"]["protection_type"]["text"], "So lệch thanh cái")
        self.assertEqual(result["fields"]["circuit_breaker"]["text"], "273")
        self.assertEqual(result["fields"]["relay_name"]["text"], "SEL311L")
        self.assertIsNone(result["fields"]["relay_version"])
        self.assertEqual(result["source_labels"]["protected_equipment"]["text"], "Đối tượng đang được bảo hộ")
        self.assertEqual(result["source_labels"]["circuit_breaker"]["text"], "Ngăn đóng cắt")
        self.assertEqual(result["source_labels"]["relay_version"]["text"], "Bản phát hành")

    def test_wide_left_half_keeps_near_boundary_number_as_value(self):
        grid = {"available": True, "regions": [{
            "region_id": "table_01",
            "bbox": [156, 100, 1494, 800],
            "vertical_lines": [156, 984, 1257, 1494],
            "column_centres": [570, 1120, 1375],
            "row_bands": [[100 + row * 100, 200 + row * 100] for row in range(7)],
        }]}
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("breaker_label", "Máy cắt:", 160, 220, 265, 250),
            block("breaker_value", "175", 423, 220, 477, 250),
        ]}

        result = extract_page1(page, grid)

        self.assertEqual(result["source_labels"]["circuit_breaker"]["text"], "Máy cắt")
        self.assertEqual(result["fields"]["circuit_breaker"]["text"], "175")

    def test_borderless_inline_value_collects_continuation(self):
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("line1", "Kiểu bảo vệ: Bảo vệ khoảng cách 21/21N", 520, 120, 950, 145),
            block("line2", "(kèm 25/79, 67/67N, FR)", 700, 150, 950, 175),
            block("next_label", "Tên rơ-le:", 520, 195, 640, 225),
            block("next_value", "PCS-902", 700, 195, 820, 225),
        ]}
        result = extract_page1(page, {"available": False, "regions": []})
        self.assertEqual(
            result["fields"]["protection_type"]["text"],
            "Bảo vệ khoảng cách 21/21N (kèm 25/79, 67/67N, FR)",
        )

    def test_borderless_ruling_line_stops_unlabelled_next_row(self):
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("label", "Thiết bị được bảo vệ:", 100, 100, 290, 130),
            block("line1", "Đường dây 273 - 271", 320, 100, 620, 128),
            block("line2", "(AC520 - 18.9 km)", 320, 132, 560, 155),
            block("unlabelled_row", "Ngưỡng chỉnh định Tín hiệu Tác động", 350, 165, 780, 190),
            block("next_label", "Máy cắt:", 100, 230, 220, 260),
        ]}
        grid = {"available": False, "regions": [], "page_horizontal_lines": [160, 200, 265]}
        result = extract_page1(page, grid)
        self.assertEqual(
            result["fields"]["protected_equipment"]["text"],
            "Đường dây 273 - 271 (AC520 - 18.9 km)",
        )
        self.assertNotIn("Ngưỡng", result["fields"]["protected_equipment"]["text"])

    def test_empty_overlapping_version_never_reuses_relay_or_software_value(self):
        region = {"region_id": "table_01", "bbox": [0, 100, 1000, 300],
                  "vertical_lines": [0, 500, 1000], "column_centres": [250, 750],
                  "row_bands": [[100, 190], [190, 280]]}
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("relay_label", "Tên rơ-le:", 510, 120, 630, 145),
            block("relay_value", "PCS-902", 640, 120, 830, 145),
            block("relay_version", "Phiên bản:", 790, 118, 930, 147),
            block("software_label", "Phần mềm:", 510, 210, 630, 235),
            block("software_value", "PCSExplorer", 640, 210, 850, 235),
            block("software_version", "Phiên bản:", 810, 208, 940, 237),
        ]}
        result = extract_page1(page, {"regions": [region]})
        self.assertEqual(result["fields"]["relay_name"]["text"], "PCS-902")
        self.assertIsNone(result["fields"]["relay_version"])
        self.assertEqual(result["fields"]["software"]["text"], "PCSExplorer")
        self.assertIsNone(result["fields"]["software_version"])

    def test_version_with_own_value_does_not_reuse_left_value(self):
        region = {"region_id": "table_01", "bbox": [0, 100, 1000, 190],
                  "vertical_lines": [0, 500, 1000], "column_centres": [250, 750],
                  "row_bands": [[100, 190]]}
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("relay_label", "Tên rơ-le:", 510, 120, 630, 145),
            block("relay_value", "PCS-902", 640, 120, 800, 145),
            block("version_label", "Phiên bản:", 790, 118, 890, 147),
            block("version_value", "V2.1", 910, 120, 970, 145),
        ]}
        result = extract_page1(page, {"regions": [region]})
        self.assertEqual(result["fields"]["relay_name"]["text"], "PCS-902")
        self.assertEqual(result["fields"]["relay_version"]["text"], "V2.1")

    def test_serial_value_stops_before_embedded_version_label(self):
        region = {"region_id": "table_01", "bbox": [0, 100, 1000, 190],
                  "vertical_lines": [0, 500, 1000], "column_centres": [250, 750],
                  "row_bands": [[100, 190]]}
        page = {"document_id": "sample", "page_number": 1, "image_path": "sample.png", "block_predictions": [
            block("serial", "Số hiệu rơ-le: PCS-902-1-EN-5A Phiên bản", 510, 120, 970, 145),
        ]}
        result = extract_page1(page, {"regions": [region]})
        self.assertEqual(result["fields"]["relay_serial"]["text"], "PCS-902-1-EN-5A")

    @patch("src.layout_analysis.page1.service.detect_table_grid", return_value={"available": False, "regions": []})
    def test_production_service_accepts_recognition_regions(self, _grid):
        result = Page1LayoutAnalysisService().analyse_page(
            "sample.png",
            [
                {"index": 0, "polygon": [[700, 10], [800, 10], [800, 30], [700, 30]], "text": "Số phiếu:"},
                {"index": 1, "polygon": [[900, 10], [1150, 10], [1150, 30], [900, 30]], "text": "A1-01-2026/E5.8/220"},
                {"index": 2, "polygon": [[700, 40], [800, 40], [800, 60], [700, 60]], "text": "Trang:"},
                {"index": 3, "polygon": [[900, 40], [960, 40], [960, 60], [900, 60]], "text": "1/5"},
            ],
            document_id="sample-page-001",
        ).as_dict()
        self.assertEqual(result["page_role"], "cover")
        self.assertEqual(result["fields"]["ticket_number"]["text"], "A1-01-2026/E5.8/220")
        self.assertEqual(result["fields"]["page_reference"]["text"], "1/5")


if __name__ == "__main__":
    unittest.main()
