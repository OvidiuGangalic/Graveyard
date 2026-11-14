"""Collect analysable functions and classes from one file."""

from __future__ import annotations

import ast
import warnings

from graveyard.analyzers.python.records import (
    ClassDef,
    DecoratorInfo,
    FileFacts,
    FunctionDef,
    Param,
)

_FuncNode = ast.FunctionDef | ast.AsyncFunctionDef


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


def collect_definitions(path: str, text: str) -> FileFacts:
    """Collect the per-file facts; an unparseable file yields ``parsed=False``."""
    text = text.replace("\r\n", "\n")
    tree = parse_module(text)
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
    return FileFacts(
        path=path,
        parsed=True,
        functions=tuple(_merge(funcs)),
        classes=tuple(classes),
        has_module_getattr=any(f.name == "__getattr__" and f.class_name is None for f in funcs),
        lines=tuple(text.split("\n")),
    )
