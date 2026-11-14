from __future__ import annotations

from pathlib import Path

import pytest

from graveyard.analyzers.python.definitions import collect_definitions
from graveyard.analyzers.python.entrypoints import exempt_rule, load_script_entries
from graveyard.models import SourceFile

NO_SCRIPTS: frozenset[tuple[str, str]] = frozenset()


def rule(
    src: str,
    func: str,
    path: str = "pkg/mod.py",
    scripts: frozenset[tuple[str, str]] = NO_SCRIPTS,
    is_test: bool = False,
) -> str | None:
    facts = collect_definitions(path, src)
    fn = next(f for f in facts.functions if f.name == func)
    cls = next((c for c in facts.classes if c.name == fn.class_name), None)
    return exempt_rule(fn, cls, SourceFile(path, "python", len(src), is_test), scripts)


def deco(name: str, func: str = "f", path: str = "pkg/mod.py") -> str | None:
    return rule(f"@{name}\ndef {func}():\n    return 1\n", func, path)


def test_PY_E1_main_and_dunder_main_file() -> None:
    assert rule("def main():\n    return 1\n", "main") == "PY-E1"
    assert rule("def helper():\n    return 1\n", "helper", "pkg/__main__.py") == "PY-E1"
    assert rule("class A:\n    def main(self):\n        return 1\n", "main") is None


def test_PY_E2_dunder_names() -> None:
    assert rule("class A:\n    def __repr__(self):\n        return 'a'\n", "__repr__") == "PY-E2"
    assert rule("def __getattr__(n):\n    return 1\n", "__getattr__") == "PY-E2"
    assert rule("def _x_():\n    return 1\n", "_x_") is None


@pytest.mark.parametrize("name", ["app.route('/')", "router.get", "app.errorhandler(404)", "cli"])
def test_PY_E3_route_decorators(name: str) -> None:
    assert deco(name) == "PY-E3"


def test_PY_E3_unrelated_decorator_not_exempt() -> None:
    assert deco("app.other") is None


def test_PY_E4_tests() -> None:
    assert rule("def helper():\n    return 1\n", "helper", is_test=True) == "PY-E4"
    assert rule("def test_x():\n    return 1\n", "test_x") == "PY-E4"
    assert rule("def pytest_configure():\n    return 1\n", "pytest_configure") == "PY-E4"
    assert deco("pytest.fixture(scope='x')") == "PY-E4"
    assert rule("class TestA:\n    def helper(self):\n        return 1\n", "helper") == "PY-E4"
    assert rule("class A(unittest.TestCase):\n    def aid(self):\n        return 1\n", "aid") == (
        "PY-E4"
    )
    assert rule("class A:\n    def setUp(self):\n        return 1\n", "setUp") == "PY-E4"
    assert rule("def helper():\n    return 1\n", "helper") is None


def test_PY_E5_django() -> None:
    view = "def index(request):\n    return 1\n"
    assert rule(view, "index", "app/views.py") == "PY-E5"
    assert rule(view, "index", "app/views/home.py") == "PY-E5"
    assert rule("class A(ListView):\n    def get_x(self):\n        return 1\n", "get_x") == "PY-E5"
    assert deco("receiver(sig)") == "PY-E5"
    assert deco("login_required") == "PY-E5"
    assert deco("admin.register(Foo)") == "PY-E5"
    assert deco("x.admin.register(Foo)") == "PY-E5"
    assert rule("def f():\n    return 1\n", "f", "app/management/commands/seed.py") == "PY-E5"
    assert rule("def f():\n    return 1\n", "f", "app/admin.py") == "PY-E5"


def test_PY_E5_negatives() -> None:
    assert deco("registry.register") is None
    assert (
        rule("def request_handler(x):\n    return 1\n", "request_handler", "app/views.py") is None
    )
    assert rule("def index(request):\n    return 1\n", "index", "app/other.py") is None


def test_PY_E6_cli_decorators() -> None:
    assert deco("click.command()") == "PY-E6"
    assert deco("app.callback") == "PY-E6"
    assert deco("click.option('-x')") == "PY-E6"


def test_PY_E6_script_entries_match_by_module_suffix() -> None:
    src = "def run_cli():\n    return 1\n"
    scripts = frozenset({("pkg.cli", "run_cli")})
    assert rule(src, "run_cli", "src/pkg/cli.py", scripts) == "PY-E6"
    assert rule(src, "run_cli", "src/xpkg/cli.py", scripts) is None
    assert rule(src, "run_cli", "pkg/other.py", scripts) is None
    assert rule("def other():\n    return 1\n", "other", "pkg/cli.py", scripts) is None
    assert rule(src, "run_cli", "pkg/cli/__init__.py", scripts) == "PY-E6"


def test_PY_E6_load_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\na = "pkg.cli:go"\n[project.gui-scripts]\nb = "pkg.gui:show"\n'
        '[project.entry-points.x]\nc = "pkg.plug:load.attr [extra]"\n'
        '[tool.poetry.scripts]\nd = "pkg.p:poet"\n',
        encoding="utf-8",
    )
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "pyproject.toml").write_text("[project\nbroken", encoding="utf-8")
    got = load_script_entries(tmp_path, ("pyproject.toml", "sub/pyproject.toml"))
    assert got == {
        ("pkg.cli", "go"),
        ("pkg.gui", "show"),
        ("pkg.plug", "load"),
        ("pkg.p", "poet"),
    }


def test_PY_E6_load_setup_files(tmp_path: Path) -> None:
    (tmp_path / "setup.py").write_text(
        'setup(entry_points={"console_scripts": ["x=pkg.a:one", "y = pkg.b:two"]})\n'
        'other = ["z=pkg.c:three"]\n',
        encoding="utf-8",
    )
    (tmp_path / "setup.cfg").write_text(
        "[options.entry_points]\nconsole_scripts =\n    w = pkg.d:four\n[metadata]\nq = r:s\n",
        encoding="utf-8",
    )
    assert load_script_entries(tmp_path, ()) == {
        ("pkg.a", "one"),
        ("pkg.b", "two"),
        ("pkg.d", "four"),
    }


def test_PY_E7_stubs() -> None:
    assert rule("def f():\n    ...\n", "f") == "PY-E7"
    assert rule("def f():\n    raise NotImplementedError\n", "f") == "PY-E7"
    assert deco("abc.abstractmethod") == "PY-E7"
    assert deco("overload") == "PY-E7"
    assert rule("def f():\n    return 1\n", "f") is None


@pytest.mark.parametrize("name", ["shared_task", "app.task(bind=True)", "mcp.tool()", "hookimpl"])
def test_PY_E8_task_decorators(name: str) -> None:
    assert deco(name) == "PY-E8"


def test_PY_E9_protocol_methods() -> None:
    def method(base: str, name: str) -> str | None:
        return rule(f"class A{base}:\n    def {name}(self):\n        return 1\n", name)

    assert method("(threading.Thread)", "run") == "PY-E9"
    assert method("(Process)", "run") == "PY-E9"
    assert method("(Base)", "run") is None
    for name in ("visit_Name", "generic_visit", "leave_x", "do_help", "handle", "handle_x"):
        assert method("(Base)", name) == "PY-E9"
        assert method("", name) is None
