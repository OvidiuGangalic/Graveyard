"""Dead imports (Requirement 6, rules PY-I1..PY-I7)."""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from pathlib import PurePosixPath

from graveyard.analyzers.common import snippet_for
from graveyard.analyzers.python.records import (
    FileFacts,
    ImportBinding,
    ModuleBinding,
    Occurrence,
)
from graveyard.models import Candidate, Flag

_NOQA = re.compile(r"#\s*(noqa|type:\s*ignore)", re.IGNORECASE)
_IMPORT_ERRORS = {"ImportError", "ModuleNotFoundError"}
_BLOCKS = ("body", "orelse", "finalbody", "handlers")
_Walked = Iterator[tuple[ast.Import | ast.ImportFrom, bool, bool]]


def _catches_import_error(handler: ast.ExceptHandler) -> bool:
    def hit(node: ast.expr | None) -> bool:
        if node is None:  # bare `except:`
            return True
        if isinstance(node, ast.Tuple):
            return any(hit(e) for e in node.elts)
        name = node.id if isinstance(node, ast.Name) else getattr(node, "attr", None)
        return name in _IMPORT_ERRORS

    return hit(handler.type)


def _walk(stmts: Iterable[ast.stmt], in_try: bool, in_if: bool) -> _Walked:
    """Module-level import statements with their conditional context."""
    for stmt in stmts:
        if isinstance(stmt, ast.Import | ast.ImportFrom):
            yield stmt, in_try, in_if
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        guarded = in_try or (
            isinstance(stmt, ast.Try | ast.TryStar)
            and any(_catches_import_error(h) for h in stmt.handlers)
        )
        nested = in_if or isinstance(stmt, ast.If)
        for field in _BLOCKS:
            for child in getattr(stmt, field, None) or []:
                body = child.body if isinstance(child, ast.ExceptHandler) else [child]
                yield from _walk(body, guarded, nested)
        for case in getattr(stmt, "cases", None) or []:
            yield from _walk(case.body, in_try, in_if)


def collect_import_bindings(
    path: str, tree: ast.Module, lines: Sequence[str]
) -> tuple[ImportBinding, ...]:
    """Module-level import bindings in source order (``path`` is unused; kept for symmetry)."""
    out: list[ImportBinding] = []
    for stmt, in_try, in_if in _walk(tree.body, False, False):
        start, end = stmt.lineno, stmt.end_lineno or stmt.lineno
        noqa = any(_NOQA.search(lines[i - 1]) for i in {start, end} if i <= len(lines))
        for a in stmt.names:
            if isinstance(stmt, ast.Import):
                module, bound, plain = a.name, a.asname or a.name.split(".")[0], True
            else:
                module, bound, plain = stmt.module or "", a.asname or a.name, False
            out.append(
                ImportBinding(
                    bound_name=bound,
                    display_name=a.name if plain else bound,  # Requirement 6.6
                    start_line=start,
                    end_line=end,
                    is_plain_import=plain,
                    module=module,
                    top_module=module.split(".")[0],
                    is_future=not plain and module == "__future__" and not stmt.level,
                    is_star=a.name == "*",
                    in_try_importerror=in_try,
                    in_if=in_if,
                    noqa=noqa,
                    names_in_statement=len(stmt.names),
                )
            )
    return tuple(out)


def reexport_pairs(
    bindings_by_file: Mapping[str, Iterable[ModuleBinding]],
) -> set[tuple[str, str]]:
    """(last segment of M, name) for every `from M import name` in the repo (PY-I6)."""
    return {
        (b.module.rsplit(".", 1)[-1], b.imported)
        for bindings in bindings_by_file.values()
        for b in bindings
        if b.kind == "import" and b.module and b.imported
    }


def _use_lines(occurrences: Iterable[Occurrence]) -> dict[str, list[int]]:
    """Bound name -> lines where it is used (PY-R1, PY-R2 base name, PY-R6)."""
    used: dict[str, list[int]] = {}
    for o in occurrences:
        if o.form == "import" or o.is_store:
            continue
        if o.form == "attr":
            if not o.receiver:
                continue
            base = o.receiver.split(".")[0]
        else:
            base = o.name
        used.setdefault(base, []).append(o.line)
    return used


def dead_imports(
    path: str,
    bindings: Sequence[ImportBinding],
    occurrences: Iterable[Occurrence],
    file_facts: FileFacts,
    reexported: Collection[tuple[str, str]] = frozenset(),
) -> list[Candidate]:
    """Unused-import Candidates of one file (Test files are analysed like any other)."""
    stem = PurePosixPath(path.replace("\\", "/")).stem
    if not file_facts.parsed or stem == "__init__":  # PY-I7, PY-I1
        return []
    used = _use_lines(occurrences)
    dunder_all = set(file_facts.dunder_all)

    def is_dead(b: ImportBinding) -> bool:
        if b.is_future or b.is_star or b.noqa or b.bound_name in dunder_all:  # PY-I3/4/5/2
            return False
        if (stem, b.bound_name) in reexported:  # PY-I6
            return False
        return all(b.start_line <= ln <= b.end_line for ln in used.get(b.bound_name, ()))

    dead = [b for b in bindings if is_dead(b)]
    per_stmt: dict[tuple[int, int, str], int] = {}
    for b in dead:
        key = (b.start_line, b.end_line, b.module)
        per_stmt[key] = per_stmt.get(key, 0) + 1
    out: list[Candidate] = []
    for b in dead:
        flags: set[Flag] = set()
        details: dict[Flag, str] = {}
        if b.is_plain_import and b.top_module not in sys.stdlib_module_names:
            flags.add(Flag.SIDE_EFFECT_IMPORT)
            details[Flag.SIDE_EFFECT_IMPORT] = b.module
        if b.in_try_importerror or b.in_if:
            flags.add(Flag.CONDITIONAL_IMPORT)
        if per_stmt[(b.start_line, b.end_line, b.module)] < b.names_in_statement:
            flags.add(Flag.PARTIAL_STATEMENT)
        if file_facts.has_dynamic_lookup:
            flags.add(Flag.DYNAMIC_PATTERN_IN_FILE)
        snippet, truncated = snippet_for(file_facts.lines, b.start_line, b.end_line)
        out.append(
            Candidate(
                name=b.display_name,
                qualified_name=b.display_name,
                kind="import",
                language="python",
                file_path=path,
                start_line=b.start_line,
                end_line=b.end_line,
                code_snippet=snippet,
                snippet_truncated=truncated,
                test_coverage="unknown",
                flags=frozenset(flags),
                flag_details=details,
            )
        )
    return out
