"""Production orchestration for extracting one relay-form PDF document."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time
import unicodedata
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from src.detection import DocumentTextDetectionService
from src.layout_analysis import Page1LayoutAnalysisService, Page3PlusLayoutAnalysisService
from src.pdf_form_splitter.pdf_io import render_pdf
from src.recognition import VietnameseRecognitionService

from .observability import (
    PipelineStageError,
    PipelineStageEvent,
    StageEventCallback,
)
from .schemas import ErrorCode, ErrorStage


ProgressCallback = Callable[[int, int, str], None]
Renderer = Callable[[Path, Path], Sequence[Path]]


class _Renderer(Protocol):
    def __call__(self, pdf_path: Path, output_dir: Path, *, dpi: int) -> Sequence[Path]: ...


def page_role(page_number: int) -> str:
    """Return the fixed document role for a one-based page number."""

    if page_number < 1:
        raise ValueError("page_number must be one-based")
    if page_number == 1:
        return "page1"
    if page_number == 2:
        return "page2_skipped"
    return "page3_plus"


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn").replace("đ", "d")


def note_candidate(regions: Iterable[dict[str, Any]]) -> str | None:
    """Return raw OCR from a visible ``Lưu ý`` heading onward for review."""

    ordered = sorted(
        (region for region in regions if str(region.get("text", "")).strip()),
        key=lambda region: (
            min(float(point[1]) for point in region.get("polygon", [[0, 0]])),
            min(float(point[0]) for point in region.get("polygon", [[0, 0]])),
        ),
    )
    start = next(
        (
            index
            for index, region in enumerate(ordered)
            if "luu y" in " ".join(
                part for part in _plain(str(region["text"])).replace(":", " ").split() if part
            )
        ),
        None,
    )
    if start is None:
        return None
    return "\n".join(str(region["text"]).strip() for region in ordered[start:])


def field_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        text = value.get("text")
        return None if text is None else str(text)
    return str(value)


def flatten_record(record: Mapping[str, Any]) -> dict[str, Any]:
    columns = (
        "record_id",
        "group_id",
        "record_key",
        "parameter_code",
        "parameter_name",
        "value",
        "range",
        "unit",
        "description",
    )
    return {column: field_text(record.get(column)) for column in columns}


@dataclass(frozen=True)
class PdfCandidate:
    """Internal document descriptor shared by production and debug adapters."""

    candidate_id: str
    name: str
    path: str
    page_count: int
    origin: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _layout_warnings(layout: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    many = layout.get("warnings")
    if isinstance(many, list):
        warnings.extend(str(item) for item in many if str(item).strip())
    one = layout.get("warning")
    if one is not None and str(one).strip():
        warnings.append(str(one))
    return list(dict.fromkeys(warnings))


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


class DocumentOcrOrchestrator:
    """Own the single production path for rendering and extracting one PDF_x."""

    def __init__(
        self,
        *,
        use_gpu: bool = False,
        render_dpi: int = 160,
        detector: Any | None = None,
        recognizer: Any | None = None,
        page1_service: Any | None = None,
        page3_plus_service: Any | None = None,
        renderer: _Renderer = render_pdf,
    ) -> None:
        if render_dpi <= 0:
            raise ValueError("render_dpi must be greater than zero")
        self.use_gpu = use_gpu
        self.render_dpi = render_dpi
        self._detector = detector
        self._recognizer = recognizer
        self._page1 = page1_service or Page1LayoutAnalysisService()
        self._page3_plus = page3_plus_service or Page3PlusLayoutAnalysisService()
        self._renderer = renderer

    def models(self) -> tuple[Any, Any]:
        """Create OCR models once, preserving the required Windows load order."""

        # PyTorch/VietOCR must load before Paddle on Windows (WinError 127).
        if self._recognizer is None:
            try:
                self._recognizer = VietnameseRecognitionService(use_gpu=self.use_gpu)
            except Exception as exc:
                msg = str(exc) if str(exc) else "Không thể khởi tạo bộ nhận dạng văn bản."
                raise PipelineStageError(
                    ErrorCode.RECOGNITION_FAILED,
                    ErrorStage.RECOGNITION,
                    msg,
                    retryable=True,
                ) from exc
        if self._detector is None:
            try:
                self._detector = DocumentTextDetectionService(use_gpu=self.use_gpu)
            except Exception as exc:
                msg = str(exc) if str(exc) else "Không thể khởi tạo bộ phát hiện văn bản."
                raise PipelineStageError(
                    ErrorCode.DETECTION_FAILED,
                    ErrorStage.DETECTION,
                    msg,
                    retryable=True,
                ) from exc
        return self._detector, self._recognizer

    def extract_pdf_x(
        self,
        candidate: PdfCandidate,
        output_dir: Path | str,
        *,
        progress: ProgressCallback | None = None,
        stage_event: StageEventCallback | None = None,
        stage: str = "all",
    ) -> dict[str, Any]:
        """Extract a single PDF_x and persist page evidence plus a summary JSON."""

        started = time.perf_counter()
        source = Path(candidate.path).resolve()
        document_id = source.stem
        output = Path(output_dir).resolve()
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PipelineStageError(
                ErrorCode.ARTIFACT_WRITE_FAILED,
                ErrorStage.ARTIFACT_WRITE,
                "Không thể chuẩn bị thư mục artifact của tài liệu.",
                retryable=True,
            ) from exc
        if stage_event:
            stage_event(PipelineStageEvent(ErrorStage.RENDERING, "started"))
        try:
            if stage == "header":
                rendered = [Path(item) for item in self._renderer(source, output / "rendered", dpi=self.render_dpi, first_page=1, last_page=min(2, candidate.page_count))]
            else:
                rendered = [Path(item) for item in self._renderer(source, output / "rendered", dpi=self.render_dpi)]
        except TypeError:
            rendered = [Path(item) for item in self._renderer(source, output / "rendered", dpi=self.render_dpi)]
        except Exception as exc:
            raise PipelineStageError(
                ErrorCode.PDF_RENDER_FAILED,
                ErrorStage.RENDERING,
                "Không thể render các trang PDF.",
                retryable=True,
            ) from exc
        if stage_event:
            stage_event(
                PipelineStageEvent(
                    ErrorStage.RENDERING,
                    "completed",
                    total_pages=len(rendered),
                )
            )

        if stage == "details" and len(rendered) <= 2:
            # File chỉ có tối đa 2 trang, không có trang 3+ nào để xử lý details
            return {
                "schema_version": "1.0",
                "stage": "details",
                "status": "success",
                "document": candidate.as_dict(),
                "setting_records": [],
                "note_candidates": [],
                "warnings": [],
                "pages": [],
                "summary": {
                    "pages": len(rendered),
                    "ocr_pages": 0,
                    "skipped_pages": 0,
                    "setting_records": 0,
                    "note_candidates": 0,
                    "warnings": 0,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            }

        detector, recognizer = self.models()

        pages: list[dict[str, Any]] = []
        important_fields: dict[str, Any] = {}
        important_source_labels: dict[str, Any] = {}
        important_field_resolution: dict[str, Any] = {}
        setting_records: list[dict[str, Any]] = []
        notes: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        artifacts: list[dict[str, str]] = [
            {"kind": "rendered_page", "relative_path": _relative_path(path, output)} for path in rendered
        ]

        if candidate.page_count != len(rendered) and stage == "all":
            warnings.append(
                {
                    "code": "page_count_mismatch",
                    "message": f"Metadata khai báo {candidate.page_count} trang nhưng renderer tạo {len(rendered)} trang.",
                }
            )

        page_output = output / "pages"
        try:
            page_output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PipelineStageError(
                ErrorCode.ARTIFACT_WRITE_FAILED,
                ErrorStage.ARTIFACT_WRITE,
                "Không thể chuẩn bị thư mục kết quả từng trang.",
                retryable=True,
            ) from exc
        for page_number, image_path in enumerate(rendered, start=1):
            if stage == "header" and page_number > 2:
                break
            if stage == "details" and page_number <= 2:
                continue

            role = page_role(page_number)
            if progress:
                progress(page_number, candidate.page_count, f"{candidate.name}: trang {page_number}/{candidate.page_count}")

            if role == "page2_skipped":
                if stage_event:
                    stage_event(
                        PipelineStageEvent(
                            ErrorStage.LAYOUT,
                            "skipped_by_policy",
                            page_number=page_number,
                            total_pages=len(rendered),
                        )
                    )
                page_warnings = ["Trang 2 được bỏ qua theo chính sách tài liệu; không chạy OCR hoặc layout."]
                warnings.append(
                    {
                        "code": "page2_skipped_by_document_policy",
                        "page_number": page_number,
                        "message": page_warnings[0],
                    }
                )
                page_payload: dict[str, Any] = {
                    "page_number": page_number,
                    "page_role": role,
                    "image_path": str(image_path),
                    "status": "skipped_by_document_policy",
                    "warnings": page_warnings,
                    "raw_ocr": [],
                    "layout": None,
                }
            else:
                if stage_event:
                    stage_event(
                        PipelineStageEvent(
                            ErrorStage.DETECTION,
                            "started",
                            page_number=page_number,
                            total_pages=len(rendered),
                        )
                    )
                try:
                    detection = detector.detect_page(image_path)
                    detection_payload = detection.as_dict()
                except Exception as exc:
                    raise PipelineStageError(
                        ErrorCode.DETECTION_FAILED,
                        ErrorStage.DETECTION,
                        "Không thể phát hiện vùng văn bản trên trang tài liệu.",
                        retryable=True,
                    ) from exc
                if stage_event:
                    stage_event(
                        PipelineStageEvent(
                            ErrorStage.DETECTION,
                            "completed",
                            page_number=page_number,
                            total_pages=len(rendered),
                        )
                    )

                if stage_event:
                    stage_event(
                        PipelineStageEvent(
                            ErrorStage.RECOGNITION,
                            "started",
                            page_number=page_number,
                            total_pages=len(rendered),
                        )
                    )
                try:
                    recognition = recognizer.recognise_page(image_path, detection.detections)
                    recognition_payload = recognition.as_dict()
                    regions = recognition_payload["regions"]
                except Exception as exc:
                    raise PipelineStageError(
                        ErrorCode.RECOGNITION_FAILED,
                        ErrorStage.RECOGNITION,
                        "Không thể nhận dạng văn bản trên trang tài liệu.",
                        retryable=True,
                    ) from exc
                if stage_event:
                    stage_event(
                        PipelineStageEvent(
                            ErrorStage.RECOGNITION,
                            "completed",
                            page_number=page_number,
                            total_pages=len(rendered),
                        )
                    )

                if stage_event:
                    stage_event(
                        PipelineStageEvent(
                            ErrorStage.LAYOUT,
                            "started",
                            page_number=page_number,
                            total_pages=len(rendered),
                        )
                    )
                try:
                    if role == "page1":
                        layout = self._page1.analyse_page(
                            image_path,
                            regions,
                            document_id=document_id,
                        ).as_dict()
                    else:
                        layout = self._page3_plus.analyse_page(
                            image_path,
                            regions,
                            document_id=document_id,
                            page_number=page_number,
                        ).as_dict()
                except Exception as exc:
                    raise PipelineStageError(
                        ErrorCode.LAYOUT_FAILED,
                        ErrorStage.LAYOUT,
                        "Không thể phân tích bố cục trang tài liệu.",
                        retryable=False,
                    ) from exc
                if stage_event:
                    stage_event(
                        PipelineStageEvent(
                            ErrorStage.LAYOUT,
                            "completed",
                            page_number=page_number,
                            total_pages=len(rendered),
                        )
                    )

                if role == "page1":
                    important_fields = {
                        name: field_text(value) for name, value in layout.get("fields", {}).items()
                    }
                    important_source_labels = {
                        name: field_text(value) for name, value in layout.get("source_labels", {}).items()
                    }
                    resolution = layout.get("field_resolution")
                    important_field_resolution = dict(resolution) if isinstance(resolution, Mapping) else {}
                else:
                    for record in layout.get("records", []):
                        setting_records.append({"page_number": page_number, **flatten_record(record)})
                    note = note_candidate(regions)
                    if note:
                        notes.append({"page_number": page_number, "text": note})

                page_warnings = _layout_warnings(layout)
                for message in page_warnings:
                    warnings.append(
                        {
                            "code": "layout_warning",
                            "page_number": page_number,
                            "message": message,
                        }
                    )
                page_payload = {
                    "page_number": page_number,
                    "page_role": role,
                    "image_path": str(image_path),
                    "status": "completed",
                    "warnings": page_warnings,
                    "detection": detection_payload,
                    "recognition": recognition_payload,
                    "raw_ocr": regions,
                    "layout": layout,
                }

            pages.append(page_payload)
            page_json = page_output / f"page_{page_number:04d}.json"
            try:
                page_json.write_text(json.dumps(page_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError as exc:
                raise PipelineStageError(
                    ErrorCode.ARTIFACT_WRITE_FAILED,
                    ErrorStage.ARTIFACT_WRITE,
                    "Không thể ghi artifact kết quả trang.",
                    retryable=True,
                ) from exc
            artifacts.append({"kind": "page_result", "relative_path": _relative_path(page_json, output)})
            if stage_event:
                stage_event(
                    PipelineStageEvent(
                        ErrorStage.ARTIFACT_WRITE,
                        "page_completed",
                        page_number=page_number,
                        total_pages=len(rendered),
                    )
                )

        result = {
            "schema_version": "1.0",
            "stage": stage,
            "document": candidate.as_dict(),
            "important_fields": important_fields,
            "important_source_labels": important_source_labels,
            "important_field_resolution": important_field_resolution,
            "setting_records": setting_records,
            "note_candidates": notes,
            "warnings": warnings,
            "pages": pages,
            "artifacts": [*artifacts, {"kind": "extraction_result", "relative_path": "extraction.json"}],
            "summary": {
                "pages": len(rendered),
                "ocr_pages": sum(page["status"] == "completed" for page in pages),
                "skipped_pages": sum(page["status"].startswith("skipped") for page in pages),
                "important_fields_populated": sum(value is not None for value in important_fields.values()),
                "setting_records": len(setting_records),
                "note_candidates": len(notes),
                "warnings": len(warnings),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        }
        try:
            (output / "extraction.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            raise PipelineStageError(
                ErrorCode.ARTIFACT_WRITE_FAILED,
                ErrorStage.ARTIFACT_WRITE,
                "Không thể ghi artifact tổng hợp tài liệu.",
                retryable=True,
            ) from exc
        if stage_event:
            stage_event(
                PipelineStageEvent(
                    ErrorStage.ARTIFACT_WRITE,
                    "document_completed",
                    total_pages=len(rendered),
                )
            )
        if progress:
            progress(len(rendered), len(rendered), f"Hoàn tất {candidate.name}")
        return result
