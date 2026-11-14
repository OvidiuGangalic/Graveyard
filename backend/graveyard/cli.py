"""Command line entry point: ``python -m graveyard.cli analyse <path|sample:haunted>``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from graveyard.analyzers.python.analyser import analyse_python
from graveyard.ingestion import ingest_local
from graveyard.ingestion.samples import sample_snapshot
from graveyard.models import RepoSnapshot


def _snapshot(target: str) -> RepoSnapshot:
    if target.startswith("sample:"):
        return sample_snapshot(target.split(":", 1)[1])  # type: ignore[arg-type]
    return ingest_local(target)


def analyse(target: str) -> dict[str, object]:
    snapshot = _snapshot(target)
    result = analyse_python(snapshot)
    return {
        "files": [f.path for f in snapshot.source_files],
        "candidates": [
            {
                "name": c.name,
                "qualified_name": c.qualified_name,
                "kind": c.kind,
                "file_path": c.file_path,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "test_coverage": c.test_coverage,
                "callers": [
                    {"file_path": k.file_path, "line": k.line, "kind": k.kind, "snippet": k.snippet}
                    for k in c.callers
                ],
            }
            for c in result.candidates
        ],
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
