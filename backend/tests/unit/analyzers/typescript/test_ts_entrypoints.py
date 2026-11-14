"""Entry-point exemption tests (TS-E1 to TS-E6)."""

from __future__ import annotations

from pathlib import Path

from graveyard.analyzers.typescript.definitions import collect_definitions
from graveyard.analyzers.typescript.entrypoints import exempt_rule
from graveyard.analyzers.typescript.packages import PackageIndex
from graveyard.analyzers.typescript.parser import parse

NO_PKG = PackageIndex.build({}, [])


def src_of(*heads: str) -> str:
    return "\n".join(h + " {return 1}" for h in heads)


def rules(src: str, path: str, packages: PackageIndex = NO_PKG) -> dict[str, str | None]:
    facts = collect_definitions(path, src.encode(), parse(path, src.encode()))
    classes = {c.name: c for c in facts.classes}
    return {
        f.qualified_name: exempt_rule(f, classes.get(f.class_name or ""), path, packages)
        for f in facts.functions
    }


def test_TS_E1_next_files_default_and_named_exports():
    heads = ["export default function Page()", "export function GET()"]
    src = src_of(*heads, "export function helper()", "function POST()")
    assert rules(src, "app/page.tsx") == {
        "Page": "TS-E1",
        "GET": "TS-E1",
        "helper": None,
        "POST": None,
    }
    assert rules("export default function X() {return 1}", "app/util.ts") == {"X": None}
    assert rules("export function GET() {return 1}", "app/util.ts") == {"GET": None}


def test_TS_E1_pages_directory():
    src = src_of("export default function P()", "export function getStaticProps()")
    src += "\nexport function x() {return 1}"
    assert rules(src, "src/pages/about.tsx") == {"P": "TS-E1", "getStaticProps": "TS-E1", "x": None}


def test_TS_E1_haunted_sample_page():
    path = (
        Path(__file__).parents[5] / "samples" / "haunted-repo" / "web" / "src" / "app" / "page.tsx"
    )
    assert path.exists()
    src = path.read_bytes()
    facts = collect_definitions("web/src/app/page.tsx", src, parse("web/src/app/page.tsx", src))
    page = next(f for f in facts.functions if f.name == "Page")
    assert exempt_rule(page, None, "web/src/app/page.tsx", NO_PKG) == "TS-E1"


def test_TS_E2_route_modules():
    heads = ["export function loader()", "export function other()"]
    src = src_of(*heads, "export default function R()")
    assert rules(src, "app/routes/home.tsx") == {"loader": "TS-E2", "other": None, "R": "TS-E2"}
    assert rules("export function loader() {return 1}", "app/home.tsx") == {"loader": None}
    assert rules("export function load() {return 1}", "src/x/+page.server.ts") == {"load": "TS-E2"}
    assert rules("export function load() {return 1}", "src/x/other.ts") == {"load": None}
    h = "export default function H() {return 1}"
    assert rules(h, "netlify/functions/h.ts") == {"H": "TS-E2"}
    assert rules("export default function H() {return 1}", "src/lib/h.ts") == {"H": None}


def test_TS_E3_entry_files_at_package_root_or_src():
    src = "export default function run() {return 1}"
    assert rules(src, "main.ts") == {"run": "TS-E3"}
    assert rules(src, "src/app.ts") == {"run": "TS-E3"}
    assert rules(src, "src/lib/app.ts") == {"run": None}
    assert rules("export function run() {return 1}", "src/app.ts") == {"run": None}
    pkgs = PackageIndex.build({"svc/package.json": b"{}"}, ["svc/src/server.ts", "src/server.ts"])
    assert rules(src, "svc/src/server.ts", pkgs) == {"run": "TS-E3"}
    assert rules(src, "src/server.ts", pkgs) == {"run": "TS-E3"}
    assert rules(src, "svc/src/lib/server.ts", pkgs) == {"run": None}


def test_TS_E4_framework_method_names():
    src = "class A { render() {return 1} renderOld() {return 1} }\nfunction render() {return 1}"
    assert rules(src, "a.ts") == {"A.render": "TS-E4", "A.renderOld": None, "render": None}


def test_TS_E5_decorators():
    src = (
        "class A { @Get() a() {return 1} b() {return 1} }\n"
        "@Injectable()\nclass B { c() {return 1} }\n"
        "class C { d() {return 1} }"
    )
    assert rules(src, "a.ts") == {
        "A.a": "TS-E5",
        "A.b": None,
        "B.c": "TS-E5",
        "C.d": None,
    }


def test_TS_E6_stubs_and_abstract():
    src = (
        "function over(a: string): void;\nfunction over(a: any) { return 1 }\n"
        "function empty() {}\nfunction thrower() { throw new Error('x') }\n"
        "abstract class A { abstract m(): void; n() {return 1} }"
    )
    r = rules(src, "a.ts")
    assert r["empty"] == r["thrower"] == r["A.m"] == "TS-E6"
    assert r["A.n"] is None
