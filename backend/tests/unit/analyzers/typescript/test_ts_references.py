"""Reference, specifier, string and dynamic-pattern facts for TypeScript sources."""

from __future__ import annotations

from pathlib import Path

import pytest

from graveyard.analyzers.typescript.parser import parse
from graveyard.analyzers.typescript.references import collect_occurrences


def _tree(src: str, path: str = "a.ts"):
    tree = parse(path, src.encode())
    assert tree is not None
    return tree


def _occ(src: str, path: str = "a.ts", skip=frozenset()):
    return collect_occurrences(_tree(src, path), src.encode(), skip)


def _pairs(src: str, path: str = "a.ts"):
    return [(o.name, o.form) for o in _occ(src, path)]


def test_TS_R1_identifiers_except_the_definition_name():
    assert _pairs("function f() { g(x); }") == [("g", "name"), ("x", "name")]
    assert _pairs("class A {}\nnew B();") == [("B", "name")]


def test_TS_R1_overload_signature_names_are_skipped():
    src = "function f(a: number): void;\nfunction f(a: any) {}\nf(1);"
    names = [(o.name, o.line) for o in _occ(src, skip=frozenset({("f", 1)})) if o.name == "f"]
    assert names == [("f", 3)]


def test_TS_R2_member_property_identifiers():
    assert ("save", "member") in _pairs("store.save();")


def test_TS_R3_shorthand_properties_and_patterns():
    assert ("f", "name") in _pairs("const o = { f };")
    assert ("save", "member") in _pairs("const { save } = store;")


def test_TS_R4_type_identifiers_and_typeof():
    pairs = _pairs("let a: Foo; let b: typeof bar; interface Baz {}")
    assert ("Foo", "type") in pairs and ("bar", "type") in pairs
    assert all(n != "Baz" for n, _ in pairs)


def test_TS_R5_jsx_names_and_nested_member_parts():
    occ = _occ("const e = <ui.Banner />;", "a.tsx")
    assert [(o.name, o.form, o.receiver) for o in occ if o.form == "jsx"] == [
        ("ui", "jsx", None),
        ("Banner", "jsx", "ui"),
    ]
    deep = [o.name for o in _occ("const e = <A.B.C></A.B.C>;", "a.tsx") if o.form == "jsx"]
    assert deep == ["A", "B", "C"]
    assert ("div", "jsx") not in _pairs("const e = <div />;", "a.tsx")


def test_TS_R6_specifier_names_not_aliases():
    occ = _occ('import { a as b } from "m"; export { c as d };')
    assert [(o.name, o.form) for o in occ] == [("a", "specifier"), ("c", "specifier")]


@pytest.mark.parametrize(
    ("src", "name", "receiver"),
    [
        ("this.x;", "x", "this"),
        ("class A extends B { m() { super.y; } }", "y", "super"),
        ("a.b.c;", "c", "a.b"),
        ("f().x;", "x", None),
        ("a[0].x;", "x", None),
    ],
)
def test_receiver_forms(src, name, receiver):
    assert next(o for o in _occ(src) if o.name == name and o.form == "member").receiver == receiver


def test_call_args_spread_and_enclosing_class():
    occ = {o.name: o for o in _occ("class K { m() { f(1, 2); this.g(...a); h; } }")}
    assert (occ["f"].call_args, occ["f"].call_has_spread) == (2, False)
    assert (occ["g"].call_args, occ["g"].call_has_spread) == (1, True)
    assert occ["h"].call_args is None
    assert occ["f"].enclosing_class == "K"
    assert _occ("f();")[0].enclosing_class is None


def test_parse_error_falls_back_to_tokens():
    src = "function f( {\n  call_me($x) return"
    occ = _occ(src)
    assert {o.form for o in occ} == {"token"}
    assert [(o.name, o.line) for o in occ if o.name in {"call_me", "$x"}] == [
        ("call_me", 2),
        ("$x", 2),
    ]


def test_cart_tsx_sample():
    path = Path(__file__).parents[5] / "samples/haunted-repo/web/src/components/Cart.tsx"
    data = path.read_bytes()
    tree = parse("Cart.tsx", data)
    occ = collect_occurrences(tree, data)
    pairs = {(o.name, o.form) for o in occ}
    assert {
        ("formatDate", "name"),
        ("Banner", "jsx"),
        ("formatCurrency", "name"),
        ("useState", "name"),
    } <= pairs
    assert [o.form for o in occ if o.name == "useMemo"] == ["specifier"]
