"""Synchronous local Python API for one relay-form PDF."""

from __future__ import annotations

from datetime import datetime, timezone
import inspect
import logging
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping, Sequence

from src.pdf_form_splitter.pdf_io import pdf_page_count

from .orchestrator import DocumentOcrOrchestrator, PdfCandidate
from .observability import (
    PipelineStageError,
    PipelineStageEvent,
    ProgressReporter,
    ServiceProgressCallback,
    StageEventCallback,
)
from .schemas import (
    Artifact,
    ArtifactManifest,
    BusinessResult,
    Confidence,
    ConfidenceLabel,
    DocumentIdentity,
    ErrorCode,
    ErrorStage,
    ExtractedField,
    FieldResolutionStatus,
    NoteCandidate,
    OcrRequest,
    OcrResult,
    OcrWarning,
    Page1Fields,
    PageResult,
    PageRole,
    PageStatus,
    ProcessingStatus,
    PublicError,
    ReviewStatus,
    SettingRecord,
    StageTimings,
    Timing,
)
from .workspace import (
    WorkspaceCollisionError,
    WorkspaceError,
    WorkspaceHandle,
    WorkspaceManager,
    WorkspaceSecurityError,
    WorkspaceWriteError,
    sha256_file,
)


PIPELINE_VERSION = "0.7.0"
PageCounter = Callable[[Path], int]


class _ServiceFailure(Exception):
    def __init__(
        self,
        code: ErrorCode,
        stage: ErrorStage,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.public_message = message
        self.retryable = retryable
        self.details = details


def _confidence_from_resolution(resolution: Mapping[str, Any]) -> Confidence | None:
    confidence = resolution.get("confidence")
    score = resolution.get("effective_score")
    if not isinstance(confidence, Mapping) or not isinstance(score, (int, float)):
        return None
    level = confidence.get("level")
    if not isinstance(level, int) or isinstance(level, bool) or level not in range(1, 6):
        return None
    label = {
        1: ConfidenceLabel.VERY_LOW,
        2: ConfidenceLabel.LOW,
        3: ConfidenceLabel.MEDIUM,
        4: ConfidenceLabel.HIGH,
        5: ConfidenceLabel.VERY_HIGH,
    }[level]
    return Confidence(level=level, label=label, score=max(0.0, min(100.0, float(score))))


def _field_resolution_status(value: str | None, resolution: Mapping[str, Any]) -> FieldResolutionStatus:
    if value is None:
        return FieldResolutionStatus.NOT_AVAILABLE
    if resolution.get("preserved_existing_value") is True:
        return FieldResolutionStatus.PRESERVED_EXISTING
    raw = str(resolution.get("status", "preserved_existing"))
    try:
        status = FieldResolutionStatus(raw)
    except ValueError:
        return FieldResolutionStatus.REVIEW_REQUIRED
    if status == FieldResolutionStatus.NOT_AVAILABLE:
        return FieldResolutionStatus.PRESERVED_EXISTING
    return status


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _warning_code(value: object) -> str:
    code = re.sub(r"[^A-Z0-9]+", "_", str(value).upper()).strip("_")
    if not code or not code[0].isalpha():
        code = f"OCR_{code or 'WARNING'}"
    if len(code) < 2:
        code = f"{code}_WARNING"
    return code[:128]


class RelayFormOcrService:
    """Public synchronous service that returns one terminal typed result."""

    def __init__(
        self,
        *,
        orchestrator: DocumentOcrOrchestrator | Any | None = None,
        use_gpu: bool = False,
        page_counter: PageCounter = pdf_page_count,
        pipeline_version: str = PIPELINE_VERSION,
        workspace_manager: WorkspaceManager | None = None,
        logger: logging.Logger | None = None,
        include_exception_trace: bool = False,
    ) -> None:
        if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?", pipeline_version) is None:
            raise ValueError("pipeline_version must be a semantic version")
        self._orchestrator = (
            orchestrator
            if orchestrator is not None
            else DocumentOcrOrchestrator(use_gpu=use_gpu)
        )
        self._page_counter = page_counter
        self._pipeline_version = pipeline_version
        self._workspace_manager = workspace_manager or WorkspaceManager()
        if logger is None:
            logger = logging.Logger("relay_form_ocr.silent", level=logging.CRITICAL + 1)
            logger.addHandler(logging.NullHandler())
        self._logger = logger
        self._include_exception_trace = include_exception_trace

    def process_pdf(
        self,
        request: OcrRequest,
        *,
        progress: ServiceProgressCallback | None = None,
    ) -> OcrResult:
        """Validate and process one PDF_x with monotonic, non-fatal progress."""

        if not isinstance(request, OcrRequest):
            raise TypeError("request must be an OcrRequest")

        started_at = datetime.now(timezone.utc)
        started_clock = time.perf_counter()
        validation_started = time.perf_counter()
        reporter = ProgressReporter(
            request.correlation_id,
            callback=progress,
            logger=self._logger,
            include_exception_trace=self._include_exception_trace,
        )
        reporter.emit(
            stage=ErrorStage.VALIDATION,
            event="validation_started",
            completed=0,
            message="Bắt đầu kiểm tra yêu cầu OCR.",
        )
        document: DocumentIdentity | None = None
        source: Path | None = None
        source_sha256: str | None = None
        workspace_handle: WorkspaceHandle | None = None

        try:
            source, source_sha256, page_count = self._validate_source(request.input_pdf)
            document = DocumentIdentity(
                document_id=f"document-{source_sha256[:16]}",
                source_name=source.name,
                source_sha256=source_sha256,
                page_count=page_count,
            )
            reporter.emit(
                stage=ErrorStage.VALIDATION,
                event="validation_completed",
                completed=5,
                message="Yêu cầu và tài liệu đầu vào hợp lệ.",
            )
            workspace_handle = self._workspace_manager.create(
                request.output_root,
                request.correlation_id,
                source_sha256,
            )
            reporter.emit(
                stage=ErrorStage.ARTIFACT_WRITE,
                event="workspace_reserved",
                completed=10,
                message="Đã giữ độc quyền workspace của lời gọi.",
            )
        except WorkspaceError as exc:
            validation_ms = (time.perf_counter() - validation_started) * 1000
            return self._terminal_failure(
                request,
                self._workspace_failure(exc, creating=True),
                started_at,
                started_clock,
                reporter,
                document=document,
                workspace_handle=workspace_handle,
                source_sha256_after=source_sha256,
                stage_ms=StageTimings(validation=validation_ms),
                exception=exc,
            )
        except _ServiceFailure as failure:
            validation_ms = (time.perf_counter() - validation_started) * 1000
            return self._terminal_failure(
                request,
                failure,
                started_at,
                started_clock,
                reporter,
                document=document,
                workspace_handle=workspace_handle,
                source_sha256_after=source_sha256,
                stage_ms=StageTimings(validation=validation_ms),
                exception=failure.__cause__,
            )

        assert source is not None and source_sha256 is not None and workspace_handle is not None
        validation_ms = (time.perf_counter() - validation_started) * 1000
        pipeline_started = time.perf_counter()
        candidate = PdfCandidate(
            candidate_id=document.document_id,
            name=document.source_name,
            path=str(source),
            page_count=document.page_count,
            origin="local_python_api",
        )

        def stage_callback(stage: PipelineStageEvent) -> None:
            reporter.emit(
                stage=stage.stage,
                event=f"{stage.stage.value}_{stage.event}",
                completed=self._stage_progress(stage),
                message=self._stage_message(stage),
                page_number=stage.page_number,
            )

        try:
            internal = self._extract_with_stage_events(
                candidate,
                workspace_handle.path,
                stage_callback,
            )
            pipeline_ms = (time.perf_counter() - pipeline_started) * 1000
            source_sha256_after = self._source_sha256_after(source)
            if source_sha256_after != source_sha256:
                return self._terminal_failure(
                    request,
                    _ServiceFailure(
                        ErrorCode.INVALID_REQUEST,
                        ErrorStage.VALIDATION,
                        "Tệp PDF đầu vào đã thay đổi trong thời gian xử lý.",
                        details={"reason": "source_modified"},
                    ),
                    started_at,
                    started_clock,
                    reporter,
                    document=document,
                    workspace_handle=workspace_handle,
                    source_sha256_after=source_sha256_after,
                    stage_ms=StageTimings(validation=validation_ms, pipeline=pipeline_ms),
                )
            result = self._success_result(
                request,
                document,
                workspace_handle,
                internal,
                started_at,
                started_clock,
                source_sha256_after=source_sha256_after,
                validation_ms=validation_ms,
                pipeline_ms=pipeline_ms,
            )
            reporter.emit(
                stage=ErrorStage.ARTIFACT_WRITE,
                event="artifact_manifest_finalized",
                completed=98,
                message="Đã kiểm kê và hoàn tất manifest artifact.",
            )
            reporter.emit(
                stage=ErrorStage.PIPELINE,
                event="request_completed",
                completed=100,
                message="Lời gọi OCR đã hoàn tất.",
                terminal=True,
                status=result.status.value,
                elapsed_ms=(time.perf_counter() - started_clock) * 1000,
            )
            return result
        except PipelineStageError as exc:
            pipeline_ms = (time.perf_counter() - pipeline_started) * 1000
            failure = _ServiceFailure(
                exc.code,
                exc.stage,
                exc.public_message,
                retryable=exc.retryable,
            )
            return self._terminal_failure(
                request,
                failure,
                started_at,
                started_clock,
                reporter,
                document=document,
                workspace_handle=workspace_handle,
                source_sha256_after=self._source_sha256_after(source),
                stage_ms=StageTimings(validation=validation_ms, pipeline=pipeline_ms),
                exception=exc.__cause__ or exc,
            )
        except WorkspaceError as exc:
            pipeline_ms = (time.perf_counter() - pipeline_started) * 1000
            return self._terminal_failure(
                request,
                self._workspace_failure(exc, creating=False),
                started_at,
                started_clock,
                reporter,
                document=document,
                workspace_handle=workspace_handle,
                source_sha256_after=self._source_sha256_after(source),
                stage_ms=StageTimings(validation=validation_ms, pipeline=pipeline_ms),
                exception=exc,
            )
        except Exception as exc:
            pipeline_ms = (time.perf_counter() - pipeline_started) * 1000
            source_sha256_after = self._source_sha256_after(source)
            failure = (
                _ServiceFailure(
                    ErrorCode.INVALID_REQUEST,
                    ErrorStage.VALIDATION,
                    "Tệp PDF đầu vào đã thay đổi trong thời gian xử lý.",
                    details={"reason": "source_modified"},
                )
                if source_sha256_after != source_sha256
                else _ServiceFailure(
                    ErrorCode.INTERNAL_PIPELINE_ERROR,
                    ErrorStage.PIPELINE,
                    "Không thể hoàn tất xử lý tài liệu OCR.",
                )
            )
            return self._terminal_failure(
                request,
                failure,
                started_at,
                started_clock,
                reporter,
                document=document,
                workspace_handle=workspace_handle,
                source_sha256_after=source_sha256_after,
                stage_ms=StageTimings(validation=validation_ms, pipeline=pipeline_ms),
                exception=exc,
            )

    @staticmethod
    def _workspace_failure(exc: WorkspaceError, *, creating: bool) -> _ServiceFailure:
        if isinstance(exc, WorkspaceCollisionError):
            reason = "workspace_collision"
            retryable = False
        elif isinstance(exc, WorkspaceSecurityError):
            reason = "workspace_security"
            retryable = False
        elif isinstance(exc, WorkspaceWriteError):
            reason = "workspace_write"
            retryable = True
        else:
            reason = "workspace_failure"
            retryable = False
        return _ServiceFailure(
            ErrorCode.OUTPUT_NOT_WRITABLE if creating else ErrorCode.ARTIFACT_WRITE_FAILED,
            ErrorStage.ARTIFACT_WRITE,
            (
                "Không thể tạo workspace an toàn dưới output_root."
                if creating
                else "Không thể xác thực hoặc ghi artifact trong workspace."
            ),
            retryable=retryable,
            details={"reason": reason},
        )

    def _extract_with_stage_events(
        self,
        candidate: PdfCandidate,
        workspace: Path,
        callback: StageEventCallback,
    ) -> Mapping[str, Any]:
        method = self._orchestrator.extract_pdf_x
        try:
            parameters = inspect.signature(method).parameters.values()
            supports_stage_event = any(
                parameter.name == "stage_event" or parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in parameters
            )
        except (TypeError, ValueError):
            supports_stage_event = False
        if supports_stage_event:
            return method(candidate, workspace, stage_event=callback)
        return method(candidate, workspace)

    @staticmethod
    def _stage_progress(stage: PipelineStageEvent) -> int:
        if stage.stage == ErrorStage.RENDERING:
            return 20 if stage.event == "completed" else 12
        if stage.event == "document_completed":
            return 94
        if stage.page_number is None or not stage.total_pages:
            return 20
        span = 70.0 / max(1, stage.total_pages)
        base = 20.0 + (stage.page_number - 1) * span
        offsets = {
            (ErrorStage.DETECTION, "started"): 0.05,
            (ErrorStage.DETECTION, "completed"): 0.25,
            (ErrorStage.RECOGNITION, "started"): 0.30,
            (ErrorStage.RECOGNITION, "completed"): 0.50,
            (ErrorStage.LAYOUT, "started"): 0.55,
            (ErrorStage.LAYOUT, "completed"): 0.75,
            (ErrorStage.LAYOUT, "skipped_by_policy"): 0.75,
            (ErrorStage.ARTIFACT_WRITE, "page_completed"): 0.95,
        }
        return int(round(base + span * offsets.get((stage.stage, stage.event), 0.0)))

    @staticmethod
    def _stage_message(stage: PipelineStageEvent) -> str:
        page = f" trang {stage.page_number}" if stage.page_number is not None else ""
        messages = {
            (ErrorStage.RENDERING, "started"): "Bắt đầu render tài liệu PDF.",
            (ErrorStage.RENDERING, "completed"): "Đã render xong các trang PDF.",
            (ErrorStage.DETECTION, "started"): f"Bắt đầu phát hiện văn bản{page}.",
            (ErrorStage.DETECTION, "completed"): f"Đã phát hiện văn bản{page}.",
            (ErrorStage.RECOGNITION, "started"): f"Bắt đầu nhận dạng văn bản{page}.",
            (ErrorStage.RECOGNITION, "completed"): f"Đã nhận dạng văn bản{page}.",
            (ErrorStage.LAYOUT, "started"): f"Bắt đầu phân tích bố cục{page}.",
            (ErrorStage.LAYOUT, "completed"): f"Đã phân tích bố cục{page}.",
            (ErrorStage.LAYOUT, "skipped_by_policy"): f"Đã áp dụng chính sách bỏ qua{page}.",
            (ErrorStage.ARTIFACT_WRITE, "page_completed"): f"Đã ghi artifact{page}.",
            (ErrorStage.ARTIFACT_WRITE, "document_completed"): "Đã ghi artifact tổng hợp tài liệu.",
        }
        return messages.get((stage.stage, stage.event), "Pipeline OCR đã chuyển stage.")

    def _terminal_failure(
        self,
        request: OcrRequest,
        failure: _ServiceFailure,
        started_at: datetime,
        started_clock: float,
        reporter: ProgressReporter,
        *,
        document: DocumentIdentity | None,
        workspace_handle: WorkspaceHandle | None,
        source_sha256_after: str | None,
        stage_ms: StageTimings,
        exception: BaseException | None = None,
    ) -> OcrResult:
        result = self._failure_result(
            request,
            failure,
            started_at,
            started_clock,
            document=document,
            workspace_handle=workspace_handle,
            source_sha256_after=source_sha256_after,
            stage_ms=stage_ms,
        )
        reporter.emit(
            stage=failure.stage,
            event="request_failed",
            completed=reporter.completed,
            message="Lời gọi OCR kết thúc với lỗi đã được phân loại.",
            terminal=True,
            level=logging.ERROR,
            status=ProcessingStatus.FAILED.value,
            error_code=failure.code,
            retryable=failure.retryable,
            elapsed_ms=(time.perf_counter() - started_clock) * 1000,
            exception=exception,
        )
        return result

    @staticmethod
    def _source_sha256_after(source: Path | None) -> str | None:
        if source is None:
            return None
        try:
            return sha256_file(source)
        except OSError:
            return None

    def _validate_source(self, source_value: Path) -> tuple[Path, str, int]:
        source = source_value.resolve()
        if not source.exists():
            raise _ServiceFailure(
                ErrorCode.INPUT_NOT_FOUND,
                ErrorStage.VALIDATION,
                "Không tìm thấy tệp PDF đầu vào.",
            )
        if not source.is_file():
            raise _ServiceFailure(
                ErrorCode.INPUT_NOT_FILE,
                ErrorStage.VALIDATION,
                "Đầu vào phải là một tệp PDF.",
            )
        try:
            with source.open("rb") as stream:
                signature = stream.read(5)
        except OSError as exc:
            raise _ServiceFailure(
                ErrorCode.INVALID_PDF,
                ErrorStage.VALIDATION,
                "Không thể đọc tệp PDF đầu vào.",
            ) from exc
        if signature != b"%PDF-":
            raise _ServiceFailure(
                ErrorCode.INVALID_PDF,
                ErrorStage.VALIDATION,
                "Tệp đầu vào không có chữ ký PDF hợp lệ.",
            )
        try:
            page_count = self._page_counter(source)
        except Exception as exc:
            raise _ServiceFailure(
                ErrorCode.INVALID_PDF,
                ErrorStage.VALIDATION,
                "Tệp PDF rỗng, hỏng hoặc không thể đọc cấu trúc trang.",
            ) from exc
        if page_count < 1:
            raise _ServiceFailure(
                ErrorCode.INVALID_PDF,
                ErrorStage.VALIDATION,
                "Tệp PDF không chứa trang hợp lệ.",
            )
        try:
            source_sha256 = sha256_file(source)
        except OSError as exc:
            raise _ServiceFailure(
                ErrorCode.INVALID_PDF,
                ErrorStage.VALIDATION,
                "Không thể đọc đầy đủ tệp PDF đầu vào.",
            ) from exc
        return source, source_sha256, page_count

    def _success_result(
        self,
        request: OcrRequest,
        document: DocumentIdentity,
        workspace_handle: WorkspaceHandle,
        internal: Mapping[str, Any],
        started_at: datetime,
        started_clock: float,
        *,
        source_sha256_after: str,
        validation_ms: float,
        pipeline_ms: float,
    ) -> OcrResult:
        artifacts, artifact_lookup = self._workspace_manager.declared_artifacts(
            workspace_handle, internal.get("artifacts")
        )
        artifacts = self._workspace_manager.finalize(
            workspace_handle,
            artifacts,
            status="completed",
            source_sha256_after=source_sha256_after,
        )
        pages_raw = internal.get("pages")
        if not isinstance(pages_raw, Sequence) or isinstance(pages_raw, (str, bytes)):
            raise ValueError("orchestrator pages must be a sequence")

        page_json_by_number: dict[int, str] = {}
        rendered_by_number: dict[int, str] = {}
        page_json_ids = [
            artifact_id
            for (kind, _relative), artifact_id in artifact_lookup.items()
            if kind == "page_result"
        ]
        rendered_ids = [
            artifact_id
            for (kind, _relative), artifact_id in artifact_lookup.items()
            if kind == "rendered_page"
        ]
        for index, artifact_id in enumerate(page_json_ids, start=1):
            page_json_by_number[index] = artifact_id
        for index, artifact_id in enumerate(rendered_ids, start=1):
            rendered_by_number[index] = artifact_id

        page1_review_required = False
        fields_raw = internal.get("important_fields")
        resolutions_raw = internal.get("important_field_resolution")
        fields = fields_raw if isinstance(fields_raw, Mapping) else {}
        resolutions = resolutions_raw if isinstance(resolutions_raw, Mapping) else {}
        page1_payload: dict[str, ExtractedField] = {}
        for field_name in Page1Fields.model_fields:
            value = _optional_text(fields.get(field_name))
            resolution_raw = resolutions.get(field_name)
            resolution = resolution_raw if isinstance(resolution_raw, Mapping) else {}
            status = _field_resolution_status(value, resolution)
            if status == FieldResolutionStatus.REVIEW_REQUIRED:
                page1_review_required = True
            page1_payload[field_name] = ExtractedField(
                value=value,
                confidence=_confidence_from_resolution(resolution) if value is not None else None,
                resolution_status=status,
                source_page=1,
            )

        pages: list[PageResult] = []
        for raw_page in pages_raw:
            if not isinstance(raw_page, Mapping):
                raise ValueError("orchestrator page must be an object")
            page_number = int(raw_page["page_number"])
            raw_role = str(raw_page.get("page_role"))
            role = {
                "page1": PageRole.PAGE1,
                "page2": PageRole.PAGE2,
                "page2_skipped": PageRole.PAGE2,
                "page3_plus": PageRole.PAGE3_PLUS,
            }.get(raw_role)
            if role is None:
                raise ValueError("unknown page role")
            raw_status = str(raw_page.get("status"))
            status = {
                "completed": PageStatus.COMPLETED,
                "skipped_by_document_policy": PageStatus.SKIPPED_BY_POLICY,
                "skipped_by_policy": PageStatus.SKIPPED_BY_POLICY,
                "failed": PageStatus.FAILED,
            }.get(raw_status)
            if status is None:
                raise ValueError("unknown page status")
            review_status = ReviewStatus.NOT_REQUIRED
            if role == PageRole.PAGE3_PLUS or status == PageStatus.FAILED:
                review_status = ReviewStatus.REVIEW_REQUIRED
            elif role == PageRole.PAGE1 and page1_review_required:
                review_status = ReviewStatus.REVIEW_REQUIRED
            artifact_ids = [
                artifact_id
                for artifact_id in (
                    rendered_by_number.get(page_number),
                    page_json_by_number.get(page_number),
                )
                if artifact_id is not None
            ]
            pages.append(
                PageResult(
                    page_number=page_number,
                    role=role,
                    status=status,
                    review_status=review_status,
                    artifact_ids=artifact_ids,
                )
            )

        settings: list[SettingRecord] = []
        setting_raw = internal.get("setting_records")
        if isinstance(setting_raw, Sequence) and not isinstance(setting_raw, (str, bytes)):
            for index, raw_record in enumerate(setting_raw, start=1):
                if not isinstance(raw_record, Mapping):
                    continue
                page_number = int(raw_record["page_number"])
                evidence_id = page_json_by_number.get(page_number)
                if evidence_id is None:
                    raise ValueError("setting record lacks page evidence")
                settings.append(
                    SettingRecord(
                        record_id=f"setting-p{page_number:04d}-{index:04d}",
                        page_number=page_number,
                        parameter_code=_optional_text(raw_record.get("parameter_code")),
                        parameter_name=_optional_text(raw_record.get("parameter_name")),
                        value=_optional_text(raw_record.get("value")),
                        unit=_optional_text(raw_record.get("unit")),
                        description=_optional_text(raw_record.get("description")),
                        confidence=None,
                        review_status=ReviewStatus.REVIEW_REQUIRED,
                        evidence_artifact_id=evidence_id,
                    )
                )

        notes: list[NoteCandidate] = []
        notes_raw = internal.get("note_candidates")
        if isinstance(notes_raw, Sequence) and not isinstance(notes_raw, (str, bytes)):
            for raw_note in notes_raw:
                if not isinstance(raw_note, Mapping):
                    continue
                page_number = int(raw_note["page_number"])
                evidence_id = page_json_by_number.get(page_number)
                text = _optional_text(raw_note.get("text"))
                if evidence_id is None or text is None:
                    raise ValueError("note candidate lacks text or page evidence")
                notes.append(
                    NoteCandidate(
                        page_number=page_number,
                        text=text,
                        review_status=ReviewStatus.REVIEW_REQUIRED,
                        evidence_artifact_id=evidence_id,
                    )
                )

        warnings: list[OcrWarning] = []
        warnings_raw = internal.get("warnings")
        if isinstance(warnings_raw, Sequence) and not isinstance(warnings_raw, (str, bytes)):
            for raw_warning in warnings_raw:
                if not isinstance(raw_warning, Mapping):
                    continue
                code = _warning_code(raw_warning.get("code", "OCR_WARNING"))
                warnings.append(
                    OcrWarning(
                        code=code,
                        message=_optional_text(raw_warning.get("message")) or "Cảnh báo từ pipeline OCR.",
                        stage=ErrorStage.RENDERING if code == "PAGE_COUNT_MISMATCH" else ErrorStage.LAYOUT,
                        page_number=raw_warning.get("page_number"),
                    )
                )

        review_required = page1_review_required or bool(settings or notes) or any(
            page.review_status == ReviewStatus.REVIEW_REQUIRED for page in pages
        )
        business = BusinessResult(
            page1_fields=Page1Fields(**page1_payload),
            setting_records=settings,
            note_candidates=notes,
            evidence_artifact_ids=list(page_json_by_number.values()),
        )
        completed_at = datetime.now(timezone.utc)
        return OcrResult(
            schema_version="1.0",
            pipeline_version=self._pipeline_version,
            correlation_id=request.correlation_id,
            status=ProcessingStatus.SUCCESS_WITH_WARNINGS if warnings else ProcessingStatus.SUCCESS,
            review_status=ReviewStatus.REVIEW_REQUIRED if review_required else ReviewStatus.NOT_REQUIRED,
            document=document,
            business=business,
            pages=pages,
            warnings=warnings,
            timing=Timing(
                started_at=started_at,
                completed_at=completed_at,
                elapsed_ms=(time.perf_counter() - started_clock) * 1000,
                stage_ms=StageTimings(validation=validation_ms, pipeline=pipeline_ms),
            ),
            artifact_manifest=ArtifactManifest(
                workspace_id=request.correlation_id,
                artifacts=artifacts,
            ),
            error=None,
        )

    def _failure_result(
        self,
        request: OcrRequest,
        failure: _ServiceFailure,
        started_at: datetime,
        started_clock: float,
        *,
        document: DocumentIdentity | None,
        workspace_handle: WorkspaceHandle | None,
        source_sha256_after: str | None,
        stage_ms: StageTimings,
    ) -> OcrResult:
        artifacts: list[Artifact] = []
        if workspace_handle is not None:
            try:
                artifacts = self._workspace_manager.partial_artifacts(workspace_handle)
                artifacts = self._workspace_manager.finalize(
                    workspace_handle,
                    artifacts,
                    status="failed",
                    source_sha256_after=source_sha256_after,
                )
            except WorkspaceError:
                artifacts = []
        completed_at = datetime.now(timezone.utc)
        return OcrResult(
            schema_version="1.0",
            pipeline_version=self._pipeline_version,
            correlation_id=request.correlation_id,
            status=ProcessingStatus.FAILED,
            review_status=ReviewStatus.REVIEW_REQUIRED,
            document=document,
            business=None,
            pages=[],
            warnings=[],
            timing=Timing(
                started_at=started_at,
                completed_at=completed_at,
                elapsed_ms=(time.perf_counter() - started_clock) * 1000,
                stage_ms=stage_ms,
            ),
            artifact_manifest=ArtifactManifest(
                workspace_id=request.correlation_id,
                artifacts=artifacts,
            ),
            error=PublicError(
                code=failure.code,
                message=failure.public_message,
                stage=failure.stage,
                retryable=failure.retryable,
                details=failure.details,
            ),
        )

__all__ = ["PIPELINE_VERSION", "RelayFormOcrService"]
