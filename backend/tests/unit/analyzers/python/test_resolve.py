from __future__ import annotations

import pytest

from graveyard.analyzers.python.definitions import collect_definitions, parse_module
from graveyard.analyzers.python.references import collect_occurrences
from graveyard.analyzers.python.resolve import ModuleIndex, Unresolved, resolve

F = "def f():\n    pass\n"
U = "unresolved"


def res(files: dict[str, str], name: str = "f", form: str = "name", at: str = "main.py"):
    """Files that the first `form` occurrence of `name` in `at` resolves to, or "unresolved"."""
    facts = {p: collect_definitions(p, t) for p, t in files.items()}
    occs = collect_occurrences(files[at], parse_module(files[at]))
    occ = next(o for o in occs if o.name == name and o.form == form)
    found = resolve(occ, at, facts, ModuleIndex(files))
    return U if isinstance(found, Unresolved) else {f.file_path for f in found}


def test_PY_S1_module_level_binding_resolves_to_own_definition() -> None:
    assert res({"main.py": F + "f()\n", "b.py": F}) == {"main.py"}


def test_PY_S2_from_import_resolves_to_imported_module() -> None:
    files = {"main.py": "from b import f\nf()\n", "b.py": F, "c.py": F}
    assert res(files) == {"b.py"}
    assert res(files, form="import") == {"b.py"}
    assert res({"main.py": "from b import f as g\ng()\n", "b.py": F}, "g") == {"b.py"}


def test_PY_S3_module_attribute_resolves_into_module() -> None:
    attr = {"b.py": F, "c.py": F}
    assert res({**attr, "main.py": "import b\nb.f()\n"}, form="attr") == {"b.py"}
    assert res({**attr, "main.py": "import b as m\nm.f()\n"}, form="attr") == {"b.py"}
    pkg = {"p/b.py": F, "q/b.py": F}
    assert res({**pkg, "main.py": "import p.b\np.b.f()\n"}, form="attr") == {"p/b.py"}
    assert res({**pkg, "main.py": "from p import b\nb.f()\n"}, form="attr") == {"p/b.py"}
    assert res({**attr, "main.py": "import os\nos.f()\n"}, form="attr") == set()


def test_PY_S6_unbound_bare_name_refers_to_no_repo_function() -> None:
    assert res({"main.py": "def g(f):\n    f()\n", "b.py": F}) == set()


def test_PY_S7_everything_else_is_unresolved() -> None:
    assert res({"main.py": "obj.f()\n", "b.py": F}, form="attr") == U
    assert res({"main.py": "from b import *\nf()\n", "b.py": F}) == U
    assert res({"main.py": "def (:\n f()\n", "b.py": F}, form="token") == U
    assert res({"main.py": "import b\nb.nope()\n", "b.py": F}, "nope", "attr") == U


def test_dynamic_lookup_makes_bare_names_unresolved() -> None:
    assert res({"main.py": "globals()\nf()\n", "b.py": F}) == U
    assert res({"main.py": "getattr(x, name)\nf()\n"}) == U
    assert res({"main.py": "getattr(x, 'a')\nf()\n"}) == set()


@pytest.mark.parametrize(
    ("src", "modules", "expected"),
    [
        ("from .m import f\nf()\n", ["a/b/m.py", "a/m.py"], {"a/b/m.py"}),
        ("from ..m import f\nf()\n", ["a/b/m.py", "a/m.py"], {"a/m.py"}),
        ("from . import m\nm.f()\n", ["a/b/m.py", "a/m.py"], {"a/b/m.py"}),
        ("from y.z import f\nf()\n", ["xy/z.py"], set()),  # whole segments only
        ("from os import f\nf()\n", ["a/m.py"], set()),  # outside the repo
        ("from m import f\nf()\n", ["p/m.py", "q/m.py"], {"p/m.py", "q/m.py"}),  # union
    ],
)
def test_module_resolution(src: str, modules: list[str], expected: set[str]) -> None:
    files = {"a/b/main.py": src, **dict.fromkeys(modules, F)}
    assert res(files, at="a/b/main.py", form="attr" if "m.f()" in src else "name") == expected


def test_reexport_via_init_one_and_two_hops() -> None:
    files = {"pkg/__init__.py": "from .m import f\n", "pkg/m.py": F, "other/m.py": F}
    assert res({**files, "main.py": "from pkg import f\nf()\n"}) == {"pkg/m.py"}
    files = {"top/__init__.py": "from pkg import f\n", "pkg/__init__.py": "from .m import f\n"}
    assert res({**files, "pkg/m.py": F, "main.py": "from top import f\nf()\n"}) == {"pkg/m.py"}


def test_reexport_star_import_and_submodule_union() -> None:
    files = {"pkg/__init__.py": "from .m import *\n", "pkg/m.py": F}
    assert res({**files, "main.py": "from pkg import f\nf()\n"}) == {"pkg/m.py"}
    both = {
        "pkg/__init__.py": "from .k import m\n",
        "pkg/k.py": "def m():\n    pass\n",
        "pkg/m.py": F,
    }
    assert res({**both, "main.py": "from pkg import m\nm()\n"}, "m") == {"pkg/k.py"}


def test_reexport_getattr_and_depth_limit_are_unresolved() -> None:
    getattr_pkg = {"pkg/__init__.py": "def __getattr__(n):\n    pass\n", "pkg/m.py": F}
    assert res({**getattr_pkg, "main.py": "from pkg import f\nf()\n"}) == U
    chain = {f"m{i}.py": f"from m{i + 1} import f\n" for i in range(1, 6)}  # 5 import hops
    assert res({**chain, "m6.py": F, "main.py": "from m1 import f\nf()\n"}) == {"m6.py"}
    chain = {f"m{i}.py": f"from m{i + 1} import f\n" for i in range(1, 7)}  # 6 import hops
    assert res({**chain, "m7.py": F, "main.py": "from m1 import f\nf()\n"}) == U
