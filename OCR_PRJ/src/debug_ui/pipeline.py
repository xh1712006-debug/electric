"""Thin debug adapter around the production document orchestrator."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any, Iterable

from src.pdf_form_splitter import PdfFormSplitterService, PdfSplitterConfig
from src.pdf_form_splitter.pdf_io import pdf_page_count
from src.relay_form_ocr import (
    DocumentOcrOrchestrator,
    PdfCandidate,
    ProgressCallback,
    field_text,
    flatten_record,
    note_candidate,
    page_role,
)


def safe_pdf_name(filename: str) -> str:
    """Keep an uploaded basename safe and ensure a PDF extension."""

    name = Path(filename).name
    stem = re.sub(r"[^0-9A-Za-zÀ-ỹ_. -]+", "_", Path(name).stem, flags=re.UNICODE).strip(" .")
    return f"{stem or 'uploaded'}.pdf"


class PdfOcrDebugPipeline:
    """Own debug-only upload/split concerns and delegate PDF_x extraction."""

    def __init__(self, *, use_gpu: bool = False, render_dpi: int = 160):
        self.use_gpu = use_gpu
        self.render_dpi = render_dpi
        self._orchestrator = DocumentOcrOrchestrator(use_gpu=use_gpu, render_dpi=render_dpi)

    def _models(self) -> tuple[Any, Any]:
        """Expose shared models for the PDF_A splitter without duplicating lifecycle logic."""

        return self._orchestrator.models()

    @staticmethod
    def save_uploaded_pdf(filename: str, content: bytes, directory: Path | str) -> Path:
        if b"%PDF" not in content[:1024]:
            raise ValueError(f"{filename} does not have a valid PDF signature")
        target_dir = Path(directory).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / safe_pdf_name(filename)
        if target.is_file() and target.read_bytes() != content:
            digest = hashlib.sha1(content).hexdigest()[:8]
            target = target.with_name(f"{target.stem}__{digest}{target.suffix}")
        target.write_bytes(content)
        return target

    @staticmethod
    def candidates(paths: Iterable[Path | str], *, origin: str) -> list[PdfCandidate]:
        result = []
        for value in paths:
            path = Path(value).resolve()
            pages = pdf_page_count(path)
            identity = hashlib.sha1(
                f"{path}:{path.stat().st_size}:{path.stat().st_mtime_ns}".encode()
            ).hexdigest()[:16]
            result.append(PdfCandidate(identity, path.name, str(path), pages, origin))
        return sorted(result, key=lambda item: item.name.casefold())

    def split_pdf_a(
        self,
        input_pdf: Path | str,
        output_dir: Path | str,
        *,
        progress: ProgressCallback | None = None,
    ) -> tuple[list[PdfCandidate], dict[str, Any]]:
        detector, recognizer = self._models()
        if progress:
            progress(0, 1, "Đang nhận diện ranh giới các phiếu trong PDF_A")
        splitter = PdfFormSplitterService(
            PdfSplitterConfig(
                dpi=self.render_dpi,
                use_gpu=self.use_gpu,
                render_reviews=False,
            ),
            detector=detector,
            recognizer=recognizer,
        )
        manifest = splitter.split_file(input_pdf, output_dir)
        documents = [Path(document["output_pdf"]) for document in manifest["documents"]]
        if progress:
            progress(1, 1, f"Đã tách được {len(documents)} PDF_x")
        return self.candidates(documents, origin="split_from_pdf_a"), manifest

    def extract_pdf_x(
        self,
        candidate: PdfCandidate,
        output_dir: Path | str,
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Delegate one-PDF extraction to the production implementation."""

        return self._orchestrator.extract_pdf_x(candidate, output_dir, progress=progress)


__all__ = [
    "PdfCandidate",
    "PdfOcrDebugPipeline",
    "field_text",
    "flatten_record",
    "note_candidate",
    "page_role",
    "safe_pdf_name",
]
