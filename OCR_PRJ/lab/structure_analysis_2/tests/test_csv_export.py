import csv
import tempfile
import unittest
from pathlib import Path

from lab.structure_analysis_2.run_experiment import CSV_FIELDS, write_csv_outputs


def page(document_id, page_number, value):
    return {
        "document_id": document_id,
        "page_number": page_number,
        "layout": {"family": "bon_cot_can_chinh"},
        "records": [{
            "group_id": None,
            "record_key": {"text": str(page_number)},
            "parameter_name": {"text": "Parameter"},
            "value": {"text": value},
            "source_row_ids": [f"row_{page_number}"],
        }],
    }


class CSVExportTests(unittest.TestCase):
    def test_writes_one_csv_per_document_and_keeps_combined_csv(self):
        payload = {"pages": [
            page("relay_A-page-003", 3, "On"),
            page("relay_A-page-004", 4, "Off"),
            page("relay_B-page-003", 3, "Enabled"),
        ]}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            combined, documents = write_csv_outputs(payload, output)
            self.assertTrue(combined.exists())
            self.assertEqual([path.name for path in documents], ["relay_A.csv", "relay_B.csv"])
            with (output / "records_by_document" / "relay_A.csv").open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(list(rows[0]), CSV_FIELDS)
            self.assertEqual([row["page_number"] for row in rows], ["3", "4"])

    def test_csv_has_utf8_bom_for_excel(self):
        payload = {"pages": [page("phiếu_01-page-003", 3, "Đúng")]} 
        with tempfile.TemporaryDirectory() as directory:
            _, documents = write_csv_outputs(payload, Path(directory))
            self.assertEqual(documents[0].read_bytes()[:3], b"\xef\xbb\xbf")


if __name__ == "__main__":
    unittest.main()
