"""Arity rule TS-A1: an argument count a method's signature cannot accept is not a reference."""

from __future__ import annotations

from graveyard.analyzers.typescript.records import TsFunction

_TYPED = (".ts", ".tsx")


def incompatible(func: TsFunction, args: int, has_spread: bool, call_file: str) -> bool:
    """True if `obj.x(...)` with `args` arguments cannot call method `func`; False when unsure."""
    if has_spread or not func.is_method or func.params.has_rest:
        return False
    if not (call_file.endswith(_TYPED) and func.file_path.endswith(_TYPED)):
        return False
    return args > func.params.total or args < func.params.required
