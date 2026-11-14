"""Command line entry point: ``python -m graveyard.cli analyse <path|sample:haunted>``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from graveyard.ingestion import ingest_local
from graveyard.ingestion.samples import sample_snapshot
from graveyard.models import RepoSnapshot
from graveyard.pipeline import run


def _snapshot(target: str) -> RepoSnapshot:
    if target.startswith("sample:"):
        return sample_snapshot(target.split(":", 1)[1])  # type: ignore[arg-type]
    return ingest_local(target)


def analyse(target: str) -> dict[str, object]:
    result = run(_snapshot(target), datetime.now(UTC))
    return {
        "warnings": list(result.warnings),
        "totals": {
            "total_files_scanned": result.total_files_scanned,
            "files_skipped": result.files_skipped,
            "items_by_language": result.items_by_language,
            "items_by_verdict": result.items_by_verdict,
            "total_dead_items": result.total_dead_items,
        },
        "items": [item.model_dump(mode="json") for item in result.items],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="graveyard")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("analyse", help="analyse a folder or sample:haunted").add_argument("path")
    args = parser.parse_args(argv)
    json.dump(analyse(args.path), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
