from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import unittest

from scripts.check_debug_ui_environment import DEPENDENCIES, dependency_versions


class DebugUiEnvironmentTests(unittest.TestCase):
    def test_complete_runtime_contains_every_pipeline_stage(self) -> None:
        self.assertEqual(
            set(DEPENDENCIES.values()),
            {
                "opencv-python",
                "numpy",
                "paddlepaddle",
                "paddleocr",
                "Pillow",
                "torch",
                "vietocr",
                "pypdf",
                "streamlit",
            },
        )

    def test_dependency_check_reports_import_failures_without_stopping(self) -> None:
        def importer(name: str):
            if name == "paddle":
                raise OSError("native DLL unavailable")
            return SimpleNamespace()

        versions, errors = dependency_versions(importer, lambda name: f"{name}-version")

        self.assertNotIn("paddlepaddle", versions)
        self.assertIn("streamlit", versions)
        self.assertEqual(errors, ["paddlepaddle: OSError: native DLL unavailable"])

    def test_vietocr_uses_tracked_config_instead_of_network_config(self) -> None:
        source = Path("src/recognition/vietocr.py").read_text(encoding="utf-8")
        config = Path("src/recognition/vgg_transformer.yml")

        self.assertTrue(config.is_file())
        self.assertIn("load_config_from_file", source)
        self.assertNotIn('load_config_from_name("vgg_transformer")', source)


if __name__ == "__main__":
    unittest.main()
