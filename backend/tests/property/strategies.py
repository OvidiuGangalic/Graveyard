"""Hypothesis strategies: small Python repos with a random cross-module call graph."""

from __future__ import annotations

import keyword
from dataclasses import dataclass, field

from hypothesis import strategies as st

_POOL = ["alpha", "beta", "gamma", "delta", "omega"]  # small pool so names repeat across modules
EXEMPT_DECORATORS = (
    "route", "app.route", "get", "validator", "receiver", "login_required", "command",
    "click.command", "task", "shared_task", "pytest.fixture", "hookimpl",
)  # fmt: skip
EXEMPT_NAMES = ("main", "setUp", "tearDown", "setUpClass", "setup_method", "teardown_class")


def _plain(name: str) -> bool:
    return (
        not keyword.iskeyword(name)
        and not keyword.issoftkeyword(name)
        and not name.startswith(("test", "pytest", "__"))
        and not name.endswith("__")
        and name not in EXEMPT_NAMES
    )


def identifier() -> st.SearchStrategy[str]:
    """A valid name that no PY-E rule exempts."""
    return st.from_regex(r"[a-z][a-z0-9_]{2,8}", fullmatch=True).filter(_plain)


@dataclass
class PyRepo:
    files: dict[str, str]
    functions: list[tuple[str, str]]  # (path, name), every defined function
    called: set[tuple[str, str]] = field(default_factory=set)

    @property
    def uncalled(self) -> list[tuple[str, str]]:
        return [f for f in self.functions if f not in self.called]


@st.composite
def python_repo(draw: st.DrawFn, unique: bool = True) -> PyRepo:
    """1-5 modules of real functions; callers use `from mN import f` plus a call."""
    count = draw(st.integers(1, 5))
    names = identifier() if unique else st.sampled_from(_POOL)
    defs: dict[str, list[str]] = {}
    seen: set[str] = set()
    for i in range(count):
        mod = draw(st.lists(names, min_size=1, max_size=8, unique=True))
        if unique:
            mod = [n for n in mod if n not in seen]
            seen.update(mod)
        defs[f"m{i}"] = mod
    called: set[tuple[str, str]] = set()
    files: dict[str, str] = {}
    for mod, funcs in defs.items():
        imports: dict[str, str] = {}  # local name -> source module
        bodies: list[str] = []
        others = [(m, n) for m, ns in defs.items() if m != mod for n in ns]
        for fn in funcs:
            target = draw(st.sampled_from(others)) if others and draw(st.booleans()) else None
            if target and target[1] not in imports and target[1] not in funcs:
                imports[target[1]] = target[0]
                called.add((f"{target[0]}.py", target[1]))
                body = f"return {target[1]}() + {draw(st.integers(0, 9))}"
            else:
                body = f"return {draw(st.integers(0, 99))}"
            bodies.append(f"def {fn}():\n    {body}\n")
        head = "".join(f"from {m} import {n}\n" for n, m in imports.items())
        files[f"{mod}.py"] = head + ("\n\n" if head else "") + "\n\n".join(bodies)
    functions = [(f"{m}.py", n) for m, ns in defs.items() for n in ns]
    return PyRepo(files, functions, called)


@st.composite
def exempt_function(draw: st.DrawFn) -> tuple[str, str]:
    """(name, source) of a function exempted by a PY-E name or decorator."""
    if draw(st.booleans()):
        name = draw(
            st.one_of(
                st.sampled_from(EXEMPT_NAMES),
                identifier().map(lambda n: f"test_{n}"),
                identifier().map(lambda n: f"pytest_{n}"),
            )
        )
        return name, f"def {name}():\n    return 1\n"
    name = draw(identifier())
    return name, f"@{draw(st.sampled_from(EXEMPT_DECORATORS))}\ndef {name}():\n    return 1\n"
