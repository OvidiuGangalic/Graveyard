from __future__ import annotations

import inspect

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from graveyard.analyzers.python.arity import incompatible
from graveyard.analyzers.python.definitions import collect_definitions
from graveyard.analyzers.python.records import CallShape

CASES = [
    ("def f(a):", 2, (), True),
    ("def f(a):", 1, ("b",), True),
    ("def f(a, b):", 1, (), True),
    ("def f(a, b=1):", 1, (), False),
    ("def f(a, *, k):", 1, (), True),
    ("def f(a, *, k):", 1, ("k",), False),
    ("def f(a, *args):", 5, (), False),
    ("def f(a, **kw):", 1, ("zzz",), False),
    ("def f(a):", 1, ("a",), False),
    ("@cache\ndef f(a):", 3, (), True),
    ("@unknown_wrapper\ndef f(a):", 3, (), False),
    ("@functools.lru_cache(1)\ndef f(a):", 3, (), True),
]


@pytest.mark.parametrize(("sig", "pos", "kw", "expected"), CASES)
def test_PY_A1_functions(sig: str, pos: int, kw: tuple[str, ...], expected: bool) -> None:
    (func,) = collect_definitions("a.py", f"{sig}\n    pass\n").functions
    assert incompatible(func, CallShape(pos, kw, False)) is expected


def test_PY_A1_unpacking_call_is_skipped() -> None:
    (func,) = collect_definitions("a.py", "def f(a):\n    pass\n").functions
    assert not incompatible(func, CallShape(9, ("x",), True))


@pytest.mark.parametrize(
    ("decorator", "pos", "expected"),
    [("", 1, False), ("", 2, True), ("@staticmethod", 1, True), ("@staticmethod", 2, False)],
)
def test_PY_A1_method_drops_first_parameter(decorator: str, pos: int, expected: bool) -> None:
    src = f"class C:\n    {decorator}\n    def m(self, a):\n        pass\n"
    (func,) = collect_definitions("a.py", src).functions
    assert incompatible(func, CallShape(pos, (), False)) is expected  # static keeps `self`


@pytest.mark.parametrize(
    ("receiver", "expected"),
    [
        ("stock", True),
        ("self.repo", True),
        ("x.StockV1", False),
        ("Base", False),
        ("super()", False),
    ],
)
def test_PY_A1_unbound_reading_for_class_like_receivers(receiver: str, expected: bool) -> None:
    src = "class StockV1:\n    def adjust(self, sku):\n        pass\n"
    (func,) = collect_definitions("a.py", src).functions
    assert incompatible(func, CallShape(2, (), False), receiver) is expected


NAMES = ["a", "b", "c", "d"]


@st.composite
def signatures_and_calls(draw: st.DrawFn):
    names = draw(st.permutations(NAMES))
    n_pos, n_kwonly = draw(st.integers(0, 3)), draw(st.integers(0, 1))
    pos, kwonly = names[:n_pos], names[n_pos : n_pos + n_kwonly]
    defaults = draw(st.integers(0, n_pos))
    vararg, kwarg = draw(st.booleans()), draw(st.booleans())
    n_args = draw(st.integers(0, 4))
    keywords = tuple(draw(st.lists(st.sampled_from([*NAMES, "z"]), unique=True, max_size=3)))
    return pos, kwonly, defaults, vararg, kwarg, n_args, keywords


@pytest.mark.property
@settings(max_examples=200)
@given(signatures_and_calls())
def test_p26_arity_never_hides_a_compatible_call(case) -> None:
    """P26 (arity never hides a compatible call). For any generated signature and any
    generated call that Python accepts for it, PY-A1 does not mark the call incompatible.

    **Validates: Requirement 2.8.**
    """
    pos, kwonly, defaults, vararg, kwarg, n_args, keywords = case
    params = [p + (" = 0" if i >= len(pos) - defaults else "") for i, p in enumerate(pos)]
    params += (["*args"] if vararg else ["*"] if kwonly else []) + kwonly
    params += ["**kw"] if kwarg else []
    src = f"def stub({', '.join(params)}):\n    pass\n"
    namespace: dict[str, object] = {}
    exec(src, namespace)  # test-generated stub, not analysed repo code
    try:
        inspect.signature(namespace["stub"]).bind(*range(n_args), **dict.fromkeys(keywords, 0))
    except TypeError:
        return  # Python rejects this call: PY-A1 may say anything
    (func,) = collect_definitions("a.py", src).functions
    assert not incompatible(func, CallShape(n_args, keywords, False))
