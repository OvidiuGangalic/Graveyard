from __future__ import annotations

import ast
from pathlib import Path

from graveyard.analyzers.common import TextIndex
from graveyard.analyzers.python.definitions import collect_definitions
from graveyard.analyzers.python.evidence import (
    RepoFacts,
    collect_strings,
    dunder_all_callers,
    flags_for,
    string_callers,
)
from graveyard.analyzers.python.records import FileFacts, FunctionDef
from graveyard.models import Flag

SAMPLE = Path(__file__).resolve().parents[5] / "samples" / "haunted-repo"


def build(files: dict[str, str], texts: dict[str, str] | None = None, root: Path | None = None):
    """Facts, strings and text index for in-memory files (texts are written under ``root``)."""
    facts = {p: collect_definitions(p, src) for p, src in files.items()}
    strings = {p: collect_strings(p, ast.parse(src), src.split("\n")) for p, src in files.items()}
    for name, body in (texts or {}).items():
        (root / name).write_text(body, encoding="utf-8")  # type: ignore[operator]
    index = TextIndex(root or Path("."), tuple(texts or ()))
    repo = RepoFacts(
        class_names=frozenset(c.name for f in facts.values() for c in f.classes),
        has_reflection=any(f.has_getattr_reflection for f in facts.values()),
        facts_by_file=facts,
    )
    return facts, strings, index, repo


def func_of(facts: FileFacts, name: str) -> FunctionDef:
    return next(f for f in facts.functions if f.qualified_name == name)


def flags(files: dict[str, str], target: str, path: str = "m.py", **kw):
    facts, strings, index, repo = build(files, **kw)
    fn = func_of(facts[path], target)
    cls = next((c for c in facts[path].classes if c.name == fn.class_name), None)
    callers = string_callers(fn, strings, index)
    return flags_for(fn, cls, facts[path], repo, callers)


def test_PY_W1_strings_in_python_files(tmp_path: Path) -> None:
    files = {
        "m.py": 'def target():\n    return "target"\n',
        "a.py": 'NAMES = ["x", "call target now"]\n',
        "b.py": '"""Module doc mentioning target."""\nX = "targets"\n',
    }
    facts, strings, index, _ = build(files)
    callers = string_callers(func_of(facts["m.py"], "target"), strings, index)
    assert [(c.file_path, c.line, c.kind) for c in callers] == [("a.py", 1, "string_match")]
    assert callers[0].snippet == 'NAMES = ["x", "call target now"]'


def test_PY_W1_own_span_and_docstrings_do_not_count() -> None:
    src = 'def target():\n    """target"""\n    return "target"\n\n\nOTHER = "target"\n'
    facts, strings, index, _ = build({"m.py": src})
    callers = string_callers(func_of(facts["m.py"], "target"), strings, index)
    assert [c.line for c in callers] == [6]  # only the string outside the span


def test_PY_W2_text_files_and_short_names(tmp_path: Path) -> None:
    texts = {"README.md": "Run `refund_all` daily\nand `go` too\n"}
    files = {"m.py": "def refund_all():\n    return 1\n\n\ndef go():\n    return 1\n"}
    facts, strings, index, _ = build(files, texts, tmp_path)
    callers = string_callers(func_of(facts["m.py"], "refund_all"), strings, index)
    assert [(c.file_path, c.line) for c in callers] == [("README.md", 1)]
    assert string_callers(func_of(facts["m.py"], "go"), strings, index) == []


def test_PY_F1_unknown_decorator() -> None:
    def one(deco: str) -> dict:
        return flags({"m.py": f"@{deco}\ndef f():\n    return 1\n"}, "f")[1]

    assert one("registry.register") == {Flag.UNKNOWN_DECORATOR: "@registry.register"}
    for benign in ("property", "functools.lru_cache(2)", "x.setter", "typing.final"):
        assert Flag.UNKNOWN_DECORATOR not in one(benign)


def test_PY_F2_external_base_class() -> None:
    def one(bases: str) -> dict:
        src = f"class A:\n    pass\n\n\nclass B({bases}):\n    def f(self):\n        return 1\n"
        return flags({"m.py": src}, "B.f")[1]

    assert one("Base") == {Flag.EXTERNAL_BASE_CLASS: "Base"}
    assert one("Generic[T]") == {}
    assert one("A") == {}


def test_PY_F3_dynamic_pattern_in_file() -> None:
    assert (
        Flag.DYNAMIC_PATTERN_IN_FILE in flags({"m.py": "def f():\n    return eval('1')\n"}, "f")[0]
    )
    getattr_src = "def __getattr__(n):\n    return 1\n\n\ndef f():\n    return 1\n"
    assert Flag.DYNAMIC_PATTERN_IN_FILE in flags({"m.py": getattr_src}, "f")[0]
    assert flags({"m.py": "def f():\n    return 1\n"}, "f")[0] == frozenset()


def test_PY_F4_repo_has_reflection_methods_only() -> None:
    other = "def g(o, n):\n    return getattr(o, n)\n"
    cls = "class A:\n    def m(self):\n        return 1\n\n\ndef f():\n    return 1\n"
    assert Flag.REPO_HAS_REFLECTION in flags({"m.py": cls, "o.py": other}, "A.m")[0]
    assert Flag.REPO_HAS_REFLECTION not in flags({"m.py": cls, "o.py": other}, "f")[0]
    literal = "def g(o):\n    return getattr(o, 'x')\n"
    assert Flag.REPO_HAS_REFLECTION not in flags({"m.py": cls, "o.py": literal}, "A.m")[0]


def test_PY_F5_in_dunder_all() -> None:
    files = {
        "pkg/m.py": "def f():\n    return 1\n\n\ndef g():\n    return 1\n",
        "pkg/__init__.py": "from .m import f\n__all__ = ['f']\n",
    }
    facts, _, _, repo = build(files)
    (caller,) = dunder_all_callers(func_of(facts["pkg/m.py"], "f"), facts["pkg/m.py"], repo)
    assert (caller.file_path, caller.line, caller.kind) == ("pkg/__init__.py", 2, "reexport")
    assert Flag.IN_DUNDER_ALL in flags(files, "f", "pkg/m.py")[0]
    assert flags(files, "g", "pkg/m.py")[0] == frozenset()


def test_PY_F6_string_match() -> None:
    files = {"m.py": "def f():\n    return 1\n", "a.py": "X = 'f'\n"}
    assert flags(files, "f") == ({Flag.STRING_MATCH}, {Flag.STRING_MATCH: "a.py:1"})


def test_haunted_sample_flags(tmp_path: Path) -> None:
    files = {p.relative_to(SAMPLE).as_posix(): p.read_text() for p in SAMPLE.rglob("*.py")}
    facts, strings, index, repo = build(files, {"README.md": "# demo\n"}, tmp_path)
    path = "inventory/plugins.py"
    refund = func_of(facts[path], "handle_refund")
    callers = string_callers(refund, strings, index)
    assert [(c.file_path, c.line) for c in callers] == [(path, 1)]
    found, _ = flags_for(refund, None, facts[path], repo, callers)
    assert found == {Flag.STRING_MATCH, Flag.DYNAMIC_PATTERN_IN_FILE}
    recount = func_of(facts["inventory/models.py"], "Stock.recount")
    cls = facts["inventory/models.py"].classes[0]
    no_callers = string_callers(recount, strings, index)
    assert flags_for(recount, cls, facts["inventory/models.py"], repo, no_callers)[0] == frozenset()
