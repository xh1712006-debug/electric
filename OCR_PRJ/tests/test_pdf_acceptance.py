import ast
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from examples.local_consumer.acceptance_runner import (
    AcceptanceConfigurationError,
    AcceptanceEvidenceError,
    build_execution_plan,
    load_corpus,
    run_acceptance_suite,
    verify_acceptance_evidence,
)
from examples.local_consumer.acceptance_visual import render_acceptance_review
from src.relay_form_ocr import RelayFormOcrService


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "contracts" / "local_api" / "v1" / "acceptance_corpus.json"
RUNNER = ROOT / "examples" / "local_consumer" / "acceptance_runner.py"
PYTHON_EXE = ROOT / "lab" / "structure_analysis_2" / ".venv" / "Scripts" / "python.exe"


class _AcceptanceOrchestrator:
    def __init__(self):
        self.calls = 0

    def extract_pdf_x(self, candidate, output_dir):
        self.calls += 1
        output = Path(output_dir)
        rendered = output / "rendered"
        pages = output / "pages"
        rendered.mkdir(parents=True, exist_ok=True)
        pages.mkdir(parents=True, exist_ok=True)
        image = rendered / "page-1.png"
        page_json = pages / "page_0001.json"
        extraction = output / "extraction.json"
        image.write_bytes(b"\x89PNG\r\n\x1a\nacceptance")
        page_json.write_text('{"page_number":1}', encoding="utf-8")
        extraction.write_text('{"result":"ổn định"}', encoding="utf-8")
        return {
            "important_fields": {"station": "Trạm kiểm thử"},
            "important_field_resolution": {},
            "setting_records": [],
            "note_candidates": [],
            "warnings": [],
            "pages": [{"page_number": 1, "page_role": "page1", "status": "completed"}],
            "artifacts": [
                {"kind": "rendered_page", "relative_path": "rendered/page-1.png"},
                {"kind": "page_result", "relative_path": "pages/page_0001.json"},
                {"kind": "extraction_result", "relative_path": "extraction.json"},
            ],
        }


def _page_counter(path):
    if path.name == "corrupt.pdf":
        raise ValueError("corrupt")
    return 1


def _write_pdf(path: Path, label: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"%PDF-1.4\n% {label}\n".encode("utf-8"))
    return path


def _write_corpus(path: Path) -> Path:
    payload = {
        "acceptance_schema_version": "1.0",
        "suite_id": "test-acceptance",
        "description": "Corpus kiểm thử acceptance.",
        "required_layout_families": ["family-a", "family-b"],
        "cases": [
            {
                "case_id": "case-a",
                "layout_family": "family-a",
                "display_name": "Phiếu A chạy lặp",
                "input_pdf": "A.pdf",
                "repeat": 2,
            },
            {
                "case_id": "case-b",
                "layout_family": "family-b",
                "display_name": "Phiếu B",
                "input_pdf": "B.pdf",
                "repeat": 1,
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class PdfAcceptanceTests(unittest.TestCase):
    def _run_fixture(self, root: Path):
        corpus_path = _write_corpus(root / "corpus.json")
        input_root = root / "dữ-liệu"
        _write_pdf(input_root / "A.pdf", "a")
        _write_pdf(input_root / "B.pdf", "b")
        corpus = load_corpus(corpus_path)
        orchestrator = _AcceptanceOrchestrator()
        service = RelayFormOcrService(orchestrator=orchestrator, page_counter=_page_counter)
        manifest, manifest_path = run_acceptance_suite(
            corpus,
            input_root=input_root,
            output_root=root / "kết-quả",
            run_id="acceptance-test",
            service=service,
            runtime={
                "python_version": "3.12.0",
                "python_implementation": "CPython",
                "platform": "Windows-test",
                "machine": "AMD64",
                "requested_device": "cpu",
                "packages": {"torch": "2.0", "paddlepaddle": "3.0"},
                "gpu": None,
            },
        )
        return corpus, orchestrator, manifest, manifest_path

    def test_default_corpus_covers_eight_families_and_repeatability(self):
        corpus = load_corpus(DEFAULT_CORPUS)
        plan = build_execution_plan(corpus, "immediate-009")
        self.assertEqual(len(corpus.cases), 8)
        self.assertEqual(len(corpus.required_layout_families), 8)
        self.assertEqual(len(plan), 10)
        self.assertEqual(sum(item["expected"] == "processed" for item in plan), 9)
        self.assertEqual(plan[-1]["expected"], "invalid_pdf")

    def test_corpus_rejects_escape_duplicate_and_uncovered_family(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = json.loads(DEFAULT_CORPUS.read_text(encoding="utf-8"))
            mutations = []
            escaped = json.loads(json.dumps(source))
            escaped["cases"][0]["input_pdf"] = "../secret.pdf"
            mutations.append(escaped)
            duplicate = json.loads(json.dumps(source))
            duplicate["cases"][1]["case_id"] = duplicate["cases"][0]["case_id"]
            mutations.append(duplicate)
            uncovered = json.loads(json.dumps(source))
            uncovered["required_layout_families"].append("new-family")
            mutations.append(uncovered)
            for index, payload in enumerate(mutations):
                path = root / f"bad-{index}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(index=index), self.assertRaises(AcceptanceConfigurationError):
                    load_corpus(path)

    def test_public_service_forwards_gpu_flag_to_default_orchestrator(self):
        with patch("src.relay_form_ocr.service.DocumentOcrOrchestrator") as orchestrator:
            RelayFormOcrService(use_gpu=True)
        orchestrator.assert_called_once_with(use_gpu=True)

    def test_runner_uses_only_public_project_api(self):
        tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
        project_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src"):
                project_imports.append(node.module)
            elif isinstance(node, ast.Import):
                project_imports.extend(alias.name for alias in node.names if alias.name.startswith("src"))
        self.assertEqual(project_imports, ["src.relay_form_ocr"])
        source = RUNNER.read_text(encoding="utf-8")
        self.assertNotIn("src.relay_form_ocr.service", source)
        self.assertNotIn("src.relay_form_ocr.workspace", source)
        self.assertNotIn("src.debug_ui", source)

    def test_full_fixture_passes_all_executions_repeatability_and_failure_contract(self):
        with TemporaryDirectory() as temporary:
            _corpus, orchestrator, manifest, manifest_path = self._run_fixture(Path(temporary))
            persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(orchestrator.calls, 3)
        self.assertEqual(manifest["state"], "passed")
        self.assertTrue(manifest["summary"]["acceptance_passed"])
        self.assertEqual(manifest["summary"]["completed_execution_count"], 4)
        self.assertEqual(manifest["summary"]["covered_family_count"], 2)
        self.assertTrue(manifest["summary"]["repeatability_passed"])
        self.assertTrue(manifest["summary"]["workspace_collision_free"])
        invalid = next(item for item in manifest["executions"] if item["expected"] == "invalid_pdf")
        self.assertEqual(invalid["public_error"]["code"], "INVALID_PDF")
        self.assertEqual(invalid["public_error"]["stage"], "validation")
        self.assertFalse(invalid["public_error"]["retryable"])
        self.assertTrue(all(item["source_unchanged"] for item in manifest["executions"]))
        self.assertEqual(persisted["summary"], manifest["summary"])

    def test_compact_and_full_evidence_verification(self):
        with TemporaryDirectory() as temporary:
            _corpus, _orchestrator, _manifest, manifest_path = self._run_fixture(Path(temporary))
            compact = verify_acceptance_evidence(manifest_path)
            full = verify_acceptance_evidence(manifest_path, full_artifact_audit=True)
        self.assertEqual(compact["verified_execution_count"], 4)
        self.assertFalse(compact["full_artifact_audit"])
        self.assertTrue(full["full_artifact_audit"])
        self.assertTrue(full["acceptance_passed"])

    def test_tampered_evidence_is_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _corpus, _orchestrator, manifest, manifest_path = self._run_fixture(root)
            result = manifest_path.parent / Path(manifest["executions"][0]["result_file"])
            result.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(AcceptanceEvidenceError, "checksum mismatch"):
                verify_acceptance_evidence(manifest_path)

    def test_resume_skips_every_persisted_terminal_execution(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            corpus, _orchestrator, manifest, _manifest_path = self._run_fixture(root)
            new_orchestrator = _AcceptanceOrchestrator()
            resumed, _ = run_acceptance_suite(
                corpus,
                input_root=root / "dữ-liệu",
                output_root=root / "kết-quả",
                run_id="acceptance-test",
                resume=True,
                service=RelayFormOcrService(
                    orchestrator=new_orchestrator, page_counter=_page_counter
                ),
            )
        self.assertEqual(new_orchestrator.calls, 0)
        self.assertEqual(resumed["executions"], manifest["executions"])
        self.assertEqual(resumed["state"], "passed")

    def test_visual_report_is_vietnamese_and_contains_no_absolute_source_path(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _corpus, _orchestrator, manifest, _manifest_path = self._run_fixture(root)
            output = render_acceptance_review(manifest, root / "acceptance_review.html")
            html = output.read_text(encoding="utf-8")
        self.assertIn('<html lang="vi">', html)
        self.assertIn("Acceptance từng PDF", html)
        self.assertIn("Độ phủ layout family", html)
        self.assertIn("bắt buộc duyệt thủ công", html)
        self.assertIn("không phải phép đo độ chính xác OCR", html)
        self.assertIn("PDF hỏng", html)
        self.assertNotIn(str(root), html)
        self.assertNotIn("C:\\", html)

    @unittest.skipUnless(PYTHON_EXE.is_file(), "requires project Python runtime")
    def test_plan_command_runs_from_external_unicode_directory_without_models(self):
        with TemporaryDirectory() as temporary:
            external = Path(temporary) / "consumer acceptance"
            external.mkdir()
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
            completed = subprocess.run(
                [
                    str(PYTHON_EXE),
                    "-m",
                    "examples.local_consumer.acceptance_runner",
                    "plan",
                    "--corpus",
                    str(DEFAULT_CORPUS),
                    "--input-root",
                    str(ROOT / "data" / "pdf"),
                    "--device",
                    "cpu",
                ],
                cwd=external,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["case_count"], 8)
        self.assertEqual(payload["layout_family_count"], 8)
        self.assertEqual(payload["real_pdf_execution_count"], 9)
        self.assertTrue(payload["all_inputs_available"])


if __name__ == "__main__":
    unittest.main()
