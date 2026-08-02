import io
import json
import os
from pathlib import Path, PurePosixPath
from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.relay_form_ocr import (
    ErrorCode,
    OcrRequest,
    ProcessingStatus,
    RelayFormOcrService,
    WorkspaceCollisionError,
    WorkspaceManager,
    WorkspaceSecurityError,
)
from src.relay_form_ocr.workspace import (
    MANIFEST_NAME,
    MARKER_NAME,
    load_workspace_manifest,
    sha256_file,
)
from src.relay_form_ocr.workspace_cleanup import main as cleanup_main
from src.relay_form_ocr.workspace_visual import render_workspace_review
import src.relay_form_ocr.workspace as workspace_module


def _write_pdf(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n% workspace isolation fixture\n")
    return path


class _WorkspaceOrchestrator:
    def __init__(self, *, fail=False, mutate_source=False, declared_path=None):
        self.fail = fail
        self.mutate_source = mutate_source
        self.declared_path = declared_path

    def extract_pdf_x(self, candidate, output_dir):
        output = Path(output_dir)
        rendered = output / "rendered"
        pages = output / "pages"
        rendered.mkdir(parents=True, exist_ok=True)
        pages.mkdir(parents=True, exist_ok=True)
        image = rendered / "page-1.png"
        page_json = pages / "page_0001.json"
        extraction = output / "extraction.json"
        image.write_bytes(b"\x89PNG\r\n\x1a\nworkspace")
        page_json.write_text('{"page_number":1}', encoding="utf-8")
        extraction.write_text('{"result":"bằng chứng"}', encoding="utf-8")
        if self.mutate_source:
            Path(candidate.path).write_bytes(b"%PDF-1.4\n% source was modified\n")
        if self.fail:
            raise RuntimeError("private pipeline failure")
        declared = self.declared_path or "extraction.json"
        return {
            "important_fields": {},
            "important_field_resolution": {},
            "setting_records": [],
            "note_candidates": [],
            "warnings": [],
            "pages": [{"page_number": 1, "page_role": "page1", "status": "completed"}],
            "artifacts": [
                {"kind": "rendered_page", "relative_path": "rendered/page-1.png"},
                {"kind": "page_result", "relative_path": "pages/page_0001.json"},
                {"kind": "extraction_result", "relative_path": declared},
            ],
        }


class WorkspaceManagerTests(unittest.TestCase):
    def _create(self, root: Path, workspace_id="workspace-001"):
        source = _write_pdf(root / "source.pdf")
        manager = WorkspaceManager()
        handle = manager.create(root / "artifacts", workspace_id, sha256_file(source))
        return source, manager, handle

    def test_workspace_creation_is_deterministic_marked_and_never_reuses_existing_empty_directory(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, manager, handle = self._create(root)
            marker = json.loads((handle.path / MARKER_NAME).read_text(encoding="utf-8"))
            empty = root / "artifacts" / "empty-reserved"
            empty.mkdir()
            with self.assertRaises(WorkspaceCollisionError):
                manager.create(root / "artifacts", "workspace-001", sha256_file(source))
            with self.assertRaises(WorkspaceCollisionError):
                manager.create(root / "artifacts", "empty-reserved", sha256_file(source))
        self.assertEqual(handle.path, handle.output_root / "workspace-001")
        self.assertEqual(marker["workspace_id"], "workspace-001")
        self.assertEqual(marker["state"], "active")

    def test_tracked_workspace_manifest_fixture_validates(self):
        fixture = (
            Path(__file__).resolve().parents[1]
            / "contracts"
            / "local_api"
            / "v1"
            / "workspace_manifest.example.json"
        )
        manifest = load_workspace_manifest(fixture)
        self.assertEqual(manifest["workspace_id"], "workspace-example-001")
        self.assertTrue(manifest["source"]["unchanged"])
        self.assertEqual(len(manifest["artifacts"]), 1)

    def test_concurrent_reservation_allows_exactly_one_owner(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _write_pdf(root / "source.pdf")
            digest = sha256_file(source)

            def reserve():
                try:
                    return WorkspaceManager().create(root / "out", "same-owner", digest).workspace_id
                except WorkspaceCollisionError:
                    return "collision"

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = sorted(pool.map(lambda _index: reserve(), range(2)))
        self.assertEqual(outcomes, ["collision", "same-owner"])

    def test_declared_artifacts_have_relative_paths_size_checksum_and_physical_manifest(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _source, manager, handle = self._create(root)
            evidence = handle.path / "bằng-chứng"
            evidence.mkdir()
            first = evidence / "trang-1.json"
            first.write_text('{"nội_dung":"Việt Nam"}', encoding="utf-8")
            artifacts, lookup = manager.declared_artifacts(
                handle,
                [{"kind": "page_result", "relative_path": "bằng-chứng/trang-1.json"}],
            )
            finalized = manager.finalize(
                handle,
                artifacts,
                status="completed",
                source_sha256_after=handle.source_sha256,
            )
            manifest_path = handle.path / MANIFEST_NAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            expected_sha256 = sha256_file(first)
            expected_size = first.stat().st_size
        self.assertEqual(lookup[("page_result", "bằng-chứng/trang-1.json")], "artifact-0001")
        self.assertEqual(len(finalized), 2)
        self.assertEqual(finalized[-1].kind, "artifact_manifest")
        self.assertEqual(finalized[0].sha256, expected_sha256)
        self.assertEqual(finalized[0].size_bytes, expected_size)
        self.assertEqual(manifest["source"]["unchanged"], True)
        self.assertEqual(len(manifest["artifacts"]), 1)
        self.assertNotIn(MANIFEST_NAME, [item["relative_path"] for item in manifest["artifacts"]])

    def test_traversal_absolute_reserved_duplicate_and_invalid_workspace_ids_are_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _source, manager, handle = self._create(root)
            safe = handle.path / "safe.json"
            safe.write_text("{}", encoding="utf-8")
            for unsafe in ("../escape.json", "/absolute.json", r"C:\escape.json", MANIFEST_NAME):
                with self.subTest(unsafe=unsafe), self.assertRaises(WorkspaceSecurityError):
                    manager.declared_artifacts(handle, [{"kind": "page_result", "relative_path": unsafe}])
            with self.assertRaises(WorkspaceSecurityError):
                manager.declared_artifacts(
                    handle,
                    [
                        {"kind": "page_result", "relative_path": "safe.json"},
                        {"kind": "page_result", "relative_path": "safe.json"},
                    ],
                )
            with self.assertRaises(WorkspaceSecurityError):
                manager.create(root / "out", "../unsafe", handle.source_sha256)
            with self.assertRaises(WorkspaceSecurityError):
                manager.create(root / "safe" / ".." / "other", "unsafe-root", handle.source_sha256)

    def test_reparse_component_is_rejected_before_artifact_is_read(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _source, manager, handle = self._create(root)
            unsafe = handle.path / "unsafe"
            unsafe.mkdir()
            (unsafe / "artifact.json").write_text("{}", encoding="utf-8")
            original = workspace_module._is_reparse

            def simulated_reparse(path):
                return path.name == "unsafe" or original(path)

            with patch("src.relay_form_ocr.workspace._is_reparse", side_effect=simulated_reparse):
                with self.assertRaises(WorkspaceSecurityError):
                    manager.declared_artifacts(
                        handle,
                        [{"kind": "page_result", "relative_path": "unsafe/artifact.json"}],
                    )

    def test_real_symlink_or_windows_reparse_output_root_is_rejected_when_supported(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.mkdir()
            link = root / "linked-output"
            try:
                os.symlink(target, link, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"OS không cho tạo symlink/reparse fixture: {exc}")
            source = _write_pdf(root / "source.pdf")
            with self.assertRaises(WorkspaceSecurityError):
                WorkspaceManager().create(link, "blocked-link", sha256_file(source))

    def test_cleanup_is_dry_run_first_requires_marker_and_never_deletes_other_workspace(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _source, manager, first = self._create(root, "cleanup-first")
            _source2, _manager2, second = self._create(root, "cleanup-second")
            (first.path / "nested").mkdir()
            (first.path / "nested" / "evidence.txt").write_text("bằng chứng", encoding="utf-8")
            dry_run = manager.cleanup(first.output_root, first.workspace_id)
            self.assertFalse(dry_run.deleted)
            self.assertTrue(first.path.is_dir())
            deleted = manager.cleanup(first.output_root, first.workspace_id, confirm=True)
            self.assertTrue(deleted.deleted)
            self.assertFalse(first.path.exists())
            self.assertTrue(second.path.is_dir())

            unmanaged = first.output_root / "unmanaged"
            unmanaged.mkdir()
            with self.assertRaises(WorkspaceSecurityError):
                manager.cleanup(first.output_root, "unmanaged", confirm=True)

    def test_cleanup_cli_returns_machine_json_for_dry_run_and_confirmed_delete(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _source, _manager, handle = self._create(root, "cleanup-cli")
            args = ["--output-root", str(handle.output_root), "--correlation-id", handle.workspace_id]
            dry_stdout = io.StringIO()
            self.assertEqual(cleanup_main(args, stdout=dry_stdout), 0)
            self.assertEqual(json.loads(dry_stdout.getvalue())["status"], "dry_run")
            delete_stdout = io.StringIO()
            self.assertEqual(cleanup_main([*args, "--confirm-delete"], stdout=delete_stdout), 0)
            self.assertEqual(json.loads(delete_stdout.getvalue())["status"], "deleted")
            self.assertFalse(handle.path.exists())


class WorkspaceServiceIntegrationTests(unittest.TestCase):
    def _request(self, root: Path, correlation_id="service-workspace") -> OcrRequest:
        source = _write_pdf(root / "dữ-liệu" / "phiếu-chỉnh-định.pdf")
        return OcrRequest(
            input_pdf=source.resolve(),
            output_root=(root / "kết-quả OCR").resolve(),
            correlation_id=correlation_id,
        )

    def test_success_preserves_source_and_returns_manifest_with_verified_artifacts(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self._request(root)
            before = sha256_file(request.input_pdf)
            result = RelayFormOcrService(
                orchestrator=_WorkspaceOrchestrator(), page_counter=lambda _path: 1
            ).process_pdf(request)
            after = sha256_file(request.input_pdf)
            manifest_artifact = next(item for item in result.artifact_manifest.artifacts if item.kind == "artifact_manifest")
            manifest_path = request.output_root / Path(str(manifest_artifact.relative_path))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            audited = [
                (
                    item.size_bytes == (request.output_root / Path(str(item.relative_path))).stat().st_size,
                    item.sha256 == sha256_file(request.output_root / Path(str(item.relative_path))),
                )
                for item in result.artifact_manifest.artifacts
            ]
        self.assertEqual(result.status, ProcessingStatus.SUCCESS)
        self.assertEqual(before, after)
        self.assertEqual(result.document.source_name, "phiếu-chỉnh-định.pdf")
        self.assertEqual(manifest["source"]["sha256_before"], before)
        self.assertEqual(manifest["source"]["sha256_after"], after)
        self.assertTrue(manifest["source"]["unchanged"])
        self.assertTrue(all(size and digest for size, digest in audited))
        self.assertTrue(all(item.relative_path.startswith("service-workspace/") for item in result.artifact_manifest.artifacts))

    def test_failure_preserves_source_and_finalizes_partial_manifest(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self._request(root, "failure-workspace")
            before = sha256_file(request.input_pdf)
            result = RelayFormOcrService(
                orchestrator=_WorkspaceOrchestrator(fail=True), page_counter=lambda _path: 1
            ).process_pdf(request)
            after = sha256_file(request.input_pdf)
            manifest_artifact = next(item for item in result.artifact_manifest.artifacts if item.kind == "artifact_manifest")
            manifest = json.loads(
                (request.output_root / Path(str(manifest_artifact.relative_path))).read_text(encoding="utf-8")
            )
        self.assertEqual(result.status, ProcessingStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INTERNAL_PIPELINE_ERROR)
        self.assertEqual(before, after)
        self.assertEqual(manifest["status"], "failed")
        self.assertTrue(manifest["source"]["unchanged"])

    def test_source_modification_is_detected_and_recorded_as_failed(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self._request(root, "source-modified")
            result = RelayFormOcrService(
                orchestrator=_WorkspaceOrchestrator(mutate_source=True), page_counter=lambda _path: 1
            ).process_pdf(request)
            manifest_artifact = next(item for item in result.artifact_manifest.artifacts if item.kind == "artifact_manifest")
            manifest = json.loads(
                (request.output_root / Path(str(manifest_artifact.relative_path))).read_text(encoding="utf-8")
            )
        self.assertEqual(result.status, ProcessingStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INVALID_REQUEST)
        self.assertFalse(manifest["source"]["unchanged"])
        self.assertNotEqual(manifest["source"]["sha256_before"], manifest["source"]["sha256_after"])

    def test_traversal_artifact_becomes_safe_artifact_write_failure(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self._request(root, "artifact-traversal")
            result = RelayFormOcrService(
                orchestrator=_WorkspaceOrchestrator(declared_path="../escape.json"),
                page_counter=lambda _path: 1,
            ).process_pdf(request)
        self.assertEqual(result.status, ProcessingStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.ARTIFACT_WRITE_FAILED)
        self.assertNotIn(str(root), result.model_dump_json())

    def test_two_correlation_ids_are_isolated_and_same_id_collision_does_not_overwrite(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_request = self._request(root, "isolated-first")
            second_request = OcrRequest(
                input_pdf=first_request.input_pdf,
                output_root=first_request.output_root,
                correlation_id="isolated-second",
            )
            service = RelayFormOcrService(orchestrator=_WorkspaceOrchestrator(), page_counter=lambda _path: 1)
            first = service.process_pdf(first_request)
            second = service.process_pdf(second_request)
            marker = first_request.output_root / "isolated-first" / MARKER_NAME
            marker_before = marker.read_text(encoding="utf-8")
            collision = service.process_pdf(first_request)
            marker_after = marker.read_text(encoding="utf-8")
        self.assertEqual((first.status, second.status), (ProcessingStatus.SUCCESS, ProcessingStatus.SUCCESS))
        self.assertEqual(collision.error.code, ErrorCode.OUTPUT_NOT_WRITABLE)
        self.assertEqual(marker_before, marker_after)
        self.assertNotEqual(
            first.artifact_manifest.artifacts[0].relative_path.split("/")[0],
            second.artifact_manifest.artifacts[0].relative_path.split("/")[0],
        )

    def test_visual_report_uses_accented_vietnamese_and_covers_security_cleanup_and_hashes(self):
        manifest = {
            "manifest_schema_version": "1.0",
            "workspace_id": "truc-quan-001",
            "status": "completed",
            "source": {"sha256_before": "a" * 64, "sha256_after": "a" * 64, "unchanged": True},
            "artifacts": [
                {
                    "artifact_id": "artifact-0001",
                    "kind": "page_result",
                    "relative_path": "truc-quan-001/pages/trang-1.json",
                    "size_bytes": 123,
                    "sha256": "b" * 64,
                }
            ],
        }
        with TemporaryDirectory() as temporary:
            output = render_workspace_review(manifest, Path(temporary) / "workspace_review.html")
            html = output.read_text(encoding="utf-8")
        self.assertIn('<html lang="vi">', html)
        self.assertIn("Kiểm thử trực quan workspace và artifact isolation", html)
        self.assertIn("Source PDF", html)
        self.assertIn("Không thay đổi", html)
        self.assertIn("Hàng rào an toàn", html)
        self.assertIn("symlink", html)
        self.assertIn("cleanup chưa xác nhận", html)
        self.assertIn("trang-1.json", html)


if __name__ == "__main__":
    unittest.main()
