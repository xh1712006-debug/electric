"""Structured progress and privacy-safe logging for the local OCR service."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from typing import Callable, TextIO

from .schemas import ErrorCode, ErrorStage


PROGRESS_TOTAL = 100


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """One synchronous, caller-facing progress notification."""

    correlation_id: str
    sequence: int
    stage: ErrorStage
    event: str
    completed: int
    total: int
    percent: float
    message: str
    page_number: int | None = None
    terminal: bool = False

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["stage"] = self.stage.value
        return payload


ServiceProgressCallback = Callable[[ProgressEvent], None]


@dataclass(frozen=True, slots=True)
class PipelineStageEvent:
    """Internal stage signal emitted by the production orchestrator."""

    stage: ErrorStage
    event: str
    page_number: int | None = None
    total_pages: int | None = None


StageEventCallback = Callable[[PipelineStageEvent], None]


class PipelineStageError(RuntimeError):
    """Internal exception carrying stable public stage/error semantics."""

    def __init__(
        self,
        code: ErrorCode,
        stage: ErrorStage,
        public_message: str,
        *,
        retryable: bool,
    ) -> None:
        super().__init__(public_message)
        self.code = code
        self.stage = stage
        self.public_message = public_message
        self.retryable = retryable


class JsonLineFormatter(logging.Formatter):
    """Format only the approved structured fields as one ASCII-safe JSON line."""

    _FIELDS = (
        "correlation_id",
        "stage",
        "event",
        "sequence",
        "completed",
        "total",
        "percent",
        "page_number",
        "terminal",
        "status",
        "error_code",
        "retryable",
        "elapsed_ms",
        "exception_type",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
        }
        for name in self._FIELDS:
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        if record.exc_info:
            payload["exception_trace"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def stream_logger(stream: TextIO, *, name: str) -> logging.Logger:
    """Create an isolated JSON-lines logger for one CLI invocation."""

    logger = logging.Logger(name, level=logging.INFO)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


class ProgressReporter:
    """Enforce monotonic progress and isolate optional callback failures."""

    def __init__(
        self,
        correlation_id: str,
        *,
        callback: ServiceProgressCallback | None,
        logger: logging.Logger,
        include_exception_trace: bool = False,
    ) -> None:
        self.correlation_id = correlation_id
        self._callback = callback
        self._logger = logger
        self._include_exception_trace = include_exception_trace
        self._completed = 0
        self._sequence = 0

    @property
    def completed(self) -> int:
        return self._completed

    def emit(
        self,
        *,
        stage: ErrorStage,
        event: str,
        completed: int,
        message: str,
        page_number: int | None = None,
        terminal: bool = False,
        level: int = logging.INFO,
        status: str | None = None,
        error_code: ErrorCode | None = None,
        retryable: bool | None = None,
        elapsed_ms: float | None = None,
        exception: BaseException | None = None,
    ) -> ProgressEvent:
        bounded = max(self._completed, min(PROGRESS_TOTAL, max(0, int(completed))))
        self._completed = bounded
        self._sequence += 1
        progress = ProgressEvent(
            correlation_id=self.correlation_id,
            sequence=self._sequence,
            stage=stage,
            event=event,
            completed=bounded,
            total=PROGRESS_TOTAL,
            percent=round((bounded / PROGRESS_TOTAL) * 100.0, 2),
            message=message,
            page_number=page_number,
            terminal=terminal,
        )
        extra: dict[str, object] = {
            "correlation_id": self.correlation_id,
            "stage": stage.value,
            "event": event,
            "sequence": progress.sequence,
            "completed": progress.completed,
            "total": progress.total,
            "percent": progress.percent,
            "terminal": terminal,
        }
        if page_number is not None:
            extra["page_number"] = page_number
        if status is not None:
            extra["status"] = status
        if error_code is not None:
            extra["error_code"] = error_code.value
        if retryable is not None:
            extra["retryable"] = retryable
        if elapsed_ms is not None:
            extra["elapsed_ms"] = round(max(0.0, elapsed_ms), 2)
        if exception is not None:
            extra["exception_type"] = type(exception).__name__
        self._logger.log(
            level,
            event,
            extra=extra,
            exc_info=exception if self._include_exception_trace else None,
        )

        callback = self._callback
        if callback is not None:
            try:
                callback(progress)
            except Exception as exc:
                self._callback = None
                self._logger.warning(
                    "progress_callback_failed",
                    extra={
                        "correlation_id": self.correlation_id,
                        "stage": stage.value,
                        "event": "progress_callback_failed",
                        "sequence": progress.sequence,
                        "completed": progress.completed,
                        "total": progress.total,
                        "percent": progress.percent,
                        "terminal": False,
                        "exception_type": type(exc).__name__,
                    },
                    exc_info=exc if self._include_exception_trace else None,
                )
        return progress


__all__ = [
    "JsonLineFormatter",
    "PROGRESS_TOTAL",
    "PipelineStageError",
    "PipelineStageEvent",
    "ProgressEvent",
    "ProgressReporter",
    "ServiceProgressCallback",
    "StageEventCallback",
    "stream_logger",
]
