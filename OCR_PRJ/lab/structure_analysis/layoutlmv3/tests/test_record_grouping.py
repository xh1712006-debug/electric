import unittest

from lab.structure_analysis.layoutlmv3.record_grouping import reconstruct_readable_page


def block(block_id: str, text: str, x1: float, y1: float, x2: float, y2: float) -> dict:
    return {
        "block_id": block_id,
        "text": text,
        "bbox_pixel": [x1, y1, x2, y2],
        "model_label": "B-QUESTION",
    }


class RecordGroupingTests(unittest.TestCase):
    def test_groups_code_name_and_value_by_relative_columns(self) -> None:
        page = {
            "document_id": "sample-page-003",
            "page_number": 3,
            "image_path": "sample.png",
            "block_predictions": [
                block("h1", "Group Alpha", 50, 20, 260, 45),
                block("c1", "003.085", 60, 70, 135, 95),
                block("n1", "Fct. assig. trigger", 180, 70, 460, 95),
                block("v1", "040.077 Starting IN>", 650, 70, 920, 95),
                block("c2", "003.086", 60, 110, 135, 135),
                block("n2", "Another parameter", 180, 110, 440, 135),
                block("v2", "Enabled", 650, 110, 760, 135),
            ],
        }
        result = reconstruct_readable_page(page)
        records = result["sections"][0]["records"]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["code"]["text"], "003.085")
        self.assertEqual(records[0]["name"]["text"], "Fct. assig. trigger")
        self.assertEqual(records[0]["values"][0]["text"], "040.077 Starting IN>")

    def test_keeps_wrapped_value_as_continuation(self) -> None:
        page = {
            "document_id": "sample-page-003",
            "page_number": 3,
            "image_path": "sample.png",
            "block_predictions": [
                block("c1", "0103", 60, 70, 110, 95),
                block("n1", "Protection Element", 180, 70, 450, 95),
                block("v1", "Direct I/P 1-1 On ((khóa", 650, 70, 940, 95),
                block("v2", "bảo vệ so lệch tại chỗ))", 650, 105, 940, 130),
            ],
        }
        result = reconstruct_readable_page(page)
        record = result["records_without_section"][0]
        self.assertEqual(len(record["values"]), 2)
        self.assertEqual(record["values"][1]["text"], "bảo vệ so lệch tại chỗ))")
        self.assertIn("dòng tiếp theo căn theo cột giá trị", record["grouping_evidence"])


if __name__ == "__main__":
    unittest.main()
