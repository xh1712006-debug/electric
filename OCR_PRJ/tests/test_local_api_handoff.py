"""Documentation, release and public-command tests for IMMEDIATE-010."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts.local_api_v1_handoff import (
    ROOT,
    load_release_manifest,
    main,
    render_handoff_html,
    validate_release,
)
from src.relay_form_ocr import PIPELINE_VERSION
from src.relay_form_ocr.cli import CLI_SCHEMA_VERSION
from src.relay_form_ocr.schemas import SCHEMA_VERSION


class LocalApiV1HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_release_manifest()

    def _external_env(self) -> dict[str, str]:
        env = os.environ.copy()
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(ROOT) if not existing else os.pathsep.join((str(ROOT), existing))
        env["PYTHONUTF8"] = "1"
        return env

    def test_release_manifest_locks_v1_versions_scope_and_next_task(self):
        self.assertEqual(self.manifest["release_id"], "ocr_prj.local_api.v1")
        self.assertEqual(self.manifest["release_status"], "scope_locked")
        self.assertEqual(self.manifest["local_api_version"], "1.0")
        self.assertEqual(self.manifest["schema_version"], SCHEMA_VERSION)
        self.assertEqual(self.manifest["cli_schema_version"], CLI_SCHEMA_VERSION)
        self.assertEqual(self.manifest["pipeline_version"], PIPELINE_VERSION)
        self.assertTrue(self.manifest["source_checkout_mode"])
        self.assertTrue(self.manifest["next_task"].startswith("PLAN-001"))

    def test_release_validator_checks_docs_links_schemas_fixtures_and_imports(self):
        self.assertEqual(validate_release(self.manifest), [])

    def test_documentation_is_nonempty_and_api_guide_has_team_integration_topics(self):
        for name in ("README.md", "API.md", "ARCHITECTURE.md", "session-handoff.md"):
            with self.subTest(name=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                self.assertGreater(len(text), 500)
        api = (ROOT / "API.md").read_text(encoding="utf-8")
        for topic in (
            "Clone và chuẩn bị runtime",
            "Public Python API tối thiểu",
            "Progress callback",
            "Error handling và retry",
            "Artifact và integrity audit",
            "CLI adapter",
            "Consumer mẫu",
            "Troubleshooting",
            "backward compatibility",
        ):
            with self.subTest(topic=topic):
                self.assertIn(topic, api)

    def test_public_import_smoke_runs_from_external_unicode_consumer_directory(self):
        with TemporaryDirectory() as temporary:
            cwd = Path(temporary) / "consumer ngoài repository"
            cwd.mkdir()
            code = (
                "import json; "
                "from src.relay_form_ocr import "
                "OcrRequest,OcrResult,RelayFormOcrService,ProgressEvent,PIPELINE_VERSION; "
                "print(json.dumps({'pipeline':PIPELINE_VERSION,'imports':5}))"
            )
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=cwd,
                env=self._external_env(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), {"pipeline": "0.7.0", "imports": 5})

    def test_cli_help_smoke_runs_from_external_unicode_consumer_directory(self):
        with TemporaryDirectory() as temporary:
            cwd = Path(temporary) / "ứng dụng quản lý"
            cwd.mkdir()
            completed = subprocess.run(
                [sys.executable, "-m", "src.relay_form_ocr", "--help"],
                cwd=cwd,
                env=self._external_env(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--input", completed.stdout)
        self.assertIn("--output-root", completed.stdout)
        self.assertIn("--correlation-id", completed.stdout)
        self.assertIn("--output-json", completed.stdout)

    def test_cli_invalid_pdf_smoke_returns_documented_typed_failure(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            cwd = root / "consumer tiếng Việt"
            cwd.mkdir()
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.relay_form_ocr",
                    "--input",
                    str((root / "missing.pdf").resolve()),
                    "--output-root",
                    str((root / "artifacts").resolve()),
                    "--correlation-id",
                    "handoff-invalid-pdf",
                    "--json",
                ],
                cwd=cwd,
                env=self._external_env(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 3)
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["pipeline_version"], "0.7.0")
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"]["code"], "INPUT_NOT_FOUND")
        self.assertNotIn(str(root), completed.stdout)

    def test_visual_report_is_accented_vietnamese_responsive_and_path_safe(self):
        with TemporaryDirectory() as temporary:
            output = render_handoff_html(self.manifest, Path(temporary) / "handoff_review.html")
            html = output.read_text(encoding="utf-8")
        self.assertIn('<html lang="vi">', html)
        self.assertIn("Bàn giao Local API v1", html)
        self.assertIn("Phạm vi hỗ trợ", html)
        self.assertIn("Giới hạn đã công bố", html)
        self.assertIn("Hàng rào sử dụng dữ liệu", html)
        self.assertIn("không phải phép đo độ chính xác OCR", html)
        self.assertIn("PLAN-001", html)
        self.assertIn("@media(max-width:440px)", html)
        self.assertNotIn("C:\\", html)
        self.assertNotIn("None", html)

    def test_visual_cli_and_check_only_succeed(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "handoff_review.html"
            self.assertEqual(main(["--output", str(output)]), 0)
            self.assertTrue(output.is_file())
        self.assertEqual(main(["--check-only"]), 0)


if __name__ == "__main__":
    unittest.main()
