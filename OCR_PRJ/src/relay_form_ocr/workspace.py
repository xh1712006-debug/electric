"""Filesystem boundary for one-call OCR workspaces and artifact manifests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Mapping, Sequence
from uuid import uuid4

from .schemas import Artifact, ArtifactManifest


WORKSPACE_SCHEMA_VERSION = "1.0"
MARKER_NAME = ".relay_form_ocr_workspace.json"
MANIFEST_NAME = "artifact_manifest.json"
_WORKSPACE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RESERVED_NAMES = {MARKER_NAME.casefold(), MANIFEST_NAME.casefold()}


class WorkspaceError(RuntimeError):
    """Base error for safe public filesystem mapping."""


class WorkspaceCollisionError(WorkspaceError):
    """A deterministic workspace path already exists."""


class WorkspaceSecurityError(WorkspaceError):
    """A path crosses a workspace boundary or reparse point."""


class WorkspaceWriteError(WorkspaceError):
    """The workspace or its metadata could not be written."""


@dataclass(frozen=True)
class WorkspaceHandle:
    output_root: Path
    path: Path
    workspace_id: str
    source_sha256: str


@dataclass(frozen=True)
class CleanupPlan:
    workspace_id: str
    relative_path: str
    file_count: int
    directory_count: int
    total_bytes: int
    deleted: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id,
            "relative_path": self.relative_path,
            "file_count": self.file_count,
            "directory_count": self.directory_count,
            "total_bytes": self.total_bytes,
            "deleted": self.deleted,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _media_type(path: Path) -> str:
    detected, _encoding = mimetypes.guess_type(path.name)
    return detected or "application/octet-stream"


def _artifact_kind(path: Path) -> str:
    if path.suffix.lower() == ".json":
        return "partial_json"
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        return "partial_image"
    return "partial_artifact"


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _path_components(path: Path) -> list[Path]:
    absolute = path.absolute()
    anchor = Path(absolute.anchor)
    components = [anchor]
    current = anchor
    for part in absolute.parts[1:]:
        current = current / part
        components.append(current)
    return components


def _assert_existing_components_are_plain(path: Path) -> None:
    for component in _path_components(path):
        if _lexists(component) and _is_reparse(component):
            raise WorkspaceSecurityError("workspace path contains a symlink or reparse point")


def _safe_internal_relative(value: object) -> PurePosixPath:
    text = str(value)
    if "\\" in text:
        raise WorkspaceSecurityError("artifact paths must use forward slashes")
    relative = PurePosixPath(text)
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise WorkspaceSecurityError("artifact path escapes the workspace")
    if relative.name.casefold() in _RESERVED_NAMES:
        raise WorkspaceSecurityError("artifact path uses a reserved workspace filename")
    return relative


def _safe_output_root(value: Path) -> Path:
    requested = Path(value).absolute()
    if any(part in {"", ".", ".."} for part in requested.parts[1:]):
        raise WorkspaceSecurityError("output_root contains an unsafe path component")
    return requested


def validate_workspace_manifest(payload: object) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise WorkspaceSecurityError("workspace manifest must be an object")
    if set(payload) != {"manifest_schema_version", "workspace_id", "status", "source", "artifacts"}:
        raise WorkspaceSecurityError("workspace manifest fields are invalid")
    workspace_id = str(payload.get("workspace_id"))
    if payload.get("manifest_schema_version") != WORKSPACE_SCHEMA_VERSION:
        raise WorkspaceSecurityError("workspace manifest schema is unsupported")
    if _WORKSPACE_ID.fullmatch(workspace_id) is None:
        raise WorkspaceSecurityError("workspace manifest ID is invalid")
    if payload.get("status") not in {"completed", "failed"}:
        raise WorkspaceSecurityError("workspace manifest status is invalid")
    source = payload.get("source")
    if not isinstance(source, Mapping) or set(source) != {"sha256_before", "sha256_after", "unchanged"}:
        raise WorkspaceSecurityError("workspace manifest source evidence is invalid")
    before = str(source.get("sha256_before"))
    after_raw = source.get("sha256_after")
    after = None if after_raw is None else str(after_raw)
    if re.fullmatch(r"[0-9a-f]{64}", before) is None:
        raise WorkspaceSecurityError("workspace manifest source hash is invalid")
    if after is not None and re.fullmatch(r"[0-9a-f]{64}", after) is None:
        raise WorkspaceSecurityError("workspace manifest final source hash is invalid")
    if source.get("unchanged") != (after == before):
        raise WorkspaceSecurityError("workspace manifest source immutability flag is inconsistent")
    raw_artifacts = payload.get("artifacts")
    if not isinstance(raw_artifacts, list):
        raise WorkspaceSecurityError("workspace manifest artifacts must be a list")
    try:
        artifacts = [Artifact.model_validate(item) for item in raw_artifacts]
        ArtifactManifest(workspace_id=workspace_id, artifacts=artifacts)
    except Exception as exc:
        raise WorkspaceSecurityError("workspace manifest artifact metadata is invalid") from exc
    if any(item.kind == "artifact_manifest" or PurePosixPath(item.relative_path).name == MANIFEST_NAME for item in artifacts):
        raise WorkspaceSecurityError("workspace manifest cannot contain a self-reference")
    return {
        "manifest_schema_version": WORKSPACE_SCHEMA_VERSION,
        "workspace_id": workspace_id,
        "status": str(payload["status"]),
        "source": {
            "sha256_before": before,
            "sha256_after": after,
            "unchanged": after == before,
        },
        "artifacts": [item.model_dump(mode="json") for item in artifacts],
    }


def load_workspace_manifest(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkspaceSecurityError("workspace manifest could not be read") from exc
    return validate_workspace_manifest(payload)


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        temporary.write_text(encoded, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    except OSError as exc:
        raise WorkspaceWriteError("workspace metadata could not be written") from exc
    finally:
        if temporary.exists():
            temporary.unlink()


class WorkspaceManager:
    """Create, audit, finalize and explicitly clean deterministic workspaces."""

    def create(self, output_root_value: Path, workspace_id: str, source_sha256: str) -> WorkspaceHandle:
        if _WORKSPACE_ID.fullmatch(workspace_id) is None:
            raise WorkspaceSecurityError("workspace_id is invalid")
        requested_root = _safe_output_root(output_root_value)
        _assert_existing_components_are_plain(requested_root)
        try:
            if _lexists(requested_root) and not requested_root.is_dir():
                raise WorkspaceWriteError("output root is not a directory")
            requested_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WorkspaceWriteError("output root could not be created") from exc
        _assert_existing_components_are_plain(requested_root)
        output_root = requested_root.resolve(strict=True)
        workspace = output_root / workspace_id
        if _lexists(workspace):
            raise WorkspaceCollisionError("workspace already exists")
        try:
            workspace.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise WorkspaceCollisionError("workspace already exists") from exc
        except OSError as exc:
            raise WorkspaceWriteError("workspace could not be created") from exc

        handle = WorkspaceHandle(output_root, workspace, workspace_id, source_sha256)
        try:
            self._write_marker(handle, state="active")
        except WorkspaceError:
            try:
                workspace.rmdir()
            except OSError:
                pass
            raise
        return handle

    def _write_marker(self, handle: WorkspaceHandle, *, state: str) -> None:
        _atomic_json(
            handle.path / MARKER_NAME,
            {
                "workspace_schema_version": WORKSPACE_SCHEMA_VERSION,
                "workspace_id": handle.workspace_id,
                "source_sha256": handle.source_sha256,
                "state": state,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _artifact_path(self, handle: WorkspaceHandle, relative: PurePosixPath) -> Path:
        lexical = handle.path.joinpath(*relative.parts)
        _assert_existing_components_are_plain(lexical)
        try:
            path = lexical.resolve(strict=True)
            path.relative_to(handle.path)
            path.relative_to(handle.output_root)
        except (OSError, ValueError) as exc:
            raise WorkspaceSecurityError("artifact escapes configured roots") from exc
        if not path.is_file() or _is_reparse(path):
            raise WorkspaceSecurityError("artifact must be a regular non-reparse file")
        return path

    def _artifact(
        self,
        handle: WorkspaceHandle,
        *,
        artifact_id: str,
        kind: str,
        relative: PurePosixPath,
    ) -> Artifact:
        path = self._artifact_path(handle, relative)
        before = path.stat()
        checksum = sha256_file(path)
        after = path.stat()
        before_fingerprint = (before.st_size, before.st_mtime_ns, getattr(before, "st_ino", None))
        after_fingerprint = (after.st_size, after.st_mtime_ns, getattr(after, "st_ino", None))
        if before_fingerprint != after_fingerprint:
            raise WorkspaceSecurityError("artifact changed while its checksum was calculated")
        public_relative = path.relative_to(handle.output_root).as_posix()
        return Artifact(
            artifact_id=artifact_id,
            kind=kind,
            relative_path=public_relative,
            media_type=_media_type(path),
            sha256=checksum,
            size_bytes=after.st_size,
        )

    def declared_artifacts(
        self,
        handle: WorkspaceHandle,
        raw_artifacts: object,
    ) -> tuple[list[Artifact], dict[tuple[str, str], str]]:
        if not isinstance(raw_artifacts, Sequence) or isinstance(raw_artifacts, (str, bytes)):
            raise WorkspaceSecurityError("orchestrator artifacts must be a sequence")
        artifacts: list[Artifact] = []
        lookup: dict[tuple[str, str], str] = {}
        seen: set[str] = set()
        for index, raw in enumerate(raw_artifacts, start=1):
            if not isinstance(raw, Mapping):
                raise WorkspaceSecurityError("orchestrator artifact must be an object")
            kind = str(raw.get("kind"))
            relative = _safe_internal_relative(raw.get("relative_path"))
            key = relative.as_posix()
            if key in seen:
                raise WorkspaceSecurityError("orchestrator artifact paths must be unique")
            seen.add(key)
            artifact_id = f"artifact-{index:04d}"
            artifacts.append(
                self._artifact(handle, artifact_id=artifact_id, kind=kind, relative=relative)
            )
            lookup[(kind, key)] = artifact_id
        return artifacts, lookup

    def partial_artifacts(self, handle: WorkspaceHandle) -> list[Artifact]:
        _assert_existing_components_are_plain(handle.path)
        try:
            entries = sorted(handle.path.rglob("*"), key=lambda item: item.as_posix())
        except OSError as exc:
            raise WorkspaceSecurityError("workspace artifacts could not be enumerated") from exc
        artifacts: list[Artifact] = []
        for path in entries:
            if _is_reparse(path):
                raise WorkspaceSecurityError("workspace contains a symlink or reparse point")
            if not path.is_file() or path.name.casefold() in _RESERVED_NAMES:
                continue
            relative = PurePosixPath(path.relative_to(handle.path).as_posix())
            artifacts.append(
                self._artifact(
                    handle,
                    artifact_id=f"artifact-{len(artifacts) + 1:04d}",
                    kind=_artifact_kind(path),
                    relative=relative,
                )
            )
        return artifacts

    def finalize(
        self,
        handle: WorkspaceHandle,
        artifacts: list[Artifact],
        *,
        status: str,
        source_sha256_after: str | None,
    ) -> list[Artifact]:
        manifest_payload = validate_workspace_manifest({
            "manifest_schema_version": WORKSPACE_SCHEMA_VERSION,
            "workspace_id": handle.workspace_id,
            "status": status,
            "source": {
                "sha256_before": handle.source_sha256,
                "sha256_after": source_sha256_after,
                "unchanged": source_sha256_after == handle.source_sha256,
            },
            "artifacts": [item.model_dump(mode="json") for item in artifacts],
        })
        _atomic_json(handle.path / MANIFEST_NAME, manifest_payload)
        manifest = self._artifact(
            handle,
            artifact_id=f"artifact-{len(artifacts) + 1:04d}",
            kind="artifact_manifest",
            relative=PurePosixPath(MANIFEST_NAME),
        )
        self._write_marker(handle, state=status)
        return [*artifacts, manifest]

    def _validated_existing(self, output_root_value: Path, workspace_id: str) -> WorkspaceHandle:
        if _WORKSPACE_ID.fullmatch(workspace_id) is None:
            raise WorkspaceSecurityError("workspace_id is invalid")
        requested_root = _safe_output_root(output_root_value)
        _assert_existing_components_are_plain(requested_root)
        if not requested_root.is_dir():
            raise WorkspaceSecurityError("output root does not exist")
        output_root = requested_root.resolve(strict=True)
        workspace = output_root / workspace_id
        _assert_existing_components_are_plain(workspace)
        if not workspace.is_dir():
            raise WorkspaceSecurityError("workspace does not exist")
        marker_path = workspace / MARKER_NAME
        if not marker_path.is_file() or _is_reparse(marker_path):
            raise WorkspaceSecurityError("workspace marker is missing or unsafe")
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise WorkspaceSecurityError("workspace marker is invalid") from exc
        expected_marker_fields = {
            "workspace_schema_version",
            "workspace_id",
            "source_sha256",
            "state",
            "updated_at",
        }
        if (
            set(marker) != expected_marker_fields
            or marker.get("workspace_schema_version") != WORKSPACE_SCHEMA_VERSION
            or marker.get("workspace_id") != workspace_id
            or marker.get("state") not in {"active", "completed", "failed"}
            or re.fullmatch(r"[0-9a-f]{64}", str(marker.get("source_sha256"))) is None
        ):
            raise WorkspaceSecurityError("workspace marker does not match the requested workspace")
        try:
            updated_at = datetime.fromisoformat(str(marker["updated_at"]))
        except ValueError as exc:
            raise WorkspaceSecurityError("workspace marker timestamp is invalid") from exc
        if updated_at.tzinfo is None:
            raise WorkspaceSecurityError("workspace marker timestamp must include timezone")
        return WorkspaceHandle(output_root, workspace, workspace_id, str(marker["source_sha256"]))

    def cleanup(self, output_root: Path, workspace_id: str, *, confirm: bool = False) -> CleanupPlan:
        handle = self._validated_existing(output_root, workspace_id)
        entries = sorted(handle.path.rglob("*"), key=lambda item: len(item.parts), reverse=True)
        files: list[Path] = []
        directories: list[Path] = []
        total_bytes = 0
        for entry in entries:
            if _is_reparse(entry):
                raise WorkspaceSecurityError("cleanup refuses symlink or reparse content")
            if entry.is_file():
                files.append(entry)
                total_bytes += entry.stat().st_size
            elif entry.is_dir():
                directories.append(entry)
            else:
                raise WorkspaceSecurityError("cleanup refuses non-regular workspace content")
        plan = CleanupPlan(
            workspace_id=workspace_id,
            relative_path=workspace_id,
            file_count=len(files),
            directory_count=len(directories) + 1,
            total_bytes=total_bytes,
            deleted=False,
        )
        if not confirm:
            return plan
        for file_path in files:
            file_path.unlink()
        for directory in directories:
            directory.rmdir()
        handle.path.rmdir()
        return CleanupPlan(**{**plan.as_dict(), "deleted": True})


__all__ = [
    "CleanupPlan",
    "MANIFEST_NAME",
    "MARKER_NAME",
    "WORKSPACE_SCHEMA_VERSION",
    "WorkspaceCollisionError",
    "WorkspaceError",
    "WorkspaceHandle",
    "WorkspaceManager",
    "WorkspaceSecurityError",
    "WorkspaceWriteError",
    "load_workspace_manifest",
    "sha256_file",
    "validate_workspace_manifest",
]
