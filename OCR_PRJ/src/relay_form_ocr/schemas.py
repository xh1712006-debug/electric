"""Strict Pydantic v2 models for the local one-PDF public contract v1."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path, PurePosixPath
import re
from typing import Annotated, Any, Literal, Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)


SCHEMA_VERSION = "1.0"
CORRELATION_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
PIPELINE_VERSION_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$"
SAFE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$"

CorrelationId = Annotated[str, StringConstraints(pattern=CORRELATION_ID_PATTERN)]
Sha256 = Annotated[str, StringConstraints(pattern=SHA256_PATTERN)]
SafeId = Annotated[str, StringConstraints(pattern=SAFE_ID_PATTERN)]
NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
NonNegativeFloat = Annotated[float, Field(ge=0)]
PositivePage = Annotated[int, Field(ge=1)]


class PublicContractModel(BaseModel):
    """Base policy shared by every public model."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class ProcessingStatus(str, Enum):
    SUCCESS = "success"
    SUCCESS_WITH_WARNINGS = "success_with_warnings"
    FAILED = "failed"


class ReviewStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    REVIEW_REQUIRED = "review_required"


class PageRole(str, Enum):
    PAGE1 = "page1"
    PAGE2 = "page2"
    PAGE3_PLUS = "page3_plus"


class PageStatus(str, Enum):
    COMPLETED = "completed"
    SKIPPED_BY_POLICY = "skipped_by_policy"
    FAILED = "failed"


class FieldResolutionStatus(str, Enum):
    AUTO_SELECTED = "auto_selected"
    PRESERVED_EXISTING = "preserved_existing"
    REVIEW_REQUIRED = "review_required"
    NOT_AVAILABLE = "not_available"


class ConfidenceLabel(str, Enum):
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class ErrorStage(str, Enum):
    VALIDATION = "validation"
    RENDERING = "rendering"
    DETECTION = "detection"
    RECOGNITION = "recognition"
    LAYOUT = "layout"
    ARTIFACT_WRITE = "artifact_write"
    PIPELINE = "pipeline"


class ErrorCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    INPUT_NOT_FOUND = "INPUT_NOT_FOUND"
    INPUT_NOT_FILE = "INPUT_NOT_FILE"
    UNSUPPORTED_INPUT_KIND = "UNSUPPORTED_INPUT_KIND"
    INVALID_PDF = "INVALID_PDF"
    OUTPUT_NOT_WRITABLE = "OUTPUT_NOT_WRITABLE"
    PDF_RENDER_FAILED = "PDF_RENDER_FAILED"
    DETECTION_FAILED = "DETECTION_FAILED"
    RECOGNITION_FAILED = "RECOGNITION_FAILED"
    LAYOUT_FAILED = "LAYOUT_FAILED"
    ARTIFACT_WRITE_FAILED = "ARTIFACT_WRITE_FAILED"
    INTERNAL_PIPELINE_ERROR = "INTERNAL_PIPELINE_ERROR"


class OcrRequest(PublicContractModel):
    """Request for exactly one local PDF_x."""

    input_pdf: Path
    output_root: Path
    correlation_id: CorrelationId

    @field_validator("input_pdf")
    @classmethod
    def validate_input_pdf(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("input_pdf must be an absolute path")
        if value.suffix.lower() != ".pdf":
            raise ValueError("input_pdf must have a .pdf extension")
        return value

    @field_validator("output_root")
    @classmethod
    def validate_output_root(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("output_root must be an absolute path")
        return value


class DocumentIdentity(PublicContractModel):
    document_id: SafeId
    source_name: NonEmptyText
    source_sha256: Sha256
    page_count: PositivePage

    @field_validator("source_name")
    @classmethod
    def source_name_is_a_basename(cls, value: str) -> str:
        if value != Path(value).name or "/" in value or "\\" in value:
            raise ValueError("source_name must be a basename without path components")
        return value


class Confidence(PublicContractModel):
    level: Annotated[int, Field(ge=1, le=5)]
    label: ConfidenceLabel
    score: Annotated[float, Field(ge=0, le=100)]

    @model_validator(mode="after")
    def level_matches_label(self) -> "Confidence":
        expected = {
            1: ConfidenceLabel.VERY_LOW,
            2: ConfidenceLabel.LOW,
            3: ConfidenceLabel.MEDIUM,
            4: ConfidenceLabel.HIGH,
            5: ConfidenceLabel.VERY_HIGH,
        }[self.level]
        if self.label != expected:
            raise ValueError(f"confidence level {self.level} must use label {expected.value}")
        return self


class ExtractedField(PublicContractModel):
    value: str | None
    confidence: Confidence | None
    resolution_status: FieldResolutionStatus
    source_page: PositivePage | None

    @model_validator(mode="after")
    def unavailable_fields_have_no_value_or_confidence(self) -> "ExtractedField":
        if self.resolution_status == FieldResolutionStatus.NOT_AVAILABLE:
            if self.value is not None or self.confidence is not None:
                raise ValueError("not_available fields must have null value and confidence")
        return self


class Page1Fields(PublicContractModel):
    """The fixed 25-field Page-1 public schema."""

    ticket_number: ExtractedField
    page_reference: ExtractedField
    station: ExtractedField
    protected_equipment: ExtractedField
    protection_type: ExtractedField
    circuit_breaker: ExtractedField
    relay_name: ExtractedField
    relay_version: ExtractedField
    wiring_diagram: ExtractedField
    relay_serial: ExtractedField
    current_transformer_ratio: ExtractedField
    manufacturer: ExtractedField
    voltage_transformer_ratio: ExtractedField
    installation_year: ExtractedField
    single_line_drawing: ExtractedField
    software: ExtractedField
    protection_cabinet: ExtractedField
    protection_circuit: ExtractedField
    issuance_purpose: ExtractedField
    dispatch_center_request: ExtractedField
    software_version: ExtractedField
    page_number: ExtractedField
    total_pages: ExtractedField
    form_title: ExtractedField
    protection_principle_heading: ExtractedField


class SettingRecord(PublicContractModel):
    record_id: SafeId
    page_number: PositivePage
    parameter_code: str | None
    parameter_name: str | None
    value: str | None
    unit: str | None
    description: str | None
    confidence: Confidence | None
    review_status: Literal[ReviewStatus.REVIEW_REQUIRED]
    evidence_artifact_id: SafeId


class NoteCandidate(PublicContractModel):
    page_number: PositivePage
    text: NonEmptyText
    review_status: Literal[ReviewStatus.REVIEW_REQUIRED]
    evidence_artifact_id: SafeId


class BusinessResult(PublicContractModel):
    page1_fields: Page1Fields
    setting_records: list[SettingRecord]
    note_candidates: list[NoteCandidate]
    evidence_artifact_ids: list[SafeId]

    @field_validator("evidence_artifact_ids")
    @classmethod
    def unique_evidence_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_artifact_ids must be unique")
        return value


class PageResult(PublicContractModel):
    page_number: PositivePage
    role: PageRole
    status: PageStatus
    review_status: ReviewStatus
    artifact_ids: list[SafeId]

    @field_validator("artifact_ids")
    @classmethod
    def unique_artifact_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("page artifact_ids must be unique")
        return value

    @model_validator(mode="after")
    def role_matches_page_and_policy(self) -> "PageResult":
        if self.role == PageRole.PAGE1 and self.page_number != 1:
            raise ValueError("page1 role requires page_number=1")
        if self.role == PageRole.PAGE2:
            if self.page_number != 2 or self.status != PageStatus.SKIPPED_BY_POLICY:
                raise ValueError("page2 role requires page_number=2 and skipped_by_policy")
        if self.role == PageRole.PAGE3_PLUS:
            if self.page_number < 3:
                raise ValueError("page3_plus role requires page_number>=3")
            if self.status == PageStatus.COMPLETED and self.review_status != ReviewStatus.REVIEW_REQUIRED:
                raise ValueError("completed page3_plus results require review")
        return self


class OcrWarning(PublicContractModel):
    code: Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{1,127}$")]
    message: NonEmptyText
    stage: ErrorStage
    page_number: PositivePage | None = None


class StageTimings(PublicContractModel):
    validation: NonNegativeFloat | None = None
    rendering: NonNegativeFloat | None = None
    detection: NonNegativeFloat | None = None
    recognition: NonNegativeFloat | None = None
    layout: NonNegativeFloat | None = None
    artifact_write: NonNegativeFloat | None = None
    pipeline: NonNegativeFloat | None = None


class Timing(PublicContractModel):
    started_at: datetime
    completed_at: datetime
    elapsed_ms: NonNegativeFloat
    stage_ms: StageTimings

    @model_validator(mode="after")
    def timestamps_are_aware_and_ordered(self) -> "Timing":
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise ValueError("timing timestamps must include a timezone")
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        return self


class Artifact(PublicContractModel):
    artifact_id: SafeId
    kind: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,127}$")]
    relative_path: NonEmptyText
    media_type: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+$")]
    sha256: Sha256
    size_bytes: Annotated[int, Field(ge=0)]

    @field_validator("relative_path")
    @classmethod
    def relative_path_is_safe_and_portable(cls, value: str) -> str:
        if "\\" in value:
            raise ValueError("relative_path must use forward slashes")
        path = PurePosixPath(value)
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("relative_path must stay below output_root")
        return value


class ArtifactManifest(PublicContractModel):
    workspace_id: SafeId
    artifacts: list[Artifact]

    @model_validator(mode="after")
    def artifact_ids_and_paths_are_unique(self) -> "ArtifactManifest":
        ids = [item.artifact_id for item in self.artifacts]
        paths = [item.relative_path for item in self.artifacts]
        if len(ids) != len(set(ids)):
            raise ValueError("artifact_id values must be unique")
        if len(paths) != len(set(paths)):
            raise ValueError("artifact relative_path values must be unique")
        return self


class PublicError(PublicContractModel):
    code: ErrorCode
    message: NonEmptyText
    stage: ErrorStage
    retryable: bool
    details: JsonValue | None


_FORBIDDEN_DETAIL_KEYS = {
    "exception",
    "image_path",
    "input_pdf",
    "model_object",
    "output_root",
    "raw_ocr",
    "stack_trace",
    "stacktrace",
    "temporary_path",
    "traceback",
}
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")


def _validate_public_json(value: Any, *, key: str | None = None) -> None:
    if key is not None and key.casefold() in _FORBIDDEN_DETAIL_KEYS:
        raise ValueError(f"public payload contains forbidden key: {key}")
    if isinstance(value, Mapping):
        for child_key, child in value.items():
            _validate_public_json(child, key=str(child_key))
    elif isinstance(value, list):
        for child in value:
            _validate_public_json(child)
    elif isinstance(value, str):
        if value.startswith(("/", "\\\\")) or _WINDOWS_ABSOLUTE.match(value):
            raise ValueError("public result must not contain absolute server paths")


class OcrResult(PublicContractModel):
    """One terminal success or failure envelope for schema version 1.0."""

    schema_version: Literal[SCHEMA_VERSION]
    pipeline_version: Annotated[str, StringConstraints(pattern=PIPELINE_VERSION_PATTERN)]
    correlation_id: CorrelationId
    status: ProcessingStatus
    review_status: ReviewStatus
    document: DocumentIdentity | None
    business: BusinessResult | None
    pages: list[PageResult]
    warnings: list[OcrWarning]
    timing: Timing
    artifact_manifest: ArtifactManifest
    error: PublicError | None

    @model_validator(mode="after")
    def terminal_invariants_and_references(self) -> "OcrResult":
        if self.status == ProcessingStatus.SUCCESS:
            if self.warnings:
                raise ValueError("success results must not contain warnings")
            self._validate_success_payload()
        elif self.status == ProcessingStatus.SUCCESS_WITH_WARNINGS:
            if not self.warnings:
                raise ValueError("success_with_warnings requires at least one warning")
            self._validate_success_payload()
        else:
            if self.business is not None:
                raise ValueError("failed results must have business=null")
            if self.error is None:
                raise ValueError("failed results require an error")
            if self.review_status != ReviewStatus.REVIEW_REQUIRED:
                raise ValueError("failed results require review_status=review_required")

        page_numbers = [page.page_number for page in self.pages]
        if len(page_numbers) != len(set(page_numbers)):
            raise ValueError("page numbers must be unique")
        if self.document is not None and self.status != ProcessingStatus.FAILED:
            if page_numbers != list(range(1, self.document.page_count + 1)):
                raise ValueError("successful page results must cover the document contiguously")

        manifest_ids = {item.artifact_id for item in self.artifact_manifest.artifacts}
        references = {artifact_id for page in self.pages for artifact_id in page.artifact_ids}
        if self.business is not None:
            references.update(self.business.evidence_artifact_ids)
            references.update(item.evidence_artifact_id for item in self.business.setting_records)
            references.update(item.evidence_artifact_id for item in self.business.note_candidates)
        missing = references - manifest_ids
        if missing:
            raise ValueError(f"artifact references are missing from manifest: {sorted(missing)}")

        _validate_public_json(self.model_dump(mode="json"))
        return self

    def _validate_success_payload(self) -> None:
        if self.document is None or self.business is None:
            raise ValueError("successful results require document and business")
        if self.error is not None:
            raise ValueError("successful results must have error=null")
        page1_values = (
            getattr(self.business.page1_fields, field_name)
            for field_name in self.business.page1_fields.__class__.model_fields
        )
        nested_review = any(
            field.resolution_status == FieldResolutionStatus.REVIEW_REQUIRED
            for field in page1_values
        ) or bool(self.business.setting_records or self.business.note_candidates) or any(
            page.review_status == ReviewStatus.REVIEW_REQUIRED for page in self.pages
        )
        if nested_review and self.review_status != ReviewStatus.REVIEW_REQUIRED:
            raise ValueError("nested review evidence requires review_status=review_required")


PUBLIC_MODEL_TYPES = (
    OcrRequest,
    OcrResult,
    DocumentIdentity,
    BusinessResult,
    Page1Fields,
    ExtractedField,
    Confidence,
    SettingRecord,
    NoteCandidate,
    PageResult,
    OcrWarning,
    Timing,
    StageTimings,
    ArtifactManifest,
    Artifact,
    PublicError,
)


__all__ = [
    "Artifact",
    "ArtifactManifest",
    "BusinessResult",
    "Confidence",
    "ConfidenceLabel",
    "DocumentIdentity",
    "ErrorCode",
    "ErrorStage",
    "ExtractedField",
    "FieldResolutionStatus",
    "NoteCandidate",
    "OcrRequest",
    "OcrResult",
    "OcrWarning",
    "Page1Fields",
    "PageResult",
    "PageRole",
    "PageStatus",
    "ProcessingStatus",
    "PublicError",
    "ReviewStatus",
    "SCHEMA_VERSION",
    "SettingRecord",
    "StageTimings",
    "Timing",
]
