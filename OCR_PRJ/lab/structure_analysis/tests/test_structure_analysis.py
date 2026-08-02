"""Synthetic tests for generic geometry and logical grouping heuristics."""

from pathlib import Path
import sys
import unittest

LAB_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB_ROOT))

from heuristics import infer_semantic_roles, reconstruct_records  # noqa: E402
from layout_graph import assign_reading_rows, build_graph, normalize_blocks  # noqa: E402
from ocr_input import infer_page_number  # noqa: E402


class StructureAnalysisTests(unittest.TestCase):
    def make_blocks(self):
        rows = [
            ("003.085", 10, 10, 70, 30),
            ("Fct. assig. trigger", 90, 10, 250, 30),
            ("040.077 Starting IN>", 300, 10, 480, 30),
            ("040.041 Starting IN>>", 300, 38, 490, 58),
            ("039.078 Starting IN>>>", 300, 66, 500, 86),
        ]
        return [
            {
                "id": f"b{index:04d}",
                "text": text,
                "polygon": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
                "recognition_confidence": 0.9,
            }
            for index, (text, x1, y1, x2, y2) in enumerate(rows)
        ]

    def test_reconstructs_multi_value_record(self) -> None:
        blocks = normalize_blocks(self.make_blocks(), 600, 800, 3)
        rows = assign_reading_rows(blocks)
        infer_semantic_roles(blocks, rows)
        records = reconstruct_records(blocks, rows)
        self.assertEqual(records[0]["code"], "003.085")
        self.assertEqual(records[0]["name"], "Fct. assig. trigger")
        self.assertEqual([value["text"] for value in records[0]["values"]], [
            "040.077 Starting IN>",
            "040.041 Starting IN>>",
            "039.078 Starting IN>>>",
        ])
        self.assertTrue(records[0]["is_multi_value"])

    def test_builds_directional_graph_edges(self) -> None:
        blocks = normalize_blocks(self.make_blocks(), 600, 800, 3)
        rows = assign_reading_rows(blocks)
        graph = build_graph(blocks, rows)
        relations = {edge["relation"] for edge in graph["edges"]}
        self.assertIn("nearest_right", relations)
        self.assertIn("nearest_below", relations)

    def test_reconstructs_wrapped_value_from_original_columns(self) -> None:
        raw = [
            {"id": "b0000", "text": "FlexLogic Entry 27", "polygon": [[10, 10], [150, 10], [150, 30], [10, 30]]},
            {"id": "b0001", "text": "Protection Element", "polygon": [[170, 10], [290, 10], [290, 30], [170, 30]]},
            {"id": "b0002", "text": "Direct I/P 1-1 On ((khóa", "polygon": [[310, 10], [520, 10], [520, 30], [310, 30]]},
            {"id": "b0003", "text": "bảo vệ so lệch tại chỗ))", "polygon": [[310, 38], [500, 38], [500, 58], [310, 58]]},
        ]
        blocks = normalize_blocks(raw, 600, 800, 3)
        rows = assign_reading_rows(blocks)
        infer_semantic_roles(blocks, rows)
        record = reconstruct_records(blocks, rows)[0]
        self.assertEqual(record["name"], "FlexLogic Entry 27 | Protection Element")
        self.assertEqual(record["values"][0]["text"], "Direct I/P 1-1 On ((khóa bảo vệ so lệch tại chỗ))")
        self.assertTrue(record["is_multiline"])

    def test_parameter_code_regex_does_not_treat_dates_as_codes(self) -> None:
        raw = [{"id": "b0000", "text": "23/4/2026", "polygon": [[10, 10], [100, 10], [100, 30], [10, 30]]}]
        blocks = normalize_blocks(raw, 600, 800, 1)
        rows = assign_reading_rows(blocks)
        infer_semantic_roles(blocks, rows)
        self.assertNotEqual(blocks[0]["semantic_role"], "parameter_code")

    def test_page_number_uses_page_suffix_not_document_variant(self) -> None:
        self.assertEqual(infer_page_number(Path("PCS-902_3-page-001.png"))[0], 1)
        self.assertEqual(infer_page_number(Path("relay-page-003.png"))[0], 3)
        self.assertEqual(infer_page_number(Path("relay_p2.png"))[0], 2)


if __name__ == "__main__":
    unittest.main()
