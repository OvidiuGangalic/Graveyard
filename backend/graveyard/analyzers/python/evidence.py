"""Weak references (PY-W1, PY-W2) and flags (PY-F1..PY-F6) for a Python candidate."""

from __future__ import annotations

import ast
import posixpath
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from graveyard import config
from graveyard.analyzers.common import TextIndex, clip, whole_token
from graveyard.analyzers.python.records import (
    ClassDef,
    FileFacts,
    FunctionDef,
    StringLit,
)
from graveyard.models import Caller, Flag


@dataclass(frozen=True)
class RepoFacts:
    class_names: frozenset[str]  # every class defined in any Python source file
    has_reflection: bool  # any file calls getattr with a non-literal name
    facts_by_file: Mapping[str, FileFacts]


_BENIGN_DECORATORS = frozenset(
    "staticmethod classmethod property setter getter deleter cached_property lru_cache cache "
    "wraps contextmanager asynccontextmanager singledispatch singledispatchmethod "
    "total_ordering final override deprecated no_type_check dataclass".split()
)
_BENIGN_PREFIXES = ("typing.", "functools.", "contextlib.")
_KNOWN_BASES = frozenset(
    "object Generic Protocol ABC NamedTuple TypedDict Enum IntEnum StrEnum Exception "
    "BaseException dict list set tuple str int".split()
)


def collect_strings(
    path: str, tree: ast.Module, lines: Sequence[str] = ()
) -> tuple[StringLit, ...]:
    """Every string constant that is not a module, class or function docstring."""
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            line = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else node.value
            out.append(StringLit(node.value, node.lineno, path, clip(line)))
    return tuple(sorted(out, key=lambda s: (s.line, s.value)))


def string_callers(
    func: FunctionDef,
    strings_by_file: Mapping[str, tuple[StringLit, ...]],
    text_index: TextIndex,
) -> list[Caller]:
    """PY-W1 (strings in Python files) and PY-W2 (text-reference files)."""
    pattern = whole_token(func.name)
    callers: list[Caller] = []
    for path, strings in strings_by_file.items():
        for s in strings:
            if path == func.file_path and func.start_line <= s.line <= func.end_line:
                continue
            if s.value == func.name or pattern.search(s.value):
                callers.append(Caller(path, s.line, "string_match", s.snippet))
    if len(func.name) > config.SHORT_NAME_LENGTH:
        callers += [
            Caller(path, line, "string_match", text)
            for path, line, text in text_index.lookup(func.name)
        ]
    return callers


def dunder_all_callers(func: FunctionDef, file_facts: FileFacts, repo: RepoFacts) -> list[Caller]:
    """PY-F5: `__all__` in the defining module or the sibling `__init__.py` lists the name."""
    init = posixpath.join(posixpath.dirname(func.file_path), "__init__.py")
    out = []
    for facts in (file_facts, repo.facts_by_file.get(init)):
        if facts is None or func.name not in facts.dunder_all:
            continue
        line = next((b.line for b in facts.bindings if b.name == "__all__"), 1)
        text = facts.lines[line - 1] if 0 < line <= len(facts.lines) else "__all__"
        out.append(Caller(facts.path, line, "reexport", clip(text)))
    return out


def _unknown_decorator(func: FunctionDef) -> str | None:
    for d in func.decorators:
        if d.final_name in _BENIGN_DECORATORS or d.dotted.startswith(_BENIGN_PREFIXES):
            continue
        return f"@{d.source}"
    return None


def _external_base(cls: ClassDef, repo: RepoFacts) -> str | None:
    for source, name in zip(cls.bases, cls.base_names, strict=False):
        if name not in _KNOWN_BASES and name not in repo.class_names:
            return source
    return None


def flags_for(
    func: FunctionDef,
    cls: ClassDef | None,
    file_facts: FileFacts,
    repo: RepoFacts,
    callers: Sequence[Caller] = (),
) -> tuple[frozenset[Flag], dict[Flag, str]]:
    """PY-F1..PY-F6. ``callers`` are the PY-W1/W2 hits from :func:`string_callers`."""
    details: dict[Flag, str] = {}
    if (decorator := _unknown_decorator(func)) is not None:
        details[Flag.UNKNOWN_DECORATOR] = decorator
    if cls is not None and (base := _external_base(cls, repo)) is not None:
        details[Flag.EXTERNAL_BASE_CLASS] = base
    if file_facts.has_dynamic_lookup:
        details[Flag.DYNAMIC_PATTERN_IN_FILE] = "dynamic lookups"
    elif file_facts.has_module_getattr:
        details[Flag.DYNAMIC_PATTERN_IN_FILE] = "module-level __getattr__"
    if func.class_name is not None and repo.has_reflection:
        details[Flag.REPO_HAS_REFLECTION] = "getattr with a non-literal name"
    if dunder_all_callers(func, file_facts, repo):
        details[Flag.IN_DUNDER_ALL] = "listed in __all__"
    if first := next((c for c in callers if c.kind == "string_match"), None):
        details[Flag.STRING_MATCH] = f"{first.file_path}:{first.line}"
    return frozenset(details), details
