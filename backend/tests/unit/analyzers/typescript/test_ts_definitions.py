"""Definition collection tests (TS-D1 to TS-D4, Span, exported status)."""

from __future__ import annotations

from pathlib import Path

from graveyard.analyzers.typescript.definitions import collect_definitions
from graveyard.analyzers.typescript.parser import parse


def facts(src: str, path: str = "a.ts"):
    return collect_definitions(path, src.encode(), parse(path, src.encode()))


def fns(src: str, path: str = "a.ts") -> dict:
    return {f.qualified_name: f for f in facts(src, path).functions}


def test_TS_D1_function_and_generator_declarations():
    f = fns("function a() {}\nfunction* g() {}\nasync function s() { return 1 }")
    assert set(f) == {"a", "g", "s"}
    assert [f[n].is_async_or_generator for n in "ags"] == [False, True, True]


def test_TS_D2_arrow_and_function_expression_constants():
    f = fns("const a = () => 1;\nlet b = function () {};\nvar c = function* () {};\nconst d = 5;")
    assert set(f) == {"a", "b", "c"}
    assert fns("const { a } = () => 1, [b] = x;") == {}


def test_TS_D4_anonymous_default_export_uses_basename():
    for src in ("export default function () {}", "export default () => 1"):
        f = facts(src, "src/widget.ts")
        assert [(x.name, x.is_default, x.is_exported) for x in f.functions] == [
            ("widget", True, True)
        ]
        assert f.has_default_export
    assert [
        (x.name, x.is_default) for x in facts("export default function foo() {}").functions
    ] == [("foo", True)]


def test_nested_inline_and_object_literal_functions_ignored():
    src = (
        "function outer() { function inner() {} const k = () => 1; [1].map(() => 2); }\n"
        "const o = { m() {}, n: () => 1 };\nif (x) { function cond() {} }\n"
    )
    assert set(fns(src)) == {"outer"}


def test_overloads_merged_with_span_from_first_signature():
    src = (
        "/** doc */\nfunction f(a: string): void;\nfunction f(a: number): void;\n"
        "function f(a: any) { return a }\n"
    )
    r = facts(src)
    assert [(f.start_line, f.end_line, f.body_kind) for f in r.functions] == [(2, 4, "normal")]
    assert r.overload_name_lines == {("f", 2), ("f", 3)}


def test_exported_via_export_statement_and_clause_with_alias():
    f = fns("export function a() {}\nexport const b = () => 1;\nfunction c() {}\nfunction d() {}")
    assert [f[n].is_exported for n in "abcd"] == [True, True, False, False]
    r = facts("function a() {}\nconst b = () => 1;\nfunction c() {}\nexport { a, b as z };")
    assert [x.is_exported for x in r.functions] == [True, True, False]
    assert r.exported_names == {"a", "b"}
    assert not fns("function a() {}\nexport { a } from './x';")["a"].is_exported


def test_exported_via_commonjs_forms():
    names = "abcdef"
    src = "".join(f"function {n}() {{}}\n" for n in names)
    src += (
        "module.exports = a;\nmodule.exports.x = b;\nexports.y = c;\nmodule.exports = { d, k: e };"
    )
    f = fns(src, "a.js")
    assert [f[n].is_exported for n in names] == [True, True, True, True, True, False]


def test_params_counting():
    f = fns(
        "function a(this: X, b: number, c?: string, d = 1, ...r: number[]) {}\n"
        "function z() {}\nfunction y({ p }: P, [q]: Q) {}"
    )
    assert (f["a"].params.total, f["a"].params.required, f["a"].params.has_rest) == (3, 1, True)
    assert (f["z"].params.total, f["z"].params.has_rest) == (0, False)
    assert (f["y"].params.total, f["y"].params.required) == (2, 2)


def test_stub_detection():
    f = fns(
        "function a() {}\nfunction b() { throw new Error('x') }\nfunction c() { return 1 }\n"
        "function d() { // todo\n}\nfunction e() { log(); throw 1 }"
    )
    assert [f[n].body_kind for n in "abcde"] == ["stub", "stub", "normal", "stub", "normal"]


def test_top_level_names_cover_declarations_and_imports():
    r = facts(
        "import d, { a as b, c } from 'x';\nimport * as ns from 'y';\nclass K {}\n"
        "const { p, q: [s] } = o;\ntype T = 1;\ninterface I {}\nenum E {}\nfunction f() {}\n"
    )
    assert r.top_level_names == {"d", "b", "c", "ns", "K", "p", "s", "T", "I", "E", "f"}


def test_parse_error_gives_parsed_false_and_no_definitions():
    r = facts("function f( { return")
    assert not r.parsed and r.functions == () and r.classes == ()
    assert not collect_definitions("a.ts", b"x", None).parsed


def test_script_versus_es_module():
    assert not facts("function f() {}", "a.js").is_es_module
    assert not facts("function f() {}", "a.cjs").is_es_module
    assert facts("export function f() {}", "a.js").is_es_module
    assert facts("import x from 'y'", "a.jsx").is_es_module
    assert facts("function f() {}", "a.ts").is_es_module  # TS files are always modules


def test_haunted_repo_format_ts():
    path = Path(__file__).parents[5] / "samples/haunted-repo/web/src/utils/format.ts"
    data = path.read_bytes()
    f = {x.name: x for x in collect_definitions(path.name, data, parse(path.name, data)).functions}
    assert f["formatCurrencyOld"].is_exported
    assert not f["padLeftLegacy"].is_exported
