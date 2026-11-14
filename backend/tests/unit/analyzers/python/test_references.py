from __future__ import annotations

import pytest

from graveyard.analyzers.python.definitions import parse_module
from graveyard.analyzers.python.records import CallShape, Occurrence
from graveyard.analyzers.python.references import collect_occurrences


def occ(src: str) -> tuple[Occurrence, ...]:
    return collect_occurrences(src, parse_module(src))


def pairs(src: str) -> list[tuple[str, str]]:
    return [(o.name, o.form) for o in occ(src)]


def one(src: str, name: str) -> Occurrence:
    return next(o for o in occ(src) if o.name == name)


def test_PY_R1_name_any_context() -> None:
    got = {(o.name, o.is_store) for o in occ("x = y + 1\ndel z\n")}
    assert got == {("x", True), ("y", False), ("z", True)}


def test_PY_R2_attribute_attr() -> None:
    assert pairs("obj.recount\n") == [("obj", "name"), ("recount", "attr")]


def test_PY_R3_import_from_alias_name() -> None:
    assert pairs("from p.q import r as s, t\n") == [("r", "import"), ("t", "import")]


def test_PY_R4_import_every_segment() -> None:
    assert pairs("import a.b.c as d\n") == [("a", "import"), ("b", "import"), ("c", "import")]


def test_PY_R5_keyword_and_param_names_absent() -> None:
    names = {o.name for o in occ("def f(a, *b, k=1, **kw):\n    return g(key=a, **kw)\n")}
    assert names == {"a", "kw", "g"}


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("def f(a: 'Foo') -> 'Bar.Baz': ...\n", {"Foo", "Bar", "Baz"}),
        ("x: 'List[Item]' = []\n", {"x", "List", "Item"}),
        ("x = []  # type: List[Item]\n", {"x", "List", "Item"}),
        ("def f(a, b):\n    # type: (int, Foo) -> Bar\n    pass\n", {"int", "Foo", "Bar"}),
    ],
)
def test_PY_R6_string_annotations_and_type_comments(src: str, expected: set[str]) -> None:
    assert expected <= {o.name for o in occ(src)}


def test_PY_R6_failed_string_gives_tokens_on_annotation_line() -> None:
    got = [o for o in occ("x = 1\ndef f(a: 'not valid(') -> None: ...\n") if o.form == "token"]
    assert [(o.name, o.line) for o in got] == [("not", 2), ("valid", 2)]


@pytest.mark.parametrize(
    ("src", "name", "receiver"),
    [
        ("obj.x\n", "x", "obj"),
        ("super().x\n", "x", "super()"),
        ("a.b.x\n", "x", "a.b"),
        ("a.b.x\n", "b", "a"),
        ("a.b().x\n", "x", None),
        ("items[0].x\n", "x", None),
    ],
)
def test_receiver_forms(src: str, name: str, receiver: str | None) -> None:
    assert one(src, name).receiver == receiver


def test_enclosing_class_and_class_body() -> None:
    src = "top1\nclass C:\n    a = prop(m)\n    def m(self):\n        return inner\nafter\n"
    c = {o.name: o for o in occ(src)}
    assert (c["top1"].enclosing_class, c["after"].enclosing_class) == (None, None)
    assert (c["prop"].enclosing_class, c["prop"].in_class_body) == ("C", True)
    assert (c["inner"].enclosing_class, c["inner"].in_class_body) == ("C", False)


@pytest.mark.parametrize(
    ("src", "shape"),
    [
        ("f(1, 2)\n", CallShape(2, (), False)),
        ("o.f(1, k=2, j=3)\n", CallShape(1, ("k", "j"), False)),
        ("f(*a)\n", CallShape(0, (), True)),
        ("f(1, **kw)\n", CallShape(1, (), True)),
    ],
)
def test_call_shapes(src: str, shape: CallShape) -> None:
    assert one(src, "f").call == shape


def test_store_vs_load_and_non_callee() -> None:
    got = {(o.name, o.is_store) for o in occ("self.a = b.c\n")}
    assert got == {("a", True), ("self", False), ("c", False), ("b", False)}
    assert one("g(f)\n", "f").call is None


def test_unparseable_tokens_with_lines() -> None:
    src = "def (:\r\n  foo bar\r\n"
    got = collect_occurrences(src, None)
    assert [(o.name, o.line, o.form) for o in got] == [
        ("def", 1, "token"),
        ("bar", 2, "token"),
        ("foo", 2, "token"),
    ]
    assert all(o.receiver is None and o.enclosing_class is None and o.call is None for o in got)
