"""Per-file facts collected by the Python analyser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Param:
    """Parameter list of a function, as needed by the arity rule."""

    positional: tuple[str, ...] = ()
    positional_defaults: int = 0
    kwonly: tuple[str, ...] = ()
    kwonly_required: tuple[str, ...] = ()
    has_vararg: bool = False
    has_kwarg: bool = False


@dataclass(frozen=True)
class DecoratorInfo:
    source: str
    final_name: str
    dotted: str
    is_call: bool


@dataclass(frozen=True)
class FunctionDef:
    name: str
    qualified_name: str
    file_path: str
    class_name: str | None
    start_line: int
    end_line: int
    is_async: bool
    decorators: tuple[DecoratorInfo, ...]
    params: Param
    body_kind: Literal["stub", "normal"]
    is_staticmethod: bool


@dataclass(frozen=True)
class ClassDef:
    name: str
    file_path: str
    start_line: int
    end_line: int
    bases: tuple[str, ...]
    base_names: tuple[str, ...]
    method_names: tuple[str, ...]
    decorators: tuple[DecoratorInfo, ...]


@dataclass(frozen=True)
class ModuleBinding:
    name: str
    kind: Literal["def", "class", "assign", "import", "global"]
    line: int
    module: str | None = None  # import bindings: dotted module as written, no leading dots
    level: int = 0  # relative-import level (number of leading dots)
    imported: str | None = None  # `from M import y as x` -> "y"; plain `import` -> None


@dataclass(frozen=True)
class ImportBinding:
    """One name bound by one alias of a module-level import statement."""

    bound_name: str
    display_name: str  # what the Candidate is called: `a.b`, `x` for `from m import x as y`
    start_line: int
    end_line: int
    is_plain_import: bool  # `import a.b` (not `from ... import`)
    module: str  # dotted, as written (no leading dots)
    top_module: str
    is_future: bool = False
    is_star: bool = False
    in_try_importerror: bool = False
    in_if: bool = False
    noqa: bool = False
    names_in_statement: int = 1


@dataclass(frozen=True)
class CallShape:
    positional: int
    keywords: tuple[str, ...]
    has_unpack: bool


@dataclass(frozen=True)
class Occurrence:
    name: str
    line: int
    form: Literal["name", "attr", "import", "token"]
    receiver: str | None
    enclosing_class: str | None
    in_class_body: bool
    is_store: bool
    call: CallShape | None
    self_param: str | None = None  # first parameter of the enclosing method, if any


@dataclass(frozen=True)
class FileFacts:
    path: str
    parsed: bool
    functions: tuple[FunctionDef, ...] = ()
    classes: tuple[ClassDef, ...] = ()
    bindings: tuple[ModuleBinding, ...] = ()
    dunder_all: tuple[str, ...] = ()
    has_module_getattr: bool = False
    has_star_import: bool = False
    star_imports: tuple[tuple[str | None, int], ...] = ()  # (module, level) of `from M import *`
    has_dynamic_lookup: bool = False  # PY-F3 construct anywhere in the file
    has_getattr_reflection: bool = False  # `getattr(x, <non-literal>)` anywhere (PY-F4)
    local_import_names: frozenset[str] = frozenset()  # names bound by non-module-level imports
    lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class StringLit:
    """A non-docstring string constant (PY-W1)."""

    value: str
    line: int
    file: str
    snippet: str = ""
