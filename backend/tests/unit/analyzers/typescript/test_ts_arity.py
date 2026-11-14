"""Arity rule tests (TS-A1)."""

from __future__ import annotations

import pytest

from graveyard.analyzers.typescript.arity import incompatible
from graveyard.analyzers.typescript.definitions import collect_definitions
from graveyard.analyzers.typescript.parser import parse


def method(params: str, path: str = "a.ts"):
    src = f"class A {{ m({params}) {{ return 1 }} }}".encode()
    return collect_definitions(path, src, parse(path, src)).functions[0]


@pytest.mark.parametrize(
    ("params", "args", "spread", "call_file", "expected"),
    [
        ("a: number, b: number", 2, False, "c.ts", False),
        ("a: number, b: number", 3, False, "c.ts", True),
        ("a: number, b: number", 1, False, "c.ts", True),
        ("a: number, b?: number", 1, False, "c.ts", False),
        ("a: number, b?: number", 3, False, "c.tsx", True),
        ("a: number, b = 5", 1, False, "c.ts", False),
        ("a: number, b = 5", 0, False, "c.ts", True),
        ("a: number, ...rest: number[]", 9, False, "c.ts", False),
        ("a: number, ...rest: number[]", 0, False, "c.ts", False),
        ("this: Foo, a: number", 1, False, "c.ts", False),
        ("this: Foo, a: number", 2, False, "c.ts", True),
        ("", 1, False, "c.ts", True),
        ("a: number", 3, False, "c.js", False),
        ("a: number", 3, False, "c.mjs", False),
        ("a: number", 3, True, "c.ts", False),
    ],
)
def test_TS_A1_table(params, args, spread, call_file, expected):
    assert incompatible(method(params), args, spread, call_file) is expected


def test_TS_A1_never_for_js_definitions():
    assert incompatible(method("a", "a.js"), 3, False, "c.ts") is False


def test_TS_A1_methods_only():
    src = b"export function f(a: number) {}"
    func = collect_definitions("a.ts", src, parse("a.ts", src)).functions[0]
    assert incompatible(func, 3, False, "c.ts") is False
