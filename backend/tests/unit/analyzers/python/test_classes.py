from __future__ import annotations

from graveyard.analyzers.python.definitions import collect_definitions, parse_module
from graveyard.analyzers.python.references import collect_occurrences
from graveyard.analyzers.python.resolve import ModuleIndex, Unresolved, resolve

U = "unresolved"
BASE = "class Base:\n    def go(self):\n        pass\n"


def res(files: dict[str, str], name: str, at: str = "main.py", form: str = "attr") -> object:
    """Qualified names the first `form` occurrence of `name` in `at` resolves to, or U."""
    facts = {p: collect_definitions(p, t) for p, t in files.items()}
    occ = next(
        o
        for o in collect_occurrences(files[at], parse_module(files[at]))
        if o.name == name and o.form == form
    )
    found = resolve(occ, at, facts, ModuleIndex(files))
    return U if isinstance(found, Unresolved) else {f.qualified_name for f in found}


def test_PY_S4_self_and_cls_resolve_to_the_class_family() -> None:
    src = BASE + "class Kid(Base):\n    def a(self):\n        self.go()\n"
    assert res({"main.py": src}, "go") == {"Base.go"}
    cls = "class A:\n    @classmethod\n    def a(cls):\n        cls.go()\n\n"
    assert res({"main.py": cls + "    def go(self):\n        pass\n"}, "go") == {"A.go"}


def test_PY_S4_family_spans_ancestors_and_descendants_across_files() -> None:
    files = {
        "base.py": BASE,
        "main.py": "from base import Base\nclass Mid(Base):\n    def a(self):\n        self.go()\n"
        "        self.leaf()\n",
        "kid.py": "from main import Mid\nclass Kid(Mid):\n    def go(self):\n        pass\n"
        "    def leaf(self):\n        pass\n",
        "other.py": "class Other:\n    def go(self):\n        pass\n",
    }
    assert res(files, "go") == {"Base.go", "Kid.go"}
    assert res(files, "leaf") == {"Kid.leaf"}


def test_PY_S4_siblings_share_a_family() -> None:
    sib = "class A(Base):\n    def a(self):\n        self.s()\n\n"
    sib += "class B(Base):\n    def s(self):\n        pass\n"
    assert res({"main.py": BASE + sib}, "s") == {"B.s"}
    assert res({"main.py": sib + "class Z:\n    pass\n", "o.py": "class Q:\n    pass\n"}, "s") == U


def test_PY_S4_super_and_class_name_receivers() -> None:
    src = BASE + "class Kid(Base):\n    def go(self):\n        super().go()\n"
    assert res({"main.py": src}, "go") == {"Base.go", "Kid.go"}
    files = {"base.py": BASE, "main.py": "from base import Base\nBase.go(1)\n"}
    assert res(files, "go") == {"Base.go"}
    assert res({"main.py": BASE + "Base.go(1)\n"}, "go") == {"Base.go"}


def test_PY_S4_method_not_in_family_is_unresolved() -> None:
    src = BASE + "class Kid(Base):\n    def a(self):\n        self.dynamic()\n"
    assert res({"main.py": src, "o.py": "def dynamic():\n    pass\n"}, "dynamic") == U


def test_PY_S4_needs_a_real_self_parameter() -> None:
    go = "    def go(self):\n        pass\n"
    static = "class A:\n    @staticmethod\n    def a(self):\n        self.go()\n\n" + go
    assert res({"main.py": static}, "go") == U
    nested = "class A:\n    class N:\n        def a(self):\n            self.go()\n\n" + go
    assert res({"main.py": nested}, "go") == U
    assert res({"main.py": "def f(self):\n    self.go()\n", "o.py": BASE}, "go") == U


def test_PY_S5_class_body_name_resolves_to_own_method() -> None:
    src = "class A:\n    def _get(self):\n        pass\n\n    total = property(_get)\n"
    assert res({"main.py": src}, "_get", form="name") == {"A._get"}
    assert res({"main.py": "class A:\n    x = property(_nope)\n"}, "_nope", form="name") == U


def test_PY_S4_family_is_the_connected_component() -> None:
    x = "    def x(self):\n        pass\n"
    run = "    def run(self):\n        self.x()\n"
    src = f"class M:\n{x}\nclass A:\n{x}{run}\nclass C(M, A):\n    pass\n"
    assert res({"main.py": src}, "x") == {"M.x", "A.x"}
