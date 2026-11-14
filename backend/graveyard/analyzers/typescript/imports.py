"""Dead imports (Requirement 7)."""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from tree_sitter import Node, Tree

from graveyard.analyzers.common import snippet_for
from graveyard.analyzers.typescript.parser import end_line, line, text
from graveyard.analyzers.typescript.records import TsFileFacts
from graveyard.analyzers.typescript.references import TsOccurrence
from graveyard.models import Candidate, Flag

_SUPPRESS = re.compile(r"eslint-disable|@ts-ignore|@ts-expect-error")
_JSX_PRAGMA = re.compile(rb"@jsx\s+([A-Za-z_$][\w$]*)")
_JSX_EXTS = {".tsx", ".jsx"}


@dataclass(frozen=True)
class TsImportBinding:
    local_name: str
    imported_name: str  # "default", "*", or the exported name
    start_line: int
    end_line: int
    is_type: bool
    specifier: str
    names_in_statement: int
    prev_line_text: str  # line above the statement ("" at file start)
    start_line_text: str
    end_line_text: str


def _specifier_string(stmt: Node) -> str:
    source = stmt.child_by_field_name("source")
    if source is None:
        return ""
    return "".join(text(c) for c in source.children if c.type == "string_fragment")


def _found(clause: Node, stmt_type: bool) -> list[tuple[str, str, bool]]:
    """(local, imported, is_type) for each binding of an import clause."""
    found: list[tuple[str, str, bool]] = []
    for c in clause.children:
        if c.type == "identifier":
            found.append((text(c), "default", stmt_type))
        elif c.type == "namespace_import":
            ident = next((i for i in c.children if i.type == "identifier"), None)
            if ident is not None:
                found.append((text(ident), "*", stmt_type))
        elif c.type == "named_imports":
            for s in c.children:
                name = s.child_by_field_name("name")
                if s.type != "import_specifier" or name is None:
                    continue
                alias = s.child_by_field_name("alias")
                inline = any(x.type == "type" for x in s.children)
                found.append((text(alias or name), text(name), stmt_type or inline))
    return found


def collect_import_bindings(tree: Tree, data: bytes) -> tuple[TsImportBinding, ...]:
    """Local names bound by top-level `import_statement`s, in source order."""
    lines = data.decode("utf-8", errors="replace").splitlines()

    def at(n: int) -> str:
        return lines[n - 1] if 1 <= n <= len(lines) else ""

    out: list[TsImportBinding] = []
    for stmt in tree.root_node.children:
        clause = next((c for c in stmt.children if c.type == "import_clause"), None)
        if stmt.type != "import_statement" or clause is None:
            continue
        found = _found(clause, any(c.type == "type" for c in stmt.children))
        start, end, spec = line(stmt), end_line(stmt), _specifier_string(stmt)
        out += [
            TsImportBinding(
                local,
                imported,
                start,
                end,
                is_type,
                spec,
                len(found),
                at(start - 1),
                at(start),
                at(end),
            )  # fmt: skip
            for local, imported, is_type in found
        ]
    return tuple(out)


def _pragma_names(tree: Tree) -> set[str]:
    """`/** @jsx h */` names `h`; `@jsxImportSource x` names no bindable local."""
    names: set[str] = set()
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "comment":
            names.update(m.decode() for m in _JSX_PRAGMA.findall(node.text or b""))
        else:
            stack.extend(node.children)
    return names


def _used_names(
    bindings: Sequence[TsImportBinding], occurrences: Iterable[TsOccurrence]
) -> set[str]:
    spans = [(b.start_line, b.end_line) for b in bindings]
    used: set[str] = set()
    for o in occurrences:
        if o.form in {"member", "token"} or (o.form == "jsx" and o.receiver is not None):
            continue  # property names are not uses of a same-named local
        if not any(s <= o.line <= e for s, e in spans):
            used.add(o.name)
    return used


def dead_imports(
    path: str,
    bindings: Sequence[TsImportBinding],
    occurrences: Iterable[TsOccurrence],
    file_facts: TsFileFacts,
    data: bytes,
    has_dynamic_pattern: bool,
    tree: Tree | None = None,
) -> list[Candidate]:
    """Unused-import Candidates of one file; `tree` is only needed for `@jsx` pragmas."""
    if not file_facts.parsed:
        return []
    used = _used_names(bindings, occurrences) | file_facts.exported_names
    pragma = _pragma_names(tree) if tree is not None else set()
    jsx_file = posixpath.splitext(path)[1].lower() in _JSX_EXTS

    def is_dead(b: TsImportBinding) -> bool:
        if b.local_name in used or b.local_name in pragma:
            return False
        if jsx_file and b.local_name == "React" and b.imported_name in {"default", "*"}:
            return False
        texts = (b.prev_line_text, b.start_line_text, b.end_line_text)
        return not any(_SUPPRESS.search(t) for t in texts)

    dead = [b for b in bindings if is_dead(b)]
    per_stmt: dict[tuple[int, int], int] = {}
    for b in dead:
        per_stmt[(b.start_line, b.end_line)] = per_stmt.get((b.start_line, b.end_line), 0) + 1
    out: list[Candidate] = []
    for b in dead:
        flags: set[Flag] = set()
        if per_stmt[(b.start_line, b.end_line)] < b.names_in_statement:
            flags.add(Flag.PARTIAL_STATEMENT)
        if has_dynamic_pattern:
            flags.add(Flag.DYNAMIC_PATTERN_IN_FILE)
        snippet, truncated = snippet_for(file_facts.lines, b.start_line, b.end_line)
        out.append(
            Candidate(
                name=b.local_name,
                qualified_name=b.local_name,
                kind="import",
                language="typescript",
                file_path=path,
                start_line=b.start_line,
                end_line=b.end_line,
                code_snippet=snippet,
                snippet_truncated=truncated,
                test_coverage="unknown",
                flags=frozenset(flags),
            )
        )
    return out
