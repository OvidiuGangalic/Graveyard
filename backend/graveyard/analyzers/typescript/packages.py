"""package.json facts and import specifier resolution (design: "Specifier resolution", TS-R7)."""

from __future__ import annotations

import json
import posixpath
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_JS_TO_TS = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}
_DEP_KEYS = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
_LIB_KEYS = ("main", "module", "exports", "types", "typings", "bin")
_ALIAS_PREFIXES = ("./", "../", "@/", "~/", "src/")


@dataclass(frozen=True)
class PackageInfo:
    dir: str  # "" for the repo root
    name: str | None
    private: bool
    is_library: bool
    entry_files: frozenset[str]
    dependencies: frozenset[str]


def _strings(value: object) -> list[str]:
    """Every string in a package.json field: a string, or any depth of lists and objects."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _parse(pkg_dir: str, d: dict[str, object], sources: frozenset[str]) -> PackageInfo:
    private = d.get("private") is True
    entries: set[str] = set()
    for key in _LIB_KEYS:
        for s in _strings(d.get(key)):
            path = posixpath.normpath(posixpath.join(pkg_dir, s.removeprefix("./")))
            entries.add(path)
            # Packages often point main at build output; also accept a sibling TS source.
            stem, ext = posixpath.splitext(path)
            entries.update(stem + e for e in _JS_TO_TS.get(ext, ()) if stem + e in sources)
    deps: set[str] = set()
    for key in _DEP_KEYS:
        section = d.get(key)
        if isinstance(section, dict):
            deps.update(section)
    name = d.get("name")
    return PackageInfo(
        dir=pkg_dir,
        name=name if isinstance(name, str) else None,
        private=private,
        is_library=not private and any(k in d for k in _LIB_KEYS),
        entry_files=frozenset(entries),
        dependencies=frozenset(deps),
    )


def _package_name(spec: str) -> str:
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") else parts[0]


class PackageIndex:
    """Every package.json in the repo, keyed by directory."""

    def __init__(self, packages: Iterable[PackageInfo]) -> None:
        self._by_dir = {p.dir: p for p in packages}
        self._by_name: dict[str, PackageInfo] = {}
        for p in sorted(self._by_dir.values(), key=lambda p: p.dir):
            if p.name:
                self._by_name.setdefault(p.name, p)
        self._deps = frozenset(n for p in self._by_dir.values() for n in p.dependencies)

    @classmethod
    def build(cls, package_files: Mapping[str, bytes], source_paths: Iterable[str]) -> PackageIndex:
        sources = frozenset(source_paths)
        found = []
        for path, raw in package_files.items():
            if posixpath.basename(path) != "package.json":
                continue
            try:
                data = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                continue  # unreadable or invalid: treated as absent
            if isinstance(data, dict):
                found.append(_parse(posixpath.dirname(path), data, sources))
        return cls(found)

    def package_for(self, path: str) -> PackageInfo | None:
        """Nearest ancestor package.json; None means the application package."""
        d = posixpath.dirname(path)
        while True:
            if d in self._by_dir:
                return self._by_dir[d]
            if not d:
                return None
            d = posixpath.dirname(d)

    def workspace(self, name: str) -> PackageInfo | None:
        return self._by_name.get(name)

    def external(self, spec: str) -> bool:
        if spec.startswith("node:"):
            return True
        name = _package_name(spec)
        return name in self._deps and name not in self._by_name


def _suffix_key(spec: str) -> tuple[str, ...]:
    rest, stripped = spec, True
    while stripped:
        stripped = False
        for prefix in _ALIAS_PREFIXES:
            if rest.startswith(prefix):
                rest, stripped = rest[len(prefix) :], True
    stem, ext = posixpath.splitext(rest)
    if ext in _EXTS:
        rest = stem
    rest = rest.removesuffix("/index").strip("/")
    return tuple(rest.split("/")) if rest and rest != "index" else ()


def _suffix_match(spec: str, paths: Iterable[str]) -> frozenset[str]:
    """TS-R7: whole-segment suffix of the file path without extension (or of its directory)."""
    key = _suffix_key(spec)
    if not key:
        return frozenset()
    n = len(key)
    out = set()
    for path in paths:
        parts = tuple(posixpath.splitext(path)[0].split("/"))
        if parts[-n:] == key or (parts[-1] == "index" and parts[-n - 1 : -1] == key):
            out.add(path)
    return frozenset(out)


def _relative(spec: str, from_file: str, sources: frozenset[str]) -> frozenset[str]:
    base = posixpath.normpath(posixpath.join(posixpath.dirname(from_file), spec))
    stem, ext = posixpath.splitext(base)
    candidates = [base]
    if ext in _JS_TO_TS:  # TS writes "./x.js" for x.ts
        candidates += [stem + e for e in _JS_TO_TS[ext]]
    candidates += [base + e for e in _EXTS] + [f"{base}/index{e}" for e in _EXTS]
    for c in candidates:
        if c in sources:
            return frozenset({c})
    return frozenset()


def resolve_specifier(
    spec: str, from_file: str, index: PackageIndex, source_paths: Iterable[str]
) -> frozenset[str] | None:
    """Repo files the specifier means; frozenset() for none in the repo; None for unresolved."""
    sources = frozenset(source_paths)
    if spec in (".", "..") or spec.startswith(("./", "../")):
        return _relative(spec, from_file, sources)
    if spec.startswith(("@/", "~/")):
        return _suffix_match(spec, sources) or None
    name = _package_name(spec)
    pkg = index.workspace(name)
    if pkg is not None:
        files = sorted(f for f in sources if index.package_for(f) is pkg)
        subpath = spec[len(name) :].lstrip("/")
        if subpath:
            return _suffix_match(subpath, files)
        # No subpath: the entry point may re-export anything, so use the entry files when
        # they are known source files, else the whole package.
        return (pkg.entry_files & sources) or frozenset(files)
    if index.external(spec):
        return frozenset()
    if "/" not in spec and not spec.startswith(("~", "@")):
        return frozenset()  # looks like a package name; TS-R7 never matches bare specifiers
    return _suffix_match(spec, sources) or None
