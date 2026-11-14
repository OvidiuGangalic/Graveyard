"""Exemption rules PY-E1..PY-E9: framework entry points are never reported."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

from graveyard.analyzers.python.records import ClassDef, DecoratorInfo, FunctionDef
from graveyard.models import SourceFile

_E3 = frozenset(
    "route get post put patch delete head options trace websocket api_route on_event middleware "
    "exception_handler errorhandler before_request after_request teardown_request "
    "before_first_request teardown_appcontext context_processor template_filter template_global "
    "url_value_preprocessor shell_context_processor cli lifespan dependency validator "
    "field_validator model_validator root_validator field_serializer model_serializer "
    "computed_field".split()
)
_E4_NAMES = frozenset(
    "setUp tearDown setUpClass tearDownClass setUpModule tearDownModule setup_method "
    "teardown_method setup_class teardown_class setup_function teardown_function".split()
)
_E5_DECORATORS = frozenset(
    "receiver action api_view login_required permission_required csrf_exempt "
    "require_http_methods require_GET require_POST".split()
)
_E5_BASES = tuple(
    "View ViewSet Mixin ModelAdmin Serializer Form Model Middleware AppConfig BaseCommand "
    "Migration TestCase".split()
)
_E5_FILES = frozenset(
    "urls.py admin.py apps.py settings.py wsgi.py asgi.py manage.py conftest.py".split()
)
_E6 = frozenset({"command", "group", "callback", "argument", "option"})
_E8 = frozenset(
    "task shared_task periodic_task job scheduled_job listens_for event hookimpl hookspec "
    "tool resource prompt".split()
)
_E9_PREFIXES = ("visit_", "leave_", "do_", "handle_")
# PY-F1 benign decorators: matched on the final name, or on the module prefix for the starred ones
BENIGN_DECORATORS = frozenset(
    "staticmethod classmethod property setter getter deleter cached_property lru_cache cache wraps "
    "contextmanager asynccontextmanager singledispatch singledispatchmethod total_ordering final "
    "override deprecated no_type_check dataclass".split()
)
BENIGN_PREFIXES = ("typing.", "functools.", "contextlib.")
_SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__"})

_TARGET = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*:\s*([A-Za-z_]\w*)")
_BLOCK = re.compile(r"(?:console_scripts|gui_scripts)\W{0,5}(.*?)(?:\]|\n\[|\Z)", re.DOTALL)
_ENTRY = re.compile(r"[\w.\-]+\s*=\s*([A-Za-z_][\w.]*)\s*:\s*([A-Za-z_]\w*)")


def is_benign(d: DecoratorInfo) -> bool:
    """PY-F1: a decorator that does not change the signature or hide the function."""
    return d.final_name in BENIGN_DECORATORS or d.dotted.startswith(BENIGN_PREFIXES)


def _target(value: object) -> tuple[str, str] | None:
    m = _TARGET.match(value) if isinstance(value, str) else None
    return (m.group(1), m.group(2)) if m else None


def _toml_entries(data: dict[str, Any]) -> list[object]:
    project = data.get("project", {})
    poetry = data.get("tool", {}).get("poetry", {})
    tables = [project.get("scripts"), project.get("gui-scripts"), poetry.get("scripts")]
    tables.extend((project.get("entry-points") or {}).values())
    return [v for t in tables if isinstance(t, dict) for v in t.values()]


def load_script_entries(root: Path, text_files: tuple[str, ...]) -> frozenset[tuple[str, str]]:
    """Collect `(module, function)` pairs declared as installed scripts (PY-E6)."""
    found: set[tuple[str, str]] = set()
    for rel in text_files:
        if PurePosixPath(rel).name != "pyproject.toml":
            continue
        try:
            data = tomllib.loads((root / rel).read_bytes().decode("utf-8", "replace"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        found.update(t for v in _toml_entries(data) if (t := _target(v)))
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            if name not in ("setup.py", "setup.cfg"):
                continue
            try:
                text = (Path(dirpath) / name).read_bytes().decode("utf-8", "replace")
            except OSError:
                continue
            for block in _BLOCK.finditer(text):
                found.update(_ENTRY.findall(block.group(1)))
    return frozenset(found)


def _module(path: str) -> tuple[str, ...]:
    parts = PurePosixPath(path).with_suffix("").parts
    return parts[:-1] if parts and parts[-1] == "__init__" else parts


def _in_scripts(func: FunctionDef, scripts: frozenset[tuple[str, str]]) -> bool:
    mod = _module(func.file_path)
    for script_mod, name in scripts:
        want = tuple(script_mod.split("."))
        if name == func.name and len(want) <= len(mod) and mod[len(mod) - len(want) :] == want:
            return True
    return False


def _bases_end(cls: ClassDef | None, suffixes: tuple[str, ...]) -> bool:
    return cls is not None and any(b.endswith(suffixes) for b in cls.base_names)


def exempt_rule(
    func: FunctionDef,
    cls: ClassDef | None,
    file: SourceFile,
    scripts: frozenset[tuple[str, str]],
) -> str | None:
    """Return the ID of the first matching PY-E rule, or None."""
    name = func.name
    finals = {d.final_name for d in func.decorators}
    path = PurePosixPath(file.path)
    top = func.class_name is None
    if (top and name == "main") or path.name == "__main__.py":
        return "PY-E1"
    if name.startswith("__") and name.endswith("__"):
        return "PY-E2"
    if finals & _E3:
        return "PY-E3"
    if (
        file.is_test
        or name.startswith(("test_", "pytest_"))
        or name in _E4_NAMES
        or any(f.endswith("fixture") for f in finals)
        or (cls is not None and cls.name.startswith("Test"))
        or _bases_end(cls, ("TestCase",))
    ):
        return "PY-E4"
    in_views = path.name == "views.py" or "views" in path.parts[:-1]
    if (
        (top and func.params.positional[:1] == ("request",) and in_views)
        or _bases_end(cls, _E5_BASES)
        or finals & _E5_DECORATORS
        or any(d.dotted.split(".")[-2:] == ["admin", "register"] for d in func.decorators)
        or "/management/commands/" in f"/{file.path}"
        or path.name in _E5_FILES
    ):
        return "PY-E5"
    if finals & _E6 or _in_scripts(func, scripts):
        return "PY-E6"
    if func.body_kind == "stub" or any(f.endswith(("abstractmethod", "overload")) for f in finals):
        return "PY-E7"
    if finals & _E8:
        return "PY-E8"
    if (name == "run" and _bases_end(cls, ("Thread", "Process"))) or (
        cls is not None
        and cls.base_names
        and (name in ("generic_visit", "handle") or name.startswith(_E9_PREFIXES))
    ):
        return "PY-E9"
    return None
