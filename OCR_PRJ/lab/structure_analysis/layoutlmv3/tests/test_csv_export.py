import unittest

from lab.structure_analysis.layoutlmv3.csv_export import RECORD_COLUMNS, record_rows, unassigned_rows


class CsvExportTests(unittest.TestCase):
    def test_exports_one_readable_row_per_record(self) -> None:
        page = {
            "document_id": "relay-page-003",
            "page_number": 3,
            "sections": [
                {
                    "title": {"text": "Nhóm bảo vệ"},
                    "records": [
                        {
                            "record_id": "record_0001",
                            "code": {"text": "003.085", "source_block_ids": ["b1"]},
                            "name": {"text": "Fct. assig. trigger", "source_block_ids": ["b2"]},
                            "values": [
                                {"text": "040.077 Starting IN>", "source_block_ids": ["b3"]},
                                {"text": "040.041 Starting IN>>", "source_block_ids": ["b4"]},
                            ],
                            "grouping_confidence": 0.85,
                            "relationship_status": "geometric_candidate_not_ground_truth",
                            "source_row_ids": ["row_0003"],
                            "grouping_evidence": ["cùng hàng"],
                        }
                    ],
                }
            ],
            "records_without_section": [],
            "unassigned_rows": [],
        }
        rows = record_rows(page)
        self.assertEqual(list(rows[0]), list(RECORD_COLUMNS))
        self.assertEqual(rows[0]["Nhóm"], "Nhóm bảo vệ")
        self.assertEqual(rows[0]["Giá trị"], "040.077 Starting IN> | 040.041 Starting IN>>")
        self.assertEqual(rows[0]["Số giá trị"], "2")

    def test_exports_unassigned_rows_separately(self) -> None:
        page = {
            "document_id": "relay-page-003",
            "page_number": 3,
            "unassigned_rows": [
                {"source_row_id": "row_0010", "text": "Ghi chú", "source_block_ids": ["b9"], "reason": "thiếu cột"}
            ],
        }
        rows = unassigned_rows(page)
        self.assertEqual(rows[0]["Nội dung OCR chưa gom"], "Ghi chú")


if __name__ == "__main__":
    unittest.main()
