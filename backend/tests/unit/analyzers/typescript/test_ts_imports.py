"""Dead TypeScript imports (Requirement 7)."""

from __future__ import annotations

from pathlib import Path

from graveyard.analyzers.typescript.definitions import collect_definitions
from graveyard.analyzers.typescript.imports import collect_import_bindings, dead_imports
from graveyard.analyzers.typescript.parser import parse
from graveyard.analyzers.typescript.references import collect_occurrences
from graveyard.models import Flag

SAMPLE = Path(__file__).resolve().parents[5] / "samples" / "haunted-repo"


def _run(src: str, path: str = "a.ts", dynamic: bool = False):
    return _run_bytes(src.encode(), path, dynamic)


def _run_bytes(data: bytes, path: str, dynamic: bool = False):
    tree = parse(path, data)
    assert tree is not None
    return dead_imports(
        path,
        collect_import_bindings(tree, data),
        collect_occurrences(tree, data),
        collect_definitions(path, data, tree),
        data,
        dynamic,
        tree,
    )


def _names(src: str, path: str = "a.ts") -> list[str]:
    return [c.name for c in _run(src, path)]


def test_unused_named_default_namespace():
    src = 'import a from "x";\nimport * as ns from "y";\nimport { b as c } from "z";\n'
    assert _names(src) == ["a", "ns", "c"]


def test_unused_type_imports():
    assert _names('import type { A } from "x";\nimport { type B, C } from "y";\nC;\n') == ["A", "B"]


def test_used_in_type_position():
    assert _names('import { T } from "x";\nlet v: T;\n') == []


def test_used_only_in_jsx():
    assert _names('import { Foo } from "x";\nconst e = <Foo />;\n', "a.tsx") == []


def test_namespace_member_and_typeof():
    src = 'import * as utils from "x";\nimport d from "y";\nutils.fn();\ntype T = typeof d;\n'
    assert _names(src) == []


def test_same_named_property_is_not_a_use():
    assert _names('import { fn } from "x";\nobj.fn();\n') == ["fn"]


def test_reexported_via_export_clause():
    assert _names('import { x } from "a";\nexport { x };\n') == []


def test_react_default_kept_in_tsx_only():
    src = 'import React from "react";\n'
    assert _names(src, "a.tsx") == []
    assert _names(src, "a.ts") == ["React"]


def test_jsx_pragma_keeps_binding():
    src = '/** @jsx h */\nimport { h } from "preact";\nimport { g } from "q";\n'
    assert _names(src, "a.tsx") == ["g"]


def test_side_effect_import_ignored():
    assert _names('import "./x";\n') == []


def test_suppression_comments():
    assert _names('// eslint-disable-next-line\nimport { a } from "x";\n') == []
    assert _names('import { a } from "x"; // @ts-expect-error\n') == []
    assert _names('import { a } from "x";\n') == ["a"]


def test_parse_error_file_gives_nothing():
    assert _names('import { a } from "x";\nfunction (( {\n') == []


def test_partial_statement_and_dynamic_flags():
    got = _run('import { a, b } from "x";\nb;\n', dynamic=True)
    assert [c.name for c in got] == ["a"]
    assert got[0].flags == {Flag.PARTIAL_STATEMENT, Flag.DYNAMIC_PATTERN_IN_FILE}
    assert got[0].kind == "import" and got[0].language == "typescript"


def test_multiline_statement_range():
    got = _run('import {\n  a,\n  b,\n} from "x";\n')
    assert [(c.start_line, c.end_line, c.flags) for c in got] == [(1, 4, frozenset())] * 2


def _sample(rel: str) -> list[str]:
    found = _run_bytes((SAMPLE / rel).read_bytes(), rel)
    return [f"{c.name}:{sorted(f.name for f in c.flags)}" for c in found]


def test_haunted_sample():
    assert _sample("web/src/components/Cart.tsx") == ["useMemo:['PARTIAL_STATEMENT']"]
    assert _sample("web/src/lib/api.ts") == ["User:[]"]
    assert _sample("web/src/app/page.tsx") == []
