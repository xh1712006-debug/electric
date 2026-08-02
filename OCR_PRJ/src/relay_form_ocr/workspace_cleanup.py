"""Explicit dry-run-first cleanup command for managed OCR workspaces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import TextIO

from .workspace import WorkspaceError, WorkspaceManager


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or delete one managed OCR workspace.")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument(
        "--confirm-delete",
        action="store_true",
        help="Delete the validated workspace; without this flag the command is dry-run only",
    )
    return parser


def _emit(payload: dict[str, object], stream: TextIO) -> None:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    binary = getattr(stream, "buffer", None)
    if binary is not None:
        binary.write(text.encode("utf-8"))
        binary.flush()
    else:
        stream.write(text)
        stream.flush()


def main(argv: list[str] | None = None, *, stdout: TextIO | None = None) -> int:
    args = _parser().parse_args(argv)
    stream = stdout if stdout is not None else sys.stdout
    try:
        plan = WorkspaceManager().cleanup(
            args.output_root.resolve(strict=False),
            args.correlation_id,
            confirm=args.confirm_delete,
        )
    except WorkspaceError:
        _emit(
            {
                "status": "failed",
                "error": {
                    "code": "WORKSPACE_CLEANUP_REFUSED",
                    "message": "Workspace không tồn tại, không thuộc OCR hoặc chứa đường dẫn không an toàn.",
                },
            },
            stream,
        )
        return 4
    _emit(
        {
            "status": "deleted" if plan.deleted else "dry_run",
            "cleanup": plan.as_dict(),
        },
        stream,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
