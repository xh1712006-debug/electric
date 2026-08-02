"""Tests for collision-safe sequential PDF renaming."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.rename_split_pdfs import MANIFEST_NAME, build_rename_plan, rename_pdfs


class RenameSplitPdfsTests(unittest.TestCase):
    def test_plan_is_sorted_and_starts_at_one(self) -> None:
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for name in ("z.pdf", "A.pdf", "middle.PDF"):
                (folder / name).write_bytes(name.encode())
            plan = build_rename_plan(folder)
            self.assertEqual([item["old_name"] for item in plan], ["A.pdf", "middle.PDF", "z.pdf"])
            self.assertEqual([item["new_name"] for item in plan], ["P_001.pdf", "P_002.pdf", "P_003.pdf"])

    def test_rename_handles_existing_target_names_without_overwrite(self) -> None:
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            original_contents = {
                "P_001.pdf": b"existing-target",
                "relay.pdf": b"relay",
                "Việt Trì.pdf": b"unicode",
            }
            for name, content in original_contents.items():
                (folder / name).write_bytes(content)

            result = rename_pdfs(folder)

            self.assertEqual(sorted(path.name for path in folder.glob("*.pdf")), [
                "P_001.pdf", "P_002.pdf", "P_003.pdf"
            ])
            for mapping in result["mappings"]:
                self.assertEqual(
                    (folder / mapping["new_name"]).read_bytes(),
                    original_contents[mapping["old_name"]],
                )
            self.assertTrue((folder / MANIFEST_NAME).is_file())

    def test_dry_run_does_not_change_files(self) -> None:
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "source.pdf").write_bytes(b"pdf")
            result = rename_pdfs(folder, dry_run=True)
            self.assertTrue(result["dry_run"])
            self.assertTrue((folder / "source.pdf").is_file())
            self.assertFalse((folder / MANIFEST_NAME).exists())
