"""PackageIndex and resolve_specifier (spec 03 tasks 6.2, 6.4)."""

from __future__ import annotations

import json
from pathlib import Path

from graveyard.analyzers.typescript.packages import PackageIndex, resolve_specifier

SAMPLE = Path(__file__).resolve().parents[5] / "samples" / "haunted-repo"


def test_library_private_and_absent() -> None:
    idx = PackageIndex.build(
        {
            "lib/package.json": b'{"name": "lib", "main": "index.js"}',
            "app/package.json": b'{"name": "app", "private": true, "main": "x.js"}',
            "tool/package.json": b'{"name": "tool"}',
        },
        [],
    )
    assert idx.package_for("lib/index.ts").is_library  # type: ignore[union-attr]
    assert not idx.package_for("app/a.ts").is_library  # type: ignore[union-attr]
    assert not idx.package_for("tool/t.ts").is_library  # type: ignore[union-attr]
    assert idx.package_for("other/b.ts") is None


def test_entry_files_with_exports_and_js_to_ts_mapping() -> None:
    pkg = {
        "main": "./dist/index.js",
        "types": "src/types.d.ts",
        "exports": {".": {"import": "./src/a.js", "require": ["./src/b.cjs"]}},
        "bin": {"cli": "bin/cli.js"},
    }
    idx = PackageIndex.build(
        {"p/package.json": json.dumps(pkg).encode()}, ["p/src/a.ts", "p/src/b.cjs"]
    )
    info = idx.package_for("p/src/a.ts")
    assert info is not None
    assert info.entry_files == {
        "p/dist/index.js",
        "p/src/types.d.ts",
        "p/src/a.js",
        "p/src/a.ts",
        "p/src/b.cjs",
        "p/bin/cli.js",
    }


def test_invalid_package_json_ignored_and_nearest_ancestor() -> None:
    idx = PackageIndex.build(
        {
            "package.json": b'{"name": "root"}',
            "a/package.json": b"{not json",
            "a/b/package.json": b'{"name": "inner"}',
            "c/package.json": b"[1]",
        },
        [],
    )
    assert idx.package_for("a/x.ts").name == "root"  # type: ignore[union-attr]
    assert idx.package_for("a/b/c/x.ts").name == "inner"  # type: ignore[union-attr]
    assert idx.package_for("c/x.ts").name == "root"  # type: ignore[union-attr]


SOURCES = [
    "packages/sdk/src/index.ts",
    "packages/sdk/src/client.ts",
    "packages/sdk/src/util/fmt.ts",
    "web/src/lib/api.ts",
    "web/src/utils/dates.ts",
    "web/src/widgets/index.tsx",
    "web/src/mylib/api.ts",
    "web/src/app/page.tsx",
]
PACKAGES = {
    "packages/sdk/package.json": b'{"name": "@haunted/sdk", "main": "src/index.ts"}',
    "web/package.json": json.dumps(
        {"name": "web", "private": True, "dependencies": {"react": "1", "@haunted/sdk": "*"}}
    ).encode(),
}
INDEX = PackageIndex.build(PACKAGES, SOURCES)


def _r(spec: str, frm: str = "web/src/app/page.tsx") -> frozenset[str] | None:
    return resolve_specifier(spec, frm, INDEX, SOURCES)


def test_workspace_and_external() -> None:
    assert INDEX.workspace("@haunted/sdk").dir == "packages/sdk"  # type: ignore[union-attr]
    assert INDEX.workspace("react") is None
    assert INDEX.external("react") and INDEX.external("react/jsx-runtime")
    assert INDEX.external("node:fs")
    assert not INDEX.external("@haunted/sdk") and not INDEX.external("lodash")


def test_relative() -> None:
    assert _r("../lib/api") == {"web/src/lib/api.ts"}
    assert _r("../lib/api.ts") == {"web/src/lib/api.ts"}
    assert _r("../lib/api.js") == {"web/src/lib/api.ts"}
    assert _r("../widgets") == {"web/src/widgets/index.tsx"}
    assert _r("./sibling", "web/src/lib/api.ts") == frozenset()
    assert _r("../../../../etc/x") == frozenset()


def test_alias_suffix_match() -> None:
    assert _r("@/lib/api") == {"web/src/lib/api.ts"}  # whole segments: not mylib/api.ts
    assert _r("@/mylib/api") == {"web/src/mylib/api.ts"}
    assert _r("~/utils/dates") == {"web/src/utils/dates.ts"}
    assert _r("src/utils/dates") == {"web/src/utils/dates.ts"}
    assert _r("@/widgets") == {"web/src/widgets/index.tsx"}
    assert _r("@/missing/thing") is None
    assert _r("@components/Button") is None


def test_workspace_and_external_resolution() -> None:
    assert _r("@haunted/sdk") == {"packages/sdk/src/index.ts"}
    assert _r("@haunted/sdk/util/fmt") == {"packages/sdk/src/util/fmt.ts"}
    assert _r("@haunted/sdk/nothing") is None  # e.g. build output: unresolved, not "nothing"
    assert _r("react") == frozenset()
    assert _r("node:fs") == frozenset()
    assert _r("lodash") == frozenset()  # undeclared package, no repo file of that name
    assert _r("dates") == {"web/src/utils/dates.ts"}  # tsconfig baseUrl import of a repo file


def test_workspace_without_entry_files_uses_whole_package() -> None:
    paths = ["p/a.ts", "p/b.ts", "q/c.ts"]
    idx = PackageIndex.build({"p/package.json": b'{"name": "p"}'}, paths)
    assert resolve_specifier("p", "q/c.ts", idx, paths) == {"p/a.ts", "p/b.ts"}


def test_haunted_sample() -> None:
    sources = [
        p.relative_to(SAMPLE).as_posix()
        for p in SAMPLE.rglob("*")
        if p.suffix in (".ts", ".tsx") and "node_modules" not in p.parts
    ]
    pkgs = {p.relative_to(SAMPLE).as_posix(): p.read_bytes() for p in SAMPLE.rglob("package.json")}
    idx = PackageIndex.build(pkgs, sources)
    page = "web/src/app/page.tsx"
    assert resolve_specifier("@haunted/sdk", page, idx, sources) == {"packages/sdk/src/index.ts"}
    assert idx.package_for("packages/sdk/src/index.ts").is_library  # type: ignore[union-attr]
    web = idx.package_for(page)
    assert web is not None and web.private and not web.is_library
