from __future__ import annotations

from pathlib import Path

import pytest

from graveyard.analyzers.python.definitions import collect_definitions, parse_module
from graveyard.analyzers.python.imports import (
    collect_import_bindings,
    dead_imports,
    reexport_pairs,
)
from graveyard.analyzers.python.references import collect_occurrences
from graveyard.models import Candidate, Flag

HAUNTED = Path(__file__).parents[5] / "samples" / "haunted-repo"


def dead(src: str, path: str = "m.py", reexported: set[tuple[str, str]] | None = None):
    tree = parse_module(src)
    facts = collect_definitions(path, src, tree)
    if tree is None:
        return dead_imports(path, (), (), facts)
    bindings = collect_import_bindings(path, tree, facts.lines)
    return dead_imports(path, bindings, collect_occurrences(src, tree), facts, reexported or ())


def names(found: list[Candidate]) -> list[str]:
    return [c.name for c in found]


def test_PY_I1_init_file_never_reported() -> None:
    assert dead("import os\n", "pkg/__init__.py") == []


def test_PY_I2_dunder_all_never_reported() -> None:
    assert dead("from os import path\n__all__ = ['path']\n") == []


def test_PY_I3_future_never_reported() -> None:
    assert dead("from __future__ import annotations\n") == []


def test_PY_I4_star_never_reported() -> None:
    assert dead("from os.path import *\n") == []


@pytest.mark.parametrize("comment", ["# noqa", "# noqa: F401", "# type: ignore"])
def test_PY_I5_noqa_first_or_last_line(comment: str) -> None:
    assert dead(f"import os  {comment}\n") == []
    assert dead(f"from os import (\n    path,\n)  {comment}\n") == []
    assert dead(f"from os import (  {comment}\n    path,\n)\n") == []


def test_PY_I6_reexported_through_module() -> None:
    assert dead("import os\n", "pkg/util.py", {("util", "os")}) == []
    assert names(dead("import os\n", "pkg/util.py", {("other", "os")})) == ["os"]


def test_PY_I6_reexport_pairs_from_bindings() -> None:
    def pairs(src: str) -> set[tuple[str, str]]:
        return reexport_pairs({"x.py": collect_definitions("x.py", src).bindings})

    assert pairs("from a.b import c as d\nimport e.f\nfrom . import g\n") == {("b", "c")}


def test_PY_I7_unparseable_file_not_reported() -> None:
    assert dead("import os\ndef (:\n") == []


def test_PY_I7_import_a_b_used_by_prefix() -> None:
    assert dead("import os.path\nos.getcwd()\n") == []
    assert names(dead("import os.path\n")) == ["os.path"]


def test_used_via_attribute_name_and_call() -> None:
    assert dead("import json\nprint(json.dumps({}))\n") == []
    assert dead("from typing import Optional\ndef f(x=Optional): ...\n") == []


def test_used_only_in_string_annotation() -> None:
    assert dead("from typing import List\ndef f(a: 'List[int]'): ...\n") == []


def test_used_only_in_type_comment() -> None:
    assert dead("from typing import List\nx = []  # type: List[int]\n") == []


def test_assignment_to_bound_name_is_not_a_use() -> None:
    assert names(dead("import json\njson = None\n")) == ["json"]


def test_alias_names_by_what_is_imported() -> None:
    assert [(c.name, c.qualified_name) for c in dead("import a.b as c\n")] == [("a.b", "a.b")]
    assert names(dead("from m import x as y\n")) == ["x"]
    assert dead("from m import x as y\nprint(y)\n") == []
    assert names(dead("from m import x as y\nprint(x)\n")) == ["x"]


def test_multiline_import_gives_full_range_and_snippet() -> None:
    (c,) = dead("x = 1\nfrom os import (\n    path,\n)\n")
    assert (c.start_line, c.end_line) == (2, 4)
    assert c.code_snippet == "from os import (\n    path,\n)"
    assert (c.kind, c.language, c.test_coverage, c.callers) == ("import", "python", "unknown", ())


def test_flag_partial_statement_on_unused_name_only() -> None:
    (c,) = dead("from m import a, b\nprint(b)\n")
    assert c.name == "a" and c.flags == {Flag.PARTIAL_STATEMENT}
    assert all(Flag.PARTIAL_STATEMENT not in c.flags for c in dead("from m import a, b\n"))


def test_flag_side_effect_import_third_party_plain_only() -> None:
    (c,) = dead("import requests\n")
    assert c.flags == {Flag.SIDE_EFFECT_IMPORT}
    assert c.flag_details[Flag.SIDE_EFFECT_IMPORT] == "requests"
    assert dead("import os\n")[0].flags == frozenset()
    assert dead("from requests import get\n")[0].flags == frozenset()


@pytest.mark.parametrize(
    "src",
    [
        "try:\n    import os\nexcept ImportError:\n    pass\n",
        "try:\n    import os\nexcept (ValueError, ModuleNotFoundError):\n    pass\n",
        "try:\n    import os\nexcept:\n    pass\n",
        "import sys\nif sys.platform == 'win32':\n    import os\n",
    ],
)
def test_flag_conditional_import(src: str) -> None:
    assert Flag.CONDITIONAL_IMPORT in next(c for c in dead(src) if c.name == "os").flags


def test_try_without_import_error_and_functions_are_plain() -> None:
    src = "try:\n    import os\nexcept ValueError:\n    pass\ndef f():\n    import sys\n"
    assert [(c.name, c.flags) for c in dead(src)] == [("os", frozenset())]


def test_flag_dynamic_pattern_in_file() -> None:
    assert dead("import os\ngetattr(x, name)\n")[0].flags == {Flag.DYNAMIC_PATTERN_IN_FILE}
    assert dead("import os\nglobals()\n")[0].flags == {Flag.DYNAMIC_PATTERN_IN_FILE}


def test_haunted_sample_dead_imports() -> None:
    files = sorted((HAUNTED / "inventory").glob("*.py"))
    parsed = {}
    for f in files:
        src = f.read_text(encoding="utf-8")
        rel = f.relative_to(HAUNTED).as_posix()
        tree = parse_module(src)
        assert tree is not None
        parsed[rel] = (src, tree, collect_definitions(rel, src, tree))
    pairs = reexport_pairs({rel: facts.bindings for rel, (_, _, facts) in parsed.items()})
    found = {}
    for rel, (src, tree, facts) in parsed.items():
        binds = collect_import_bindings(rel, tree, facts.lines)
        for c in dead_imports(rel, binds, collect_occurrences(src, tree), facts, pairs):
            found[(c.file_path, c.name)] = (c.start_line, c.flags)
    assert found == {
        ("inventory/reports.py", "json"): (1, frozenset()),
        ("inventory/models.py", "Optional"): (1, frozenset()),
        ("inventory/api.py", "inventory.signals"): (1, frozenset({Flag.SIDE_EFFECT_IMPORT})),
    }
