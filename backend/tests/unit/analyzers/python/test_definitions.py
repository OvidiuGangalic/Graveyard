from __future__ import annotations

import pytest

from graveyard.analyzers.python.definitions import collect_definitions, parse_module
from graveyard.analyzers.python.records import FileFacts, FunctionDef


def facts(src: str) -> FileFacts:
    return collect_definitions("m.py", src)


def funcs(src: str) -> dict[str, FunctionDef]:
    return {f.qualified_name: f for f in facts(src).functions}


def test_nested_lambda_and_conditional_defs_ignored() -> None:
    f = facts(
        "def top():\n    def inner(): pass\n    g = lambda: 1\n"
        "if X:\n    def cond(): pass\ntry:\n    def tried(): pass\nexcept E:\n    pass\n"
        "class C:\n    class N:\n        def deep(self): pass\n"
        "    if X:\n        def m(self): pass\n"
    )
    assert [x.qualified_name for x in f.functions] == ["top"]


def test_span_async_and_methods() -> None:
    fs = funcs(
        "@a\n@b(1)\nasync def f():\n    return 1\n"
        "class C(Base, mod.Mixin):\n    def m(self):\n        return 1\n"
    )
    assert (fs["f"].start_line, fs["f"].end_line, fs["f"].is_async) == (1, 4, True)
    assert fs["C.m"].class_name == "C" and fs["C.m"].start_line == 6
    cls = facts("class C(Base, mod.Mixin):\n    def m(self): ...\n").classes[0]
    assert cls.bases == ("Base", "mod.Mixin")
    assert cls.base_names == ("Base", "Mixin")
    assert cls.method_names == ("m",)
    generic = facts("class R(typing.Generic[T], Base[int]): pass\n").classes[0]
    assert generic.base_names == ("Generic", "Base")


def test_syntax_warnings_are_silenced(recwarn) -> None:
    assert facts('x = "\\d"\n').parsed
    assert not [w for w in recwarn if issubclass(w.category, SyntaxWarning)]


def test_overloads_merged() -> None:
    src = "@overload\ndef f(a): ...\n@overload\ndef f(a, b): ...\n@deco\ndef f(*a):\n    return 1\n"
    f = funcs(src)["f"]
    assert (f.start_line, f.end_line, f.body_kind) == (5, 7, "normal")
    assert [d.final_name for d in f.decorators] == ["overload", "overload", "deco"]


def test_property_setter_merged() -> None:
    fs = facts(
        "class C:\n    @property\n    def x(self):\n        return 1\n"
        "    @x.setter\n    def x(self, v):\n        pass\n"
    ).functions
    assert len(fs) == 1 and fs[0].start_line == 5
    assert [d.dotted for d in fs[0].decorators] == ["property", "x.setter"]


@pytest.mark.parametrize(
    ("body", "kind"),
    [
        ("...", "stub"),
        ("pass", "stub"),
        ('"""doc"""', "stub"),
        ('"""doc"""\n    ...', "stub"),
        ('"""doc"""\n    pass', "stub"),
        ("raise NotImplementedError", "stub"),
        ("raise NotImplementedError('x')", "stub"),
        ("return 1", "normal"),
        ('"""doc"""\n    return 1', "normal"),
        ("raise ValueError()", "normal"),
        ("x = 1\n    pass", "normal"),
    ],
)
def test_stub_detection(body: str, kind: str) -> None:
    assert funcs(f"def f():\n    {body}\n")["f"].body_kind == kind


def test_params() -> None:
    p = funcs("def f(a, b=1, /, c=2, *args, k, o=3, **kw): pass")["f"].params
    assert p.positional == ("a", "b", "c") and p.positional_defaults == 2
    assert p.kwonly == ("k", "o") and p.kwonly_required == ("k",)
    assert p.has_vararg and p.has_kwarg
    q = funcs("def f(a): pass")["f"].params
    assert not q.has_vararg and not q.has_kwarg and q.kwonly == ()


@pytest.mark.parametrize(
    ("deco", "final", "dotted", "call"),
    [
        ("app.get('/x')", "get", "app.get", True),
        ("registry.register", "register", "registry.register", False),
        ("functools.lru_cache(maxsize=2)", "lru_cache", "functools.lru_cache", True),
        ("property", "property", "property", False),
    ],
)
def test_decorators(deco: str, final: str, dotted: str, call: bool) -> None:
    d = funcs(f"@{deco}\ndef f(): pass")["f"].decorators[0]
    assert (d.source, d.final_name, d.dotted, d.is_call) == (deco, final, dotted, call)


def test_staticmethod() -> None:
    fs = funcs("class C:\n    @staticmethod\n    def a(): pass\n    def b(self): pass\n")
    assert fs["C.a"].is_staticmethod and not fs["C.b"].is_staticmethod


def test_module_getattr() -> None:
    assert facts("def __getattr__(n): ...\n").has_module_getattr
    assert not facts("class C:\n    def __getattr__(self, n): ...\n").has_module_getattr


@pytest.mark.parametrize("src", ["print 'hi'\n", "x = 1\x00\n", "def (:\n", "(" * 5000])
def test_unparseable(src: str) -> None:
    f = facts(src)
    assert not f.parsed and f.functions == ()
    assert parse_module(src) is None


def test_crlf_line_numbers() -> None:
    f = facts("x = 1\r\n\r\ndef f():\r\n    return 1\r\n")
    assert (f.functions[0].start_line, f.functions[0].end_line) == (3, 4)
    assert f.lines[:3] == ("x = 1", "", "def f():")


def test_form_feed_lines_match_ast() -> None:
    f = facts("x = 1\x0c\ndef f(): pass\n")
    assert f.lines[f.functions[0].start_line - 1] == "def f(): pass"
