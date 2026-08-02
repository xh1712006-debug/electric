"""Chỉ số token và entity có thể chạy mà không cần seqeval."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


def _safe_prf(true_positive: int, false_positive: int, false_negative: int) -> dict[str, float]:
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def _entity_spans(labels: Iterable[str]) -> set[tuple[str, int, int]]:
    spans: set[tuple[str, int, int]] = set()
    active_type: str | None = None
    start = -1
    sequence = list(labels)
    for index, label in enumerate(sequence + ["O"]):
        if label == "O" or "-" not in label:
            prefix, entity_type = "O", None
        else:
            prefix, entity_type = label.split("-", 1)
        continuation = prefix == "I" and active_type == entity_type
        if active_type is not None and not continuation:
            spans.add((active_type, start, index - 1))
            active_type = None
        if prefix == "B" or (prefix == "I" and not continuation):
            active_type = entity_type
            start = index
    return spans


def classification_metrics(gold: list[str], predicted: list[str]) -> dict[str, Any]:
    if len(gold) != len(predicted):
        raise ValueError("Gold và prediction phải có cùng số token")
    labels = sorted((set(gold) | set(predicted)) - {"O"})
    per_class: dict[str, dict[str, float]] = {}
    token_tp = token_fp = token_fn = 0
    for label in labels:
        tp = sum(g == label and p == label for g, p in zip(gold, predicted))
        fp = sum(g != label and p == label for g, p in zip(gold, predicted))
        fn = sum(g == label and p != label for g, p in zip(gold, predicted))
        per_class[label] = _safe_prf(tp, fp, fn)
        token_tp += tp
        token_fp += fp
        token_fn += fn

    gold_entities = _entity_spans(gold)
    predicted_entities = _entity_spans(predicted)
    entity_tp = len(gold_entities & predicted_entities)
    entity_fp = len(predicted_entities - gold_entities)
    entity_fn = len(gold_entities - predicted_entities)
    return {
        "token": _safe_prf(token_tp, token_fp, token_fn),
        "entity": _safe_prf(entity_tp, entity_fp, entity_fn),
        "per_class_f1": {
            label: values["f1"] for label, values in per_class.items()
        },
        "per_class": per_class,
        "evaluated_tokens": len(gold),
        "gold_entities": len(gold_entities),
        "predicted_entities": len(predicted_entities),
    }


def unavailable_metrics(reason: str, **runtime: Any) -> dict[str, Any]:
    return {
        "ground_truth_available": False,
        "reason": reason,
        "token": {"precision": None, "recall": None, "f1": None},
        "entity": {"precision": None, "recall": None, "f1": None},
        "per_class_f1": {},
        "runtime": runtime,
    }
