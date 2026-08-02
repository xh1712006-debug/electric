import unittest

from lab.structure_analysis.layoutlmv3.entities import bio_entities
from lab.structure_analysis.layoutlmv3.metrics import classification_metrics


def prediction(index: int, text: str, label: str, block_id: str = "b0") -> dict:
    return {
        "word_id": f"w{index}",
        "word_index": index,
        "block_id": block_id,
        "text": text,
        "bbox_pixel": [index * 10, 0, index * 10 + 9, 10],
        "target_schema_label": label,
        "confidence": 0.9,
    }


class EntityMetricTests(unittest.TestCase):
    def test_wrapped_value_becomes_one_entity_across_blocks(self) -> None:
        rows = [
            prediction(0, "Direct", "B-PARAM_VALUE", "b0"),
            prediction(1, "I/P", "I-PARAM_VALUE", "b0"),
            prediction(2, "bảo", "I-PARAM_VALUE", "b1"),
            prediction(3, "vệ", "I-PARAM_VALUE", "b1"),
        ]
        entities = bio_entities(rows, "target_schema_label")
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]["text"], "Direct I/P bảo vệ")
        self.assertEqual(entities[0]["block_ids"], ["b0", "b1"])

    def test_metrics_require_exact_entity_span(self) -> None:
        gold = ["B-PARAM_NAME", "I-PARAM_NAME", "O", "B-PARAM_VALUE"]
        predicted = ["B-PARAM_NAME", "O", "O", "B-PARAM_VALUE"]
        metrics = classification_metrics(gold, predicted)
        self.assertAlmostEqual(metrics["token"]["precision"], 1.0)
        self.assertLess(metrics["entity"]["f1"], 1.0)
        self.assertIn("B-PARAM_VALUE", metrics["per_class_f1"])


if __name__ == "__main__":
    unittest.main()
