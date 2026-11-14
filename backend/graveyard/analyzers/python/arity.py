"""Arity rule PY-A1: a call that a definition's signature cannot accept is not a reference to it."""

from __future__ import annotations

from graveyard.analyzers.python.entrypoints import is_benign
from graveyard.analyzers.python.records import CallShape, FunctionDef


def _rejects(func: FunctionDef, names: tuple[str, ...], call: CallShape) -> bool:
    p = func.params
    required = names[: max(len(names) - p.positional_defaults, 0)]
    if call.positional > len(names) and not p.has_vararg:
        return True
    if not p.has_kwarg and any(k not in (*names, *p.kwonly) for k in call.keywords):
        return True
    given = {*names[: call.positional], *call.keywords}
    return any(r not in given for r in (*required, *p.kwonly_required))


def incompatible(func: FunctionDef, call: CallShape, receiver: str | None = None) -> bool:
    """True if `call` would raise TypeError for `func`; False when unsure (wrapper, unpacking).

    A method is read as bound (first parameter dropped); when the receiver looks like a class
    (`Base.m(obj)`, `super().m()`) the unbound reading (first parameter supplied) also counts.
    """
    if call.has_unpack or not all(is_benign(d) for d in func.decorators):
        return False
    names = func.params.positional
    if not func.class_name or func.is_staticmethod:
        return _rejects(func, names, call)
    last = (receiver or "").rsplit(".", 1)[-1]
    unbound = last[:1].isupper() or last.startswith("super")
    return _rejects(func, names[1:], call) and not (unbound and not _rejects(func, names, call))
