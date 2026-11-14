"""Reference, specifier, string and dynamic-pattern facts for TypeScript sources."""

from __future__ import annotations

import pytest

from graveyard.analyzers.typescript.parser import parse
from graveyard.analyzers.typescript.references import (
    collect_occurrences,
    collect_specifiers,
    collect_strings,
    dynamic_patterns,
)


def _tree(src: str, path: str = "a.ts"):
    tree = parse(path, src.encode())
    assert tree is not None
    return tree


def test_template_substitutions_are_code_not_strings():
    src = "const s = `Updated ${formatDate(d)} ok`;"
    occ = collect_occurrences(_tree(src), src.encode())
    assert ("formatDate", "name") in [(o.name, o.form) for o in occ]
    assert [t for t, _ in collect_strings(_tree(src))] == ["Updated ", " ok"]


@pytest.mark.parametrize("path", ["a.ts", "a.tsx", "a.js"])
def test_specifier_kinds_table(path):
    src = "\n".join(
        [
            'import x from "s1";',
            'import { a as b } from "s2";',
            'import * as ns from "s3";',
            'export { a } from "s4";',
            'export * from "s5";',
            'const { c: d } = require("s6");',
            'const all = require("s7");',
            'import("s8");',
            "import(expr);",
        ]
    )
    got = [(s.spec, s.line, s.kind, s.names) for s in collect_specifiers(_tree(src, path))]
    assert got == [
        ("s1", 1, "static", (("default", "x"),)),
        ("s2", 2, "static", (("a", "b"),)),
        ("s3", 3, "static", (("*", "ns"),)),
        ("s4", 4, "reexport", (("a", "a"),)),
        ("s5", 5, "reexport_all", ()),
        ("s6", 6, "require", (("c", "d"),)),
        ("s7", 7, "require", (("*", "all"),)),
        ("s8", 8, "dynamic", ()),
    ]


def test_strings_exclude_specifiers_and_import_require_arguments():
    src = (
        'import a from "m1";\nexport * from "m2";\nrequire("m3");\nimport("m4");\nconst s = "keep";'
    )
    assert collect_strings(_tree(src)) == (("keep", 5),)


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("eval(code);", (True, False)),
        ("new Function('return 1');", (True, False)),
        ("this[name];", (True, False)),
        ("window[k] = 1;", (True, False)),
        ("module.exports[k];", (True, False)),
        ("import(path);", (True, False)),
        ("obj[expr](1);", (False, True)),
        ("this['fixed']; obj['m'](1); import('lit'); evaluate(1);", (False, False)),
        ("const o = {}; o[k];", (False, False)),
    ],
)
def test_dynamic_patterns(src, expected):
    assert dynamic_patterns(_tree(src)) == expected
