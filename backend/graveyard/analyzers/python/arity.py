"""Arity rule PY-A1: a call that a definition's signature cannot accept is not a reference to it."""

from __future__ import annotations

from graveyard.analyzers.python.entrypoints import is_benign
from graveyard.analyzers.python.records import CallShape, FunctionDef


def incompatible(func: FunctionDef, call: CallShape) -> bool:
    """True if `call` would raise TypeError for `func`; False when unsure (wrapper, unpacking)."""
    if call.has_unpack or not all(is_benign(d) for d in func.decorators):
        return False
    p = func.params
    names = p.positional[1:] if func.class_name and not func.is_staticmethod else p.positional
    required = names[: max(len(names) - p.positional_defaults, 0)]
    if call.positional > len(names) and not p.has_vararg:
        return True
    if not p.has_kwarg and any(k not in (*names, *p.kwonly) for k in call.keywords):
        return True
    given = {*names[: call.positional], *call.keywords}
    return any(r not in given for r in (*required, *p.kwonly_required))
