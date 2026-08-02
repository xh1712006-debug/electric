"""Verify the complete runtime used by the local OCR debug UI."""

from __future__ import annotations

import argparse
import importlib
from importlib import metadata
import json
from pathlib import Path
import sys
from typing import Any, Callable


DEPENDENCIES = {
    "cv2": "opencv-python",
    "numpy": "numpy",
    # On Windows, load PyTorch before Paddle. The reverse order can make
    # torch/lib/shm.dll fail with WinError 127 because of native DLL clashes.
    "torch": "torch",
    "paddle": "paddlepaddle",
    "paddleocr": "paddleocr",
    "PIL": "Pillow",
    "vietocr": "vietocr",
    "pypdf": "pypdf",
    "streamlit": "streamlit",
}


def dependency_versions(
    importer: Callable[[str], Any] = importlib.import_module,
    version_reader: Callable[[str], str] = metadata.version,
) -> tuple[dict[str, str], list[str]]:
    versions: dict[str, str] = {}
    errors: list[str] = []
    for module_name, distribution_name in DEPENDENCIES.items():
        try:
            importer(module_name)
            versions[distribution_name] = version_reader(distribution_name)
        except Exception as exc:  # Native ML imports can fail for reasons beyond ImportError.
            errors.append(f"{distribution_name}: {type(exc).__name__}: {exc}")
    return versions, errors


def poppler_paths() -> tuple[dict[str, str], list[str]]:
    try:
        from src.pdf_form_splitter.pdf_io import poppler_binary

        return (
            {name: poppler_binary(name) for name in ("pdftoppm", "pdfinfo")},
            [],
        )
    except Exception as exc:
        return {}, [f"Poppler: {type(exc).__name__}: {exc}"]


def warmup_models() -> list[str]:
    """Initialise both OCR models so downloads and native errors happen during setup."""

    errors: list[str] = []
    try:
        from src.recognition.service import VietnameseRecognitionService

        VietnameseRecognitionService(use_gpu=False)
    except Exception as exc:
        errors.append(f"VietOCR recognizer: {type(exc).__name__}: {exc}")
    try:
        from src.detection.service import DocumentTextDetectionService

        DocumentTextDetectionService(use_gpu=False)
    except Exception as exc:
        errors.append(f"PP-OCR detector: {type(exc).__name__}: {exc}")
    return errors


def build_report(*, warmup: bool = False) -> dict[str, Any]:
    versions, dependency_errors = dependency_versions()
    poppler, poppler_errors = poppler_paths()
    model_errors = warmup_models() if warmup else []
    errors = dependency_errors + poppler_errors + model_errors
    return {
        "ready": not errors,
        "python": sys.version.split()[0],
        "python_executable": str(Path(sys.executable).resolve()),
        "dependencies": versions,
        "poppler": poppler,
        "models_warmed_up": warmup and not model_errors,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--warmup-models",
        action="store_true",
        help="Initialise PP-OCR and VietOCR, downloading their files if required.",
    )
    args = parser.parse_args()
    report = build_report(warmup=args.warmup_models)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
