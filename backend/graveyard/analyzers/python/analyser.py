"""Python analyser: per-file collection, then a join over every name occurrence."""

from __future__ import annotations

import logging
from collections import defaultdict

from graveyard.analyzers.common import cap_callers, check_deadline, clip, snippet_for
from graveyard.analyzers.python.arity import incompatible
from graveyard.analyzers.python.definitions import collect_definitions, parse_module
from graveyard.analyzers.python.entrypoints import exempt_rule, load_script_entries
from graveyard.analyzers.python.records import FileFacts, FunctionDef, Occurrence
from graveyard.analyzers.python.references import _tokens, collect_occurrences
from graveyard.analyzers.python.resolve import ModuleIndex, Unresolved, resolve
from graveyard.ingestion.walker import read_text
from graveyard.models import (
    AnalyserResult,
    Caller,
    Candidate,
    Flag,
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
    *,
    resolve_all_unresolved: bool = False,
) -> AnalyserResult:
    files = [f for f in snapshot.source_files if f.language == "python"]
    facts: dict[str, FileFacts] = {}
    texts: dict[str, list[str]] = {}
    occs: list[_Entry] = []
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
        occs += [(source.path, occ, source.is_test) for occ in occurrences]
        progress("python", done)

    modules = ModuleIndex(f.path for f in files)
    unresolved: dict[str, list[_Entry]] = defaultdict(list)  # by name
    resolved: dict[FunctionDef, list[_Entry]] = defaultdict(list)
    for entry in occs:
        path, occ, _ = entry
        found = Unresolved() if resolve_all_unresolved else resolve(occ, path, facts, modules)
        if isinstance(found, Unresolved):
            unresolved[occ.name].append(entry)
        else:
            for func in found:
                resolved[func].append(entry)

    has_tests = any(f.is_test for f in files)
    scripts = load_script_entries(snapshot.root, snapshot.text_files)
    candidates: list[Candidate] = []
    defined = 0
    for source in files:
        if source.is_test:
            continue
        classes = {c.name: c for c in facts[source.path].classes}
        for func in facts[source.path].functions:
            defined += 1
            cls = classes.get(func.class_name) if func.class_name else None
            if exempt_rule(func, cls, source, scripts):  # PY-E1..E9: never reported
                continue
            by_name = [
                e
                for e in unresolved.get(func.name, ())
                if func.class_name is None  # bare names never mean methods (PY-S7)
                or resolve_all_unresolved
                or e[1].form != "name"
                or e[1].in_class_body
            ]
            skipped = [  # PY-A1: calls this definition could not accept
                e
                for e in by_name
                if not resolve_all_unresolved and e[1].call and incompatible(func, e[1].call)
            ]
            entries = resolved.get(func, []) + [e for e in by_name if e not in skipped]
            used = any(
                not is_test and not _inside(func, source.path, occ.line, path)
                for path, occ, is_test in entries
            )
            if used:
                continue
            flags: set[Flag] = set()
            details: dict[Flag, str] = {}
            calls = sorted(
                (path, occ.line)
                for path, occ, is_test in skipped
                if not is_test and not _inside(func, source.path, occ.line, path)
            )
            if calls:  # PY-F7
                flags.add(Flag.ARITY_MISMATCH)
                details[Flag.ARITY_MISMATCH] = f"{calls[0][0]}:{calls[0][1]}"
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
                    flags=frozenset(flags),
                    flag_details=details,
                )
            )
    candidates.sort(key=lambda c: (c.file_path, c.start_line, c.name))
    return AnalyserResult(tuple(candidates), defined, len(files) - failed, failed)


def _line(lines: list[str], line: int) -> str:
    return lines[line - 1] if 0 < line <= len(lines) else ""
