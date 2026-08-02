"""Schema nhãn dùng chung cho chuẩn bị dữ liệu, huấn luyện và đánh giá."""

from __future__ import annotations

from typing import Iterable


LABELS = (
    "O",
    "B-SECTION",
    "I-SECTION",
    "B-RECORD_KEY",
    "I-RECORD_KEY",
    "B-PARAM_CODE",
    "I-PARAM_CODE",
    "B-PARAM_NAME",
    "I-PARAM_NAME",
    "B-PARAM_VALUE",
    "I-PARAM_VALUE",
    "B-NOTE",
    "I-NOTE",
)

LABEL_TO_ID = {label: index for index, label in enumerate(LABELS)}
ID_TO_LABEL = {index: label for label, index in LABEL_TO_ID.items()}
ENTITY_TYPES = tuple(
    label.removeprefix("B-") for label in LABELS if label.startswith("B-")
)


def split_bio(label: str) -> tuple[str, str | None]:
    if label == "O":
        return "O", None
    if label not in LABEL_TO_ID:
        raise ValueError(f"Nhãn không thuộc schema: {label!r}")
    prefix, entity_type = label.split("-", 1)
    return prefix, entity_type


def validate_bio_sequence(labels: Iterable[str]) -> list[str]:
    """Kiểm tra chuỗi BIO; không tự sửa nhãn do người gán."""

    errors: list[str] = []
    previous_type: str | None = None
    previous_prefix = "O"
    for index, label in enumerate(labels):
        if label not in LABEL_TO_ID:
            errors.append(f"Từ {index}: nhãn {label!r} không hợp lệ")
            previous_prefix, previous_type = "O", None
            continue
        prefix, entity_type = split_bio(label)
        if prefix == "I" and (
            previous_prefix not in {"B", "I"} or previous_type != entity_type
        ):
            errors.append(
                f"Từ {index}: {label} không đứng sau B-/I- của cùng loại thực thể"
            )
        previous_prefix, previous_type = prefix, entity_type
    return errors
