"""Python analyser: per-file collection, then a join over every name occurrence."""

from __future__ import annotations

import logging
from collections import defaultdict

from graveyard.analyzers.common import cap_callers, check_deadline, clip, snippet_for
from graveyard.analyzers.python.definitions import collect_definitions, parse_module
from graveyard.analyzers.python.records import FileFacts, FunctionDef, Occurrence
from graveyard.analyzers.python.references import _tokens, collect_occurrences
from graveyard.ingestion.walker import read_text
from graveyard.models import (
    AnalyserResult,
    Caller,
    Candidate,
    ProgressFn,
    RepoSnapshot,
    no_progress,
)

log = logging.getLogger(__name__)

_Entry = tuple[str, Occurrence, bool]  # (file_path, occurrence, is_test_file)


def _inside(func: FunctionDef, path: str, line: int, occ_path: str) -> bool:
    return occ_path == path and func.start_line <= line <= func.end_line


def analyse_python(
    snapshot: RepoSnapshot,
    progress: ProgressFn = no_progress,
    deadline: float | None = None,
) -> AnalyserResult:
    files = [f for f in snapshot.source_files if f.language == "python"]
    facts: dict[str, FileFacts] = {}
    texts: dict[str, list[str]] = {}
    index: dict[str, list[_Entry]] = defaultdict(list)
    failed = 0
    for done, source in enumerate(files, 1):
        check_deadline(deadline)
        text = read_text(snapshot.root, source.path)
        try:
            tree = parse_module(text.replace("\r\n", "\n"))
            file_facts = collect_definitions(source.path, text, tree)
            occurrences = collect_occurrences(text, tree)
        except Exception:
            log.exception("Python analysis failed for %s", source.path)
            file_facts, occurrences = FileFacts(source.path, False), tuple(_tokens(text))
        failed += not file_facts.parsed
        facts[source.path] = file_facts
        texts[source.path] = text.replace("\r\n", "\n").split("\n")
        for occ in occurrences:
            index[occ.name].append((source.path, occ, source.is_test))
        progress("python", done)

    has_tests = any(f.is_test for f in files)
    candidates: list[Candidate] = []
    defined = 0
    for source in files:
        if source.is_test:
            continue
        for func in facts[source.path].functions:
            defined += 1
            entries = index.get(func.name, ())
            used = any(
                not is_test and not _inside(func, source.path, occ.line, path)
                for path, occ, is_test in entries
            )
            if used:
                continue
            lines = facts[source.path].lines
            tests = [
                Caller(path, occ.line, "test_reference", clip(_line(texts[path], occ.line)))
                for path, occ, is_test in entries
                if is_test
            ]
            snippet, truncated = snippet_for(lines, func.start_line, func.end_line)
            coverage = "covered" if tests else "not_covered" if has_tests else "unknown"
            candidates.append(
                Candidate(
                    name=func.name,
                    qualified_name=func.qualified_name,
                    kind="function",
                    language="python",
                    file_path=source.path,
                    start_line=func.start_line,
                    end_line=func.end_line,
                    code_snippet=snippet,
                    snippet_truncated=truncated,
                    callers=cap_callers(tests),
                    test_coverage=coverage,
                )
            )
    candidates.sort(key=lambda c: (c.file_path, c.start_line, c.name))
    return AnalyserResult(tuple(candidates), defined, len(files) - failed, failed)


def _line(lines: list[str], line: int) -> str:
    return lines[line - 1] if 0 < line <= len(lines) else ""
