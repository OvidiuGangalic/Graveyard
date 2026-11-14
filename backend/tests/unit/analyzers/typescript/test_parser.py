"""Parser wrapper tests, including the node-type probes behind the TS design tables."""

from __future__ import annotations

import pytest

from graveyard.analyzers.typescript.parser import (
    end_line,
    grammar_for,
    has_error,
    line,
    parse,
    text,
    walk,
)


def _tree(path: str, src: str):
    tree = parse(path, src.encode())
    assert tree is not None
    return tree


@pytest.mark.parametrize(
    ("path", "grammar"),
    [
        ("a.ts", "ts"),
        ("a.tsx", "tsx"),
        ("a.js", "js"),
        ("a.jsx", "js"),
        ("a.mjs", "js"),
        ("a.cjs", "js"),
        ("A.TS", "ts"),
    ],
)
def test_grammar_per_extension(path, grammar):
    assert grammar_for(path) == grammar


def test_tsx_and_js_parse_jsx_but_ts_does_not():
    src = "const e = <div>hi</div>;"
    assert not has_error(_tree("a.tsx", src))
    assert not has_error(_tree("a.jsx", src))
    assert has_error(_tree("a.ts", src))


def test_has_error_on_broken_input():
    assert not has_error(_tree("a.ts", "function f() { return 1; }"))
    assert has_error(_tree("a.ts", "function f( { return"))
    assert has_error(_tree("a.js", "const = ;"))


def test_walk_is_preorder_and_stays_inside_the_node():
    tree = _tree("a.ts", "f(a, b); g();")
    stmt = tree.root_node.children[1]
    assert [n.type for n in walk(stmt)] == [
        "expression_statement",
        "call_expression",
        "identifier",
        "arguments",
        "(",
        ")",
        ";",
    ]
    assert [n.type for n in walk(tree.root_node)][:3] == [
        "program",
        "expression_statement",
        "call_expression",
    ]


def test_walk_deeply_nested_input_does_not_recurse():
    depth = 5000
    tree = _tree("a.ts", "x = " + "(" * depth + "1" + ")" * depth + ";")
    assert sum(1 for n in walk(tree.root_node) if n.type == "parenthesized_expression") == depth
    tree = _tree("a.js", "x = " + "[" * depth + "]" * depth + ";")
    assert sum(1 for _ in walk(tree.root_node)) > depth


@pytest.mark.parametrize("path", ["a.ts", "a.tsx", "a.js"])
def test_arbitrary_bytes_never_raise(path):
    for data in (b"", b"\x00\xff\xfe", bytes(range(256)) * 20, b"\xef\xbb\xbfclass {", b"`${"):
        tree = parse(path, data)
        assert tree is not None
        list(walk(tree.root_node))
        text(tree.root_node)


def test_text_and_lines():
    tree = _tree("a.ts", "// caf\xe9\nfunction f() {\n}\n")
    fn = tree.root_node.children[1]
    assert (line(fn), end_line(fn)) == (2, 3)
    assert text(fn) == "function f() {\n}"
    bad = parse("a.js", b"x = '\xff';")
    assert "�" in text(bad.root_node)


# (path, source, node type, expected parent type): the grammar facts the design relies on.
_NODES = [
    ("a.ts", "abstract class A {}", "abstract_class_declaration", "program"),
    ("a.ts", "class A {}", "type_identifier", "class_declaration"),
    ("a.js", "class A {}", "identifier", "class_declaration"),
    ("a.ts", "export default function () {}", "function_expression", "export_statement"),
    ("a.ts", "export default () => 1", "arrow_function", "export_statement"),
    ("a.ts", "export default function* () {}", "generator_function", "export_statement"),
    ("a.ts", "export default function f() {}", "function_declaration", "export_statement"),
    ("a.ts", "class C { @d m() {} }", "decorator", "class_body"),
    ("a.ts", "@d class C {}", "decorator", "class_declaration"),
    ("a.ts", "@d export class C {}", "decorator", "export_statement"),
    ("a.ts", "function f(a: string): void; function f(a: any) {}", "function_signature", "program"),
    ("a.ts", "abstract class A { abstract m(): void }", "abstract_method_signature", "class_body"),
    ("a.ts", "class C { constructor() {} }", "method_definition", "class_body"),
    ("a.ts", "class C { p = () => 1 }", "public_field_definition", "class_body"),
    ("a.ts", "function f(a = 1) {}", "required_parameter", "formal_parameters"),
    ("a.ts", "function f(a?: number) {}", "optional_parameter", "formal_parameters"),
    ("a.ts", "function f(...r: number[]) {}", "rest_pattern", "required_parameter"),
    ("a.ts", "function f(this: X) {}", "this", "required_parameter"),
    ("a.ts", "import d from 'x'", "identifier", "import_clause"),
    ("a.ts", "import * as n from 'x'", "namespace_import", "import_clause"),
    ("a.ts", "import * as n from 'x'", "identifier", "namespace_import"),
    ("a.ts", "import { a as b } from 'x'", "import_specifier", "named_imports"),
    ("a.ts", "export { a as b }", "export_specifier", "export_clause"),
    ("a.ts", "let t: typeof x", "type_query", "type_annotation"),
    ("a.tsx", "<A.B.C />", "member_expression", "jsx_self_closing_element"),
    ("a.tsx", "<A.B.C />", "member_expression", "member_expression"),
    ("a.jsx", "<A.B />", "member_expression", "jsx_self_closing_element"),
    ("a.ts", "`a${b}c`", "string_fragment", "template_string"),
    ("a.ts", "`a${b}c`", "template_substitution", "template_string"),
    ("a.ts", "o[k](1)", "subscript_expression", "call_expression"),
    ("a.ts", "import('x')", "import", "call_expression"),
    ("a.js", "import('x')", "import", "call_expression"),
    ("a.ts", "const f = function () {}", "function_expression", "variable_declarator"),
    ("a.ts", "const f = function* () {}", "generator_function", "variable_declarator"),
    ("a.ts", "function* g() {}", "generator_function_declaration", "program"),
    ("a.ts", "export * from 'x'", "export_statement", "program"),
    ("a.js", "import { a } from 'x'; import * as n from 'y'", "import_specifier", "named_imports"),
    ("a.js", "const e = <A />", "jsx_self_closing_element", "variable_declarator"),
    ("a.js", "class C { m() {} }", "method_definition", "class_body"),
    ("a.ts", "o.p", "property_identifier", "member_expression"),
    ("a.ts", "({ a })", "shorthand_property_identifier", "object"),
    ("a.ts", "const { a } = o", "shorthand_property_identifier_pattern", "object_pattern"),
]


@pytest.mark.parametrize(("path", "src", "node_type", "parent_type"), _NODES)
def test_design_node_types(path, src, node_type, parent_type):
    tree = _tree(path, src)
    assert any(
        n.type == node_type and n.parent is not None and n.parent.type == parent_type
        for n in walk(tree.root_node)
    )


def _first(tree, node_type):
    return next(n for n in walk(tree.root_node) if n.type == node_type)


def test_accessors_have_anonymous_get_set_children():
    tree = _tree("a.ts", "class C { get x() { return 1 } set x(v) {} }")
    getter, setter = (n for n in walk(tree.root_node) if n.type == "method_definition")
    assert "get" in [c.type for c in getter.children]
    assert "set" in [c.type for c in setter.children]


def test_constructor_is_a_method_definition_named_constructor():
    method = _first(_tree("a.ts", "class C { constructor() {} }"), "method_definition")
    assert text(method.child_by_field_name("name")) == "constructor"


def test_field_names_the_design_relies_on():
    tree = _tree("a.ts", "export default () => 1; function f(a = 1) {}")
    assert _first(tree, "export_statement").child_by_field_name("value").type == "arrow_function"
    assert _first(tree, "required_parameter").child_by_field_name("value") is not None
    tree = _tree("a.ts", "export default function f() {}")
    assert _first(tree, "export_statement").child_by_field_name("declaration") is not None
    tree = _tree("a.ts", "class C { @d m() {} }")
    assert _first(tree, "decorator").parent.children[1].type == "decorator"


def test_type_import_markers_are_anonymous_tokens():
    tree = _tree("a.ts", "import type T from 'x'; import { type U } from 'y'")
    assert not any(n.type == "type" and n.is_named for n in walk(tree.root_node))
    assert "type" in [c.type for c in _first(tree, "import_statement").children]
    spec = _first(tree, "import_specifier")
    assert spec.child_by_field_name("name") is not None
    assert "type" in [c.type for c in spec.children]
