"""Collect analysable functions, classes and module-level bindings from one file."""

from __future__ import annotations

import ast
import warnings
from collections.abc import Iterator

from graveyard.analyzers.python.records import (
    ClassDef,
    DecoratorInfo,
    FileFacts,
    FunctionDef,
    ModuleBinding,
    Param,
)

_FuncNode = ast.FunctionDef | ast.AsyncFunctionDef
_BLOCK_FIELDS = ("body", "orelse", "finalbody", "handlers")


def parse_module(text: str) -> ast.Module | None:
    """Parse source text; return None on any failure. Never raises."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # e.g. SyntaxWarning for "\d" in analysed code
            return ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def _final_name(node: ast.expr) -> str:
    """Last name of a base or decorator expression: `typing.Generic[T]` -> `Generic`."""
    while isinstance(node, ast.Subscript | ast.Call):
        node = node.value if isinstance(node, ast.Subscript) else node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    return node.id if isinstance(node, ast.Name) else ast.unparse(node)


def _decorator(node: ast.expr) -> DecoratorInfo:
    target = node.func if isinstance(node, ast.Call) else node
    dotted = ast.unparse(target)
    return DecoratorInfo(
        source=ast.unparse(node),
        final_name=dotted.rsplit(".", 1)[-1],
        dotted=dotted,
        is_call=isinstance(node, ast.Call),
    )


def _params(args: ast.arguments) -> Param:
    positional = [a.arg for a in (*args.posonlyargs, *args.args)]
    required = tuple(
        a.arg for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=True) if d is None
    )
    return Param(
        positional=tuple(positional),
        positional_defaults=len(args.defaults),
        kwonly=tuple(a.arg for a in args.kwonlyargs),
        kwonly_required=required,
        has_vararg=args.vararg is not None,
        has_kwarg=args.kwarg is not None,
    )


def _is_stub_stmt(stmt: ast.stmt, is_first: bool) -> bool:
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
        value = stmt.value.value
        return value is Ellipsis or (is_first and isinstance(value, str))
    if isinstance(stmt, ast.Raise) and stmt.exc is not None:
        exc = stmt.exc.func if isinstance(stmt.exc, ast.Call) else stmt.exc
        return isinstance(exc, ast.Name) and exc.id == "NotImplementedError"
    return False


def _body_kind(node: _FuncNode) -> str:
    stub = all(_is_stub_stmt(s, i == 0) for i, s in enumerate(node.body))
    return "stub" if stub else "normal"


def _function(node: _FuncNode, path: str, cls: str | None) -> FunctionDef:
    decorators = tuple(_decorator(d) for d in node.decorator_list)
    first = min([node.lineno, *(d.lineno for d in node.decorator_list)])
    return FunctionDef(
        name=node.name,
        qualified_name=f"{cls}.{node.name}" if cls else node.name,
        file_path=path,
        class_name=cls,
        start_line=first,
        end_line=node.end_lineno or node.lineno,
        is_async=isinstance(node, ast.AsyncFunctionDef),
        decorators=decorators,
        params=_params(node.args),
        body_kind=_body_kind(node),  # type: ignore[arg-type]
        is_staticmethod=any(d.final_name == "staticmethod" for d in decorators),
    )


def _merge(funcs: list[FunctionDef]) -> list[FunctionDef]:
    """Requirement 1.3: same name in one scope -> last Span, all decorators."""
    merged: dict[tuple[str | None, str], FunctionDef] = {}
    for f in funcs:
        prev = merged.get((f.class_name, f.name))
        if prev is not None:
            f = FunctionDef(**{**f.__dict__, "decorators": prev.decorators + f.decorators})
        merged[(f.class_name, f.name)] = f
    return list(merged.values())


def _module_blocks(stmts: list[ast.stmt]) -> Iterator[ast.stmt]:
    """Yield module-level statements, descending into if/try/with/for/while blocks."""
    for stmt in stmts:
        yield stmt
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        for field in _BLOCK_FIELDS:
            for child in getattr(stmt, field, None) or []:
                if isinstance(child, ast.ExceptHandler):
                    yield from _module_blocks(child.body)
                elif isinstance(child, ast.stmt):
                    yield from _module_blocks([child])
        for case in getattr(stmt, "cases", None) or []:
            yield from _module_blocks(case.body)


def _target_names(target: ast.expr) -> Iterator[str]:
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, ast.Tuple | ast.List):
        for elt in target.elts:
            yield from _target_names(elt)
    elif isinstance(target, ast.Starred):
        yield from _target_names(target.value)


def _strings(value: ast.expr | None) -> list[str]:
    if not isinstance(value, ast.List | ast.Tuple):
        return []
    return [e.value for e in value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]


def _bindings(
    tree: ast.Module,
) -> tuple[list[ModuleBinding], list[str], list[tuple[str | None, int]]]:
    out: list[ModuleBinding] = []
    dunder_all: list[str] = []
    star: list[tuple[str | None, int]] = []
    for stmt in _module_blocks(tree.body):
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
            out.append(ModuleBinding(stmt.name, "def", stmt.lineno))
        elif isinstance(stmt, ast.ClassDef):
            out.append(ModuleBinding(stmt.name, "class", stmt.lineno))
        elif isinstance(stmt, ast.Assign | ast.AnnAssign | ast.AugAssign):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            for target in targets:
                for name in _target_names(target):
                    out.append(ModuleBinding(name, "assign", stmt.lineno))
                    if name == "__all__":
                        dunder_all += _strings(stmt.value)
        elif isinstance(stmt, ast.Import):
            for a in stmt.names:
                name = a.asname or a.name.split(".")[0]
                out.append(ModuleBinding(name, "import", stmt.lineno, a.name))
        elif isinstance(stmt, ast.ImportFrom):
            for a in stmt.names:
                if a.name == "*":
                    star.append((stmt.module, stmt.level))
                else:
                    name = a.asname or a.name
                    out.append(
                        ModuleBinding(name, "import", stmt.lineno, stmt.module, stmt.level, a.name)
                    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            out += [ModuleBinding(n, "global", node.lineno) for n in node.names]
    return out, dunder_all, star


_DYNAMIC_CALLS = {"globals", "locals", "vars", "eval", "exec", "__import__"}


def _is_dynamic(node: ast.AST) -> bool:
    """PY-F3: a construct that can reach a name by a runtime string."""
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name):
            if f.id in _DYNAMIC_CALLS:
                return True
            if f.id in {"getattr", "setattr", "hasattr"} and len(node.args) > 1:
                arg = node.args[1]
                return not (isinstance(arg, ast.Constant) and isinstance(arg.value, str))
        return isinstance(f, ast.Attribute) and ast.unparse(f) == "importlib.import_module"
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and ast.unparse(node.value) == "sys.modules"
    )


def _local_import_names(tree: ast.Module) -> frozenset[str]:
    """Names (alias, imported name, module segments) of imports outside module-level blocks."""
    top = {id(s) for s in _module_blocks(tree.body)}
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom) and id(node) not in top:
            for a in node.names:
                names |= {a.asname or a.name, *a.name.split(".")}
                names.add(a.name.split(".")[0])
    return frozenset(names)


def collect_definitions(path: str, text: str, tree: ast.Module | None = None) -> FileFacts:
    """Collect the per-file facts; an unparseable file yields ``parsed=False``.

    ``tree`` is the already-parsed module, when the caller has one.
    """
    text = text.replace("\r\n", "\n")
    tree = tree or parse_module(text)
    if tree is None:
        return FileFacts(path=path, parsed=False)
    funcs: list[FunctionDef] = []
    classes: list[ClassDef] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
            funcs.append(_function(stmt, path, None))
        elif isinstance(stmt, ast.ClassDef):
            methods = [
                _function(n, path, stmt.name)
                for n in stmt.body
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
            ]
            funcs += methods
            bases = tuple(ast.unparse(b) for b in stmt.bases)
            classes.append(
                ClassDef(
                    name=stmt.name,
                    file_path=path,
                    start_line=min([stmt.lineno, *(d.lineno for d in stmt.decorator_list)]),
                    end_line=stmt.end_lineno or stmt.lineno,
                    bases=bases,
                    base_names=tuple(_final_name(b) for b in stmt.bases),
                    method_names=tuple(dict.fromkeys(m.name for m in methods)),
                    decorators=tuple(_decorator(d) for d in stmt.decorator_list),
                )
            )
    bindings, dunder_all, star = _bindings(tree)
    return FileFacts(
        path=path,
        parsed=True,
        functions=tuple(_merge(funcs)),
        classes=tuple(classes),
        bindings=tuple(bindings),
        dunder_all=tuple(dunder_all),
        has_module_getattr=any(f.name == "__getattr__" and f.class_name is None for f in funcs),
        has_star_import=bool(star),
        star_imports=tuple(star),
        local_import_names=_local_import_names(tree),
        has_dynamic_lookup=any(_is_dynamic(n) for n in ast.walk(tree)),
        lines=tuple(text.split("\n")),
    )
