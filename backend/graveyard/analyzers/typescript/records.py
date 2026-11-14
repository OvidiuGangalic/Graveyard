"""Per-file facts collected by the TypeScript analyser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TsParams:
    """Parameter counts for TS-A1: `this` is not counted, and a rest parameter is not in `total`."""

    total: int = 0
    required: int = 0
    has_rest: bool = False


@dataclass(frozen=True)
class TsFunction:
    name: str
    qualified_name: str
    file_path: str
    class_name: str | None
    start_line: int
    end_line: int
    is_exported: bool
    is_default: bool
    is_method: bool
    is_async_or_generator: bool
    decorators: tuple[str, ...]
    params: TsParams
    body_kind: Literal["stub", "normal"]
    is_abstract: bool


@dataclass(frozen=True)
class TsClass:
    name: str
    file_path: str
    start_line: int
    end_line: int
    extends: str | None  # source text of the extends expression
    extends_name: str | None  # its final name: `a.B<T>` -> `B`
    implements: bool
    decorators: tuple[str, ...]
    method_names: tuple[str, ...]
    is_exported: bool


@dataclass(frozen=True)
class TsFileFacts:
    path: str
    parsed: bool
    is_es_module: bool = False
    functions: tuple[TsFunction, ...] = ()
    classes: tuple[TsClass, ...] = ()
    top_level_names: frozenset[str] = frozenset()
    exported_names: frozenset[str] = frozenset()
    has_default_export: bool = False
    overload_name_lines: frozenset[tuple[str, int]] = frozenset()
    lines: tuple[str, ...] = ()
