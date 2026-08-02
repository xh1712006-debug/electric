import unittest

from lab.structure_analysis.layoutlmv3.data import (
    blocks_to_words,
    normalize_bbox_1000,
    validate_completed_annotation,
)


class DataTests(unittest.TestCase):
    def test_block_to_words_preserves_block_mapping(self) -> None:
        raw = {
            "image_width": 1000,
            "image_height": 2000,
            "blocks": [
                {
                    "block_id": "b0007",
                    "text": "Direct I/P 1-1 On",
                    "polygon": [[100, 200], [900, 200], [900, 300], [100, 300]],
                    "detection_confidence": 0.9,
                }
            ],
        }
        words = blocks_to_words(raw)
        self.assertEqual([row["text"] for row in words], ["Direct", "I/P", "1-1", "On"])
        self.assertTrue(all(row["block_id"] == "b0007" for row in words))
        self.assertTrue(all(0 <= value <= 1000 for row in words for value in row["bbox_1000"]))
        self.assertLess(words[0]["bbox_pixel"][0], words[-1]["bbox_pixel"][0])

    def test_normalization_clamps_outside_pixels(self) -> None:
        self.assertEqual(normalize_bbox_1000([-10, 5, 120, 200], 100, 100), [0, 50, 1000, 1000])

    def test_draft_annotation_is_not_training_data(self) -> None:
        payload = {
            "status": "draft",
            "page_number": 3,
            "split": "train",
            "words": [
                {
                    "word_id": "w00000",
                    "text": "003.085",
                    "bbox_1000": [0, 0, 10, 10],
                    "label": None,
                }
            ],
        }
        errors = validate_completed_annotation(payload)
        self.assertGreaterEqual(len(errors), 2)


if __name__ == "__main__":
    unittest.main()
