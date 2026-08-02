"""Rename direct PDF children to P_001.pdf, P_002.pdf, ... safely."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
from typing import Any


DEFAULT_FOLDER = Path("data") / "pdf_split" / "documents"
MANIFEST_NAME = "rename_manifest.json"


def build_rename_plan(folder: Path | str) -> list[dict[str, Any]]:
    """Create a deterministic, case-insensitive filename-order rename plan."""

    directory = Path(folder).resolve()
    if not directory.is_dir():
        raise NotADirectoryError(directory)
    pdfs = sorted(
        (path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: (path.name.casefold(), path.name),
    )
    if not pdfs:
        raise FileNotFoundError(f"No PDF files found directly in: {directory}")
    if len(pdfs) > 999:
        raise ValueError("P_xxx supports at most 999 PDF files")
    return [
        {
            "index": index,
            "old_name": source.name,
            "new_name": f"P_{index:03d}.pdf",
            "size_bytes": source.stat().st_size,
        }
        for index, source in enumerate(pdfs, start=1)
    ]


def rename_pdfs(folder: Path | str, *, dry_run: bool = False) -> dict[str, Any]:
    """Apply the plan using a temporary directory so targets cannot collide."""

    directory = Path(folder).resolve()
    mappings = build_rename_plan(directory)
    payload = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "directory": str(directory),
        "ordering": "case_insensitive_original_filename",
        "pattern": "P_xxx.pdf",
        "count": len(mappings),
        "dry_run": dry_run,
        "mappings": mappings,
    }
    if dry_run:
        return payload

    temporary = directory / f".pdf_rename_{uuid.uuid4().hex}"
    temporary.mkdir()
    staged: list[tuple[Path, Path, Path]] = []
    completed: list[tuple[Path, Path, Path]] = []
    try:
        for mapping in mappings:
            original = directory / mapping["old_name"]
            intermediate = temporary / f"{mapping['index']:03d}.pdf"
            destination = directory / mapping["new_name"]
            original.replace(intermediate)
            staged.append((original, intermediate, destination))
        for item in staged:
            original, intermediate, destination = item
            intermediate.replace(destination)
            completed.append((original, intermediate, destination))
    except Exception:
        for original, _, destination in reversed(completed):
            if destination.exists():
                destination.replace(original)
        for original, intermediate, _ in staged:
            if intermediate.exists():
                intermediate.replace(original)
        raise
    finally:
        if temporary.exists() and not any(temporary.iterdir()):
            temporary.rmdir()

    (directory / MANIFEST_NAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rename direct PDF files to P_001.pdf, P_002.pdf, ..."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        type=Path,
        default=DEFAULT_FOLDER,
        help=f"PDF directory (default: {DEFAULT_FOLDER})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the mapping without renaming files")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = rename_pdfs(args.folder, dry_run=args.dry_run)
    # Windows PowerShell may use cp1258, which cannot encode every Vietnamese
    # character. Keep console output portable; the saved manifest stays UTF-8.
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
