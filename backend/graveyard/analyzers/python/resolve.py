"""Resolve a name occurrence to the definitions it means (rules PY-S1, S2, S3, S6, S7)."""

from __future__ import annotations

from collections.abc import Iterable

from graveyard import config
from graveyard.analyzers.python.records import FileFacts, FunctionDef, ModuleBinding, Occurrence


class Unresolved:
    """Sentinel: the occurrence may mean any function carrying its name (PY-S7)."""


UNRESOLVED = Unresolved()
Resolution = frozenset[FunctionDef] | Unresolved
_NONE: frozenset[FunctionDef] = frozenset()
_Facts = dict[str, FileFacts]


class ModuleIndex:
    """Dotted module path -> repo files, by whole-segment suffix match."""

    def __init__(self, paths: Iterable[str]) -> None:
        self._modules = []
        for path in paths:
            parts = path.removesuffix(".py").split("/")
            self._modules.append((tuple(parts[:-1] if parts[-1] == "__init__" else parts), path))
        self.memo: dict[tuple[object, ...], Resolution] = {}

    def resolve(self, dotted: str) -> list[str]:
        want = tuple(dotted.split(".")) if dotted else ()
        if not want:
            return []
        return [path for segs, path in self._modules if segs[-len(want) :] == want]

    def files(self, b: ModuleBinding, file: str, sub: str | None = None) -> list[str]:
        """Files of the module `b` imports from (or its submodule `sub`), made absolute."""
        pkg = file.split("/")[:-1]
        if b.level - 1 > len(pkg):
            return []
        pkg = pkg[: len(pkg) - max(b.level - 1, 0)] if b.level else []
        base = ".".join([*pkg, *([b.module] if b.module else [])])
        return self.resolve(f"{base}.{sub}" if base and sub else sub or base)


def _find(g: str, name: str, depth: int, facts: _Facts, idx: ModuleIndex) -> Resolution | None:
    """Functions named `name` that module `g` binds; None if it does not bind it at all."""
    ff = facts.get(g)
    # depth 1 is the module named by the importing file; every further import is one step
    if depth > config.REEXPORT_DEPTH + 1 or ff is None or not ff.parsed:
        return UNRESOLVED
    found = [b for b in ff.bindings if b.name == name]
    if not found:
        if ff.has_module_getattr:
            return UNRESOLVED
        return _via_star(g, ff, name, depth, facts, idx)
    out: set[FunctionDef] = set()
    for b in found:
        if b.kind == "def":
            out |= {f for f in ff.functions if f.name == name and f.class_name is None}
        elif b.kind == "import" and b.imported is not None:
            r = _follow(b, g, depth + 1, facts, idx)
            if isinstance(r, Unresolved):
                return r
            out |= r
    return frozenset(out)


def _via_star(
    g: str, ff: FileFacts, name: str, depth: int, facts: _Facts, idx: ModuleIndex
) -> Resolution | None:
    out: set[FunctionDef] = set()
    seen = False
    for module, level in ff.star_imports:
        star = ModuleBinding("*", "import", 0, module, level)
        for f in idx.files(star, g):
            r = None if f == g else _find(f, name, depth + 1, facts, idx)
            if isinstance(r, Unresolved):
                return r
            if r is not None:
                seen, out = True, out | r
    return frozenset(out) if seen else None


def _follow(b: ModuleBinding, g: str, depth: int, facts: _Facts, idx: ModuleIndex) -> Resolution:
    """Follow `from M import y` bound in `g`; a name that is only a submodule has no function."""
    assert b.imported is not None
    submodule = bool(idx.files(b, g, b.imported))
    out: set[FunctionDef] = set()
    for f in idx.files(b, g):
        r = None if f == g else _find(f, b.imported, depth, facts, idx)
        if isinstance(r, Unresolved) or (r is None and not submodule):
            return UNRESOLVED
        out |= r or _NONE
    return frozenset(out)


def _modules_of(
    b: ModuleBinding, recv: str, file: str, facts: _Facts, idx: ModuleIndex
) -> list[str] | None:
    """Repo files that receiver `recv` (starting with the name `b` binds) denotes; None: unknown."""
    if b.imported is None:
        assert b.module is not None
        if not idx.resolve(b.module) and not idx.resolve(b.module.split(".")[0]):
            return []  # outside the repo
        plain = b.name == b.module.split(".")[0]
        if plain and (recv == b.module or b.module.startswith(recv + ".")):
            return idx.resolve(recv) or None
        return (idx.resolve(b.module) or None) if recv == b.name and not plain else None
    sub, files = idx.files(b, file, b.imported), idx.files(b, file)
    if recv != b.name or (files and not sub):
        return None
    if any(x.name == b.imported and x.kind != "import" for f in files for x in facts[f].bindings):
        return None  # `m` is also a name defined in the package: not only a module
    return sub


def _resolve_attr(occ: Occurrence, file: str, facts: _Facts, idx: ModuleIndex) -> Resolution:
    if occ.receiver is None:
        return UNRESOLVED
    bs = [b for b in facts[file].bindings if b.name == occ.receiver.split(".")[0]]
    if not bs or any(b.kind != "import" for b in bs):
        return UNRESOLVED
    out: set[FunctionDef] = set()
    for b in bs:
        mods = _modules_of(b, occ.receiver, file, facts, idx)
        if mods is None:
            return UNRESOLVED
        for m in mods:
            r = _find(m, occ.name, 1, facts, idx)
            if r is None or isinstance(r, Unresolved):
                return UNRESOLVED
            out |= r
    return frozenset(out)


def _resolve(occ: Occurrence, file: str, facts: _Facts, idx: ModuleIndex) -> Resolution:
    ff = facts[file]
    if not ff.parsed or occ.form == "token":
        return UNRESOLVED
    head = occ.receiver.split(".")[0] if occ.form == "attr" and occ.receiver else occ.name
    if head in ff.local_import_names:  # a function- or class-local import may rebind it
        return UNRESOLVED
    if occ.form == "attr":
        return _resolve_attr(occ, file, facts, idx)
    if occ.form == "import":  # PY-S2: the alias resolves like the name it imports
        cands = [
            b
            for b in ff.bindings
            if b.kind == "import"
            and (
                b.imported == occ.name
                or (b.imported is None and occ.name in (b.module or "").split("."))
            )
        ]
        if not cands:
            return UNRESOLVED  # an import inside a function: not a module-level binding
        out: set[FunctionDef] = set()
        for b in cands:
            r = _NONE if b.imported is None else _follow(b, file, 1, facts, idx)
            if isinstance(r, Unresolved):
                return r
            out |= r
        return frozenset(out)
    if any(b.name == occ.name for b in ff.bindings):  # PY-S1 / PY-S2
        r = _find(file, occ.name, 0, facts, idx)
        return UNRESOLVED if r is None else r
    if ff.has_star_import or ff.has_dynamic_lookup or occ.in_class_body:  # PY-S7 (S5 comes later)
        return UNRESOLVED
    return _NONE  # PY-S6


def resolve(
    occ: Occurrence, file: str, facts_by_file: _Facts, module_index: ModuleIndex
) -> Resolution:
    """The definitions `occ` (found in `file`) refers to, or UNRESOLVED."""
    key = (file, occ.form, occ.name, occ.receiver, occ.in_class_body)
    if key not in module_index.memo:
        module_index.memo[key] = _resolve(occ, file, facts_by_file, module_index)
    return module_index.memo[key]
