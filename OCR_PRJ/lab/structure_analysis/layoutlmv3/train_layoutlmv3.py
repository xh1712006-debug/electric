"""Fine-tune LayoutLMv3; từ chối chạy khi chưa có annotation thật hợp lệ."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image

from .data import load_annotations
from .encoding import encode_page
from .run_layoutlmv3 import ANNOTATION_SOURCE, OUTPUT_ROOT, write_json
from .schema import ID_TO_LABEL, LABELS, LABEL_TO_ID


CONFIG_PATH = Path(__file__).resolve().parent / "training_config.json"


class ChunkDataset:
    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self.chunks = chunks

    def __len__(self) -> int:
        return len(self.chunks)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.chunks[index]["model_inputs"]


def encode_annotations(
    annotations: list[dict[str, Any]], processor: Any, config: dict[str, Any]
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for annotation in annotations:
        words = annotation["words"]
        labels = [word["label"] for word in words]
        with Image.open(annotation["image_path"]) as image:
            chunks.extend(
                encode_page(
                    processor,
                    image.convert("RGB"),
                    words,
                    labels=labels,
                    max_length=int(config["max_length"]),
                    stride=int(config["stride"]),
                )
            )
    return chunks


def trainer_metrics(evaluation: Any) -> dict[str, float]:
    import numpy as np

    logits, labels = evaluation
    predicted = np.argmax(logits, axis=-1)
    gold_flat: list[str] = []
    prediction_flat: list[str] = []
    for prediction_row, label_row in zip(predicted, labels):
        for prediction_id, label_id in zip(prediction_row, label_row):
            if int(label_id) == -100:
                continue
            gold_flat.append(ID_TO_LABEL[int(label_id)])
            prediction_flat.append(ID_TO_LABEL[int(prediction_id)])
    from .metrics import classification_metrics

    measured = classification_metrics(gold_flat, prediction_flat)
    return {
        "token_precision": measured["token"]["precision"],
        "token_recall": measured["token"]["recall"],
        "token_f1": measured["token"]["f1"],
        "entity_precision": measured["entity"]["precision"],
        "entity_recall": measured["entity"]["recall"],
        "entity_f1": measured["entity"]["f1"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations-dir", default=str(ANNOTATION_SOURCE))
    parser.add_argument("--config", default=str(CONFIG_PATH))
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    annotations, audit = load_annotations(Path(args.annotations_dir))
    train_pages = [row for row in annotations if row["split"] == "train"]
    validation_pages = [row for row in annotations if row["split"] == "validation"]
    manifest = {
        "annotation_audit": audit,
        "train_pages": len(train_pages),
        "validation_pages": len(validation_pages),
        "labels": list(LABELS),
        "config": config,
    }
    write_json(OUTPUT_ROOT / "training" / "training_manifest.json", manifest)
    if not train_pages:
        raise SystemExit(
            "Không có annotation split=train hợp lệ. Không khởi tạo classifier ngẫu nhiên hoặc tạo kết quả giả."
        )

    try:
        from transformers import (
            AutoModelForTokenClassification,
            AutoProcessor,
            Trainer,
            TrainingArguments,
            default_data_collator,
        )
    except ImportError as exc:
        raise SystemExit("Hãy cài requirements-layoutlmv3.txt trước khi train.") from exc

    processor = AutoProcessor.from_pretrained(config["base_model"], apply_ocr=False)
    train_dataset = ChunkDataset(encode_annotations(train_pages, processor, config))
    validation_dataset = (
        ChunkDataset(encode_annotations(validation_pages, processor, config))
        if validation_pages
        else None
    )
    model = AutoModelForTokenClassification.from_pretrained(
        config["base_model"],
        num_labels=len(LABELS),
        label2id=LABEL_TO_ID,
        id2label=ID_TO_LABEL,
        ignore_mismatched_sizes=True,
    )
    training_output = OUTPUT_ROOT / "training" / "checkpoints"
    arguments = TrainingArguments(
        output_dir=str(training_output),
        learning_rate=float(config["learning_rate"]),
        per_device_train_batch_size=int(config["train_batch_size"]),
        per_device_eval_batch_size=int(config["eval_batch_size"]),
        num_train_epochs=float(config["epochs"]),
        weight_decay=float(config["weight_decay"]),
        eval_strategy="epoch" if validation_dataset else "no",
        save_strategy="epoch",
        logging_steps=int(config["logging_steps"]),
        load_best_model_at_end=bool(validation_dataset),
        metric_for_best_model="entity_f1" if validation_dataset else None,
        report_to=[],
        remove_unused_columns=False,
        seed=int(config["seed"]),
    )
    trainer = Trainer(
        model=model,
        args=arguments,
        train_dataset=train_dataset,
        eval_dataset=validation_dataset,
        data_collator=default_data_collator,
        compute_metrics=trainer_metrics if validation_dataset else None,
        processing_class=processor,
    )
    train_result = trainer.train()
    final_directory = OUTPUT_ROOT / "training" / "final_model"
    trainer.save_model(str(final_directory))
    processor.save_pretrained(str(final_directory))
    write_json(
        OUTPUT_ROOT / "training" / "train_metrics.json",
        {key: float(value) for key, value in train_result.metrics.items()},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
