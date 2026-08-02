import unittest
from unittest.mock import patch

from src.layout_analysis import DocumentLayoutAnalysisService


class LayoutAnalysisServiceTests(unittest.TestCase):
    @patch("src.layout_analysis.page3_plus.service.detect_table_grid", return_value={"available": False, "regions": []})
    def test_recognised_polygons_become_candidate_records(self, _grid):
        result = DocumentLayoutAnalysisService().analyse_page("sample.png", [
            {"index": 0, "polygon": [[10, 10], [40, 10], [40, 25], [10, 25]], "text": "0103"},
            {"index": 1, "polygon": [[100, 10], [250, 10], [250, 25], [100, 25]], "text": "Parameter"},
            {"index": 2, "polygon": [[400, 10], [500, 10], [500, 25], [400, 25]], "text": "Enabled"},
            {"index": 3, "polygon": [[10, 40], [40, 40], [40, 55], [10, 55]], "text": "0104"},
            {"index": 4, "polygon": [[100, 40], [250, 40], [250, 55], [100, 55]], "text": "Parameter two"},
            {"index": 5, "polygon": [[400, 40], [500, 40], [500, 55], [400, 55]], "text": "Disabled"},
        ], document_id="sample-page-003", page_number=3)
        payload = result.as_dict()
        self.assertEqual(payload["document_id"], "sample-page-003")
        self.assertEqual(payload["records"][0]["parameter_code"]["text"], "0103")
        self.assertEqual(payload["records"][0]["value"]["text"], "Enabled")

    @patch("src.layout_analysis.page3_plus.service.detect_table_grid", return_value={"available": False, "regions": []})
    def test_page3_header_uses_dynamic_pagination_label(self, _grid):
        result = DocumentLayoutAnalysisService().analyse_page("sample.png", [
            {"index": 0, "polygon": [[300, 10], [390, 10], [390, 30], [300, 30]], "text": "Leaf index:"},
            {"index": 1, "polygon": [[410, 10], [470, 10], [470, 30], [410, 30]], "text": "3/9"},
            {"index": 2, "polygon": [[10, 100], [50, 100], [50, 120], [10, 120]], "text": "0103"},
            {"index": 3, "polygon": [[100, 100], [250, 100], [250, 120], [100, 120]], "text": "Parameter"},
            {"index": 4, "polygon": [[400, 100], [500, 100], [500, 120], [400, 120]], "text": "Enabled"},
        ], document_id="sample-page-003", page_number=3)
        payload = result.as_dict()
        self.assertEqual(payload["layout"]["page_reference"]["text"], "3/9")
        self.assertEqual(payload["layout"]["page_reference"]["matched_label"], "Leaf index")
        metadata_text = " ".join(" ".join(row["cells"]) for row in payload["rows"] if row["row_type"] == "document_metadata")
        self.assertIn("3/9", metadata_text)
