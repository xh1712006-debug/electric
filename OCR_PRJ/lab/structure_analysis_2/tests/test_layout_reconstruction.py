import unittest

from lab.structure_analysis_2.cell_ocr import cells_requiring_reocr
from lab.structure_analysis_2.layout_reconstruction import reconstruct_page


def block(identifier, text, x, y):
    return {"block_id": identifier, "text": text, "bbox_pixel": [x, y, x + 70, y + 18]}


def sized_block(identifier, text, x1, y1, x2, y2):
    return {"block_id": identifier, "text": text, "bbox_pixel": [x1, y1, x2, y2]}


def four_column_grid(row_bands=None):
    row_bands = row_bands or [[90, 120], [120, 160]]
    return {"available": True, "regions": [{
        "region_id": "table_01", "bbox": [80, 90, 900, row_bands[-1][1]],
        "vertical_lines": [80, 180, 350, 650, 900],
        "horizontal_lines": [band[0] for band in row_bands] + [row_bands[-1][1]],
        "column_centres": [130, 265, 500, 775], "row_bands": row_bands,
    }]}


class LayoutReconstructionTests(unittest.TestCase):
    def test_three_column_hex_code_table(self):
        page = {"document_id": "sample", "page_number": 3, "image_path": "sample.png", "block_predictions": [
            block("a", "Code", 100, 100), block("b", "Parameter", 300, 100), block("c", "Value", 700, 100),
            block("d", "09.0A", 100, 140), block("e", "Setting Group 4", 300, 140), block("f", "Disabled", 700, 140),
        ]}
        result = reconstruct_page(page)
        record = result["records"][-1]
        self.assertEqual(record["parameter_code"]["text"], "09.0A")
        self.assertEqual(record["parameter_name"]["text"], "Setting Group 4")
        self.assertEqual(record["value"]["text"], "Disabled")

    def test_plain_numeric_codes_are_not_continuation_lines(self):
        page = {"document_id": "sample", "page_number": 3, "image_path": "sample.png", "block_predictions": [
            block("a", "0103", 100, 100), block("b", "Parameter one", 300, 100), block("c", "Enabled", 700, 100),
            block("d", "0104", 100, 140), block("e", "Parameter two", 300, 140), block("f", "Disabled", 700, 140),
        ]}
        result = reconstruct_page(page)
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["records"][1]["parameter_code"]["text"], "0104")

    def test_four_column_description_table(self):
        page = {"document_id": "sample", "page_number": 3, "image_path": "sample.png", "block_predictions": [
            block("a", "Index", 100, 100), block("b", "Item", 200, 100), block("c", "Description", 400, 100), block("d", "Setting", 800, 100),
            block("e", "2", 100, 140), block("f", "21D", 200, 140), block("g", "Distance protection", 400, 140), block("h", "Enable", 800, 140),
        ]}
        result = reconstruct_page(page)
        record = result["records"][-1]
        self.assertEqual(record["record_key"]["text"], "2")
        self.assertEqual(record["parameter_name"]["text"], "21D")
        self.assertEqual(record["description"]["text"], "Distance protection")
        self.assertEqual(record["value"]["text"], "Enable")

    def test_group_attributes_header_maps_value_unit_and_description(self):
        page = {"document_id": "sample", "page_number": 3, "image_path": "sample.png", "block_predictions": [
            block("a", "Group/Attributes", 100, 100), block("b", "Value Set", 200, 100), block("c", "Unit", 400, 100), block("d", "Description", 800, 100),
            block("e", "AI1_Ch1_Ratio", 100, 140), block("f", "1100", 200, 140), block("g", "-", 400, 140), block("h", "For AC analog input ch#1", 800, 140),
        ]}
        result = reconstruct_page(page, four_column_grid())
        self.assertEqual(result["layout"]["table_regions"][0]["column_roles"], ["parameter_name", "value", "unit", "description"])
        self.assertEqual(result["rows"][0]["row_type"], "table_header")
        self.assertEqual(len(result["records"]), 1)
        record = result["records"][0]
        self.assertEqual(record["parameter_name"]["text"], "AI1_Ch1_Ratio")
        self.assertEqual(record["value"]["text"], "1100")
        self.assertEqual(record["unit"]["text"], "-")
        self.assertEqual(record["description"]["text"], "For AC analog input ch#1")

    def test_grid_header_uses_cell_boundaries_not_header_text_start(self):
        grid = {"available": True, "regions": [{
            "region_id": "table_01", "bbox": [150, 90, 1465, 160],
            "vertical_lines": [156, 510, 691, 783, 1462],
            "horizontal_lines": [90, 120, 160],
            "column_centres": [333, 600.5, 737, 1122.5], "row_bands": [[90, 120], [120, 160]],
        }]}
        page = {"document_id": "sample", "page_number": 3, "image_path": "sample.png", "block_predictions": [
            block("a", "Group/Attributes", 160, 100), block("b", "Value Set", 514, 100), block("c", "Unit", 694, 100), block("d", "Description", 788, 100),
            block("e", "AI1_Ch1_Ratio", 160, 140), block("f", "1100", 514, 140), block("g", "-", 694, 140), block("h", "For AC analog input ch#1", 788, 140),
        ]}
        result = reconstruct_page(page, grid)
        self.assertEqual(result["layout"]["table_regions"][0]["column_roles"], ["parameter_name", "value", "unit", "description"])
        self.assertEqual(result["rows"][0]["row_type"], "table_header")

    def test_merged_index_item_header_keeps_four_column_default(self):
        page = {"document_id": "sample", "page_number": 3, "image_path": "sample.png", "block_predictions": [
            block("a", "Index Item", 100, 100), block("b", "Description", 400, 100), block("c", "Setting", 800, 100),
            block("d", "2", 100, 140), block("e", "21D", 220, 140), block("f", "Distance protection", 400, 140), block("g", "Enable", 800, 140),
        ]}
        grid = four_column_grid()
        result = reconstruct_page(page, grid)
        self.assertEqual(result["layout"]["table_regions"][0]["column_roles"], ["record_key", "parameter_name", "description", "value"])

    def test_headerless_four_physical_columns_can_be_one_value_field(self):
        page = {"document_id": "sample", "page_number": 3, "image_path": "sample.png", "block_predictions": [
            block("a", "0103", 100, 100), block("b", "Parameter one", 300, 100), block("c", "Disabled", 500, 100),
            block("d", "0104", 100, 130), block("e", "Parameter two", 300, 130), block("f", "Definite Time only", 800, 130),
            block("g", "0105", 100, 160), block("h", "Parameter three", 300, 160), block("i", "Enabled", 500, 160),
            block("j", "0106", 100, 190), block("k", "Parameter four", 300, 190), block("l", "50 Hz", 800, 190),
        ]}
        result = reconstruct_page(page)
        self.assertEqual(result["layout"]["column_roles"], ["record_key", "parameter_name", "value", "value"])
        self.assertEqual([record["value"]["text"] for record in result["records"]], ["Disabled", "Definite Time only", "Enabled", "50 Hz"])
        self.assertTrue(all("description" not in record for record in result["records"]))

    def test_grid_rows_win_over_overlapping_tall_ocr_boxes(self):
        page = {"document_id": "sample", "page_number": 3, "image_path": "sample.png", "block_predictions": [
            sized_block("a", "12", 100, 125, 160, 158),
            sized_block("b", "50/51P1", 210, 123, 330, 146),
            sized_block("c", "Enable stage 1", 380, 123, 620, 146),
            sized_block("d", "Enable", 700, 123, 820, 146),
            sized_block("e", "13", 100, 145, 160, 180),
            sized_block("f", "50/51P2", 210, 163, 330, 184),
            sized_block("g", "Enable stage 2", 380, 163, 620, 184),
            sized_block("h", "Disable", 700, 163, 820, 184),
        ]}
        grid = four_column_grid([[120, 160], [160, 200]])
        result = reconstruct_page(page, grid)
        records = [record for record in result["records"] if record.get("record_key")]
        self.assertEqual([record["record_key"]["text"] for record in records], ["12", "13"])

    def test_cell_reocr_is_planned_for_crossing_block_but_not_spanning_heading(self):
        page = {"document_id": "sample", "page_number": 3, "image_path": "sample.png", "block_predictions": [
            sized_block("heading", "GROUP TITLE", 90, 92, 890, 115),
            sized_block("key", "1", 100, 125, 150, 150),
            sized_block("merged", "Code Description", 100, 125, 500, 150),
            sized_block("value", "On", 700, 125, 800, 150),
        ]}
        plans = cells_requiring_reocr(page, four_column_grid())
        planned_keys = {plan["key"] for plan in plans}
        self.assertNotIn("table_01:0:0", planned_keys)
        self.assertIn("table_01:1:0", planned_keys)
        self.assertIn("table_01:1:1", planned_keys)
        self.assertIn("table_01:1:2", planned_keys)

    def test_complete_multicolumn_row_is_not_continuation_without_key(self):
        page = {"document_id": "sample", "page_number": 3, "image_path": "sample.png", "block_predictions": [
            block("a", "0103", 100, 100), block("b", "Parameter one", 300, 100), block("c", "Enabled", 700, 100),
            block("d", "Parameter two", 300, 130), block("e", "Disabled", 700, 130),
        ]}
        result = reconstruct_page(page)
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["records"][1]["parameter_name"]["text"], "Parameter two")

    def test_incomplete_row_without_key_is_continuation(self):
        page = {"document_id": "sample", "page_number": 3, "image_path": "sample.png", "block_predictions": [
            block("a", "0103", 100, 100), block("b", "Long parameter", 300, 100), block("c", "Enabled", 700, 100),
            block("d", "0104", 100, 130), block("e", "Second parameter", 300, 130), block("f", "Disabled", 700, 130),
            block("g", "continued description", 300, 160),
        ]}
        result = reconstruct_page(page)
        self.assertEqual(len(result["records"]), 2)
        self.assertIn("continued description", result["records"][1]["parameter_name"]["text"])


if __name__ == "__main__":
    unittest.main()
