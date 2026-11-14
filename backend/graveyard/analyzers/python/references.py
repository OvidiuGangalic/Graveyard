"""Collect name occurrences (rules PY-R1..PY-R6) from one file."""

from __future__ import annotations

import ast
import re
import warnings
from typing import Any

from graveyard.analyzers.python.records import CallShape, Occurrence

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_Func = ast.FunctionDef | ast.AsyncFunctionDef
_Ctx = tuple[str | None, bool]  # (enclosing top-level class, directly in class body)


def _tokens(text: str, line: int | None = None, ctx: _Ctx = (None, False)) -> list[Occurrence]:
    out = []
    for i, src in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        out += [
            Occurrence(m.group(), line or i, "token", None, ctx[0], ctx[1], False, None)
            for m in _TOKEN.finditer(src)
        ]
    return out


def _dotted(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return None if head is None else f"{head}.{node.attr}"
    return None


def _receiver(node: ast.expr) -> str | None:
    is_super = (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "super"
    )
    return "super()" if is_super else _dotted(node)


def _parse(text: str, **kwargs: Any) -> Any:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(text, **kwargs)


class _Collector:
    def __init__(self) -> None:
        self.out: list[Occurrence] = []
        self.shapes: dict[int, CallShape] = {}
        self.line: int | None = None  # fixed line while visiting a parsed string
        self.self_param: str | None = None  # first parameter of the enclosing method
        self.depth = 0  # class nesting depth

    def add(self, node: Any, name: str, form: Any, receiver: str | None, ctx: _Ctx) -> None:
        line = self.line or getattr(node, "end_lineno", None) or node.lineno
        store = isinstance(getattr(node, "ctx", None), ast.Store | ast.Del)
        shape = self.shapes.get(id(node))
        self.out.append(
            Occurrence(name, line, form, receiver, ctx[0], ctx[1], store, shape, self.self_param)
        )

    def string(self, text: str, node: Any, ctx: _Ctx, mode: str) -> None:
        line = self.line or node.lineno
        try:
            tree = _parse(text.strip(), mode=mode)
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            self.out += _tokens(text, line, ctx)
            return
        saved, self.line = self.line, line
        self.visit(tree, ctx)
        self.line = saved

    def visit(self, node: ast.AST, ctx: _Ctx, ann: bool = False) -> None:
        tc = getattr(node, "type_comment", None)
        if isinstance(tc, str):
            self.string(tc, node, ctx, "func_type" if isinstance(node, _Func) else "eval")
        if isinstance(node, ast.Name):
            self.add(node, node.id, "name", None, ctx)
        elif isinstance(node, ast.Attribute):
            self.add(node, node.attr, "attr", _receiver(node.value), ctx)
            self.visit(node.value, ctx)
        elif isinstance(node, ast.Call):
            self.shapes[id(node.func)] = CallShape(
                sum(not isinstance(a, ast.Starred) for a in node.args),
                tuple(k.arg for k in node.keywords if k.arg),
                any(isinstance(a, ast.Starred) for a in node.args)
                or any(k.arg is None for k in node.keywords),
            )
            self.children(node, ctx)
        elif isinstance(node, ast.Constant):
            if ann and isinstance(node.value, str):
                self.string(node.value, node, ctx, "eval")
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name != "*":
                    self.add(a, a.name, "import", None, ctx)
        elif isinstance(node, ast.Import):
            for a in node.names:
                for seg in a.name.split("."):
                    self.add(a, seg, "import", None, ctx)
        elif isinstance(node, ast.arg):  # PY-R5: the name itself is not an occurrence
            if node.annotation:
                self.visit(node.annotation, ctx, True)
        elif isinstance(node, ast.AnnAssign):
            self.visit(node.target, ctx)
            self.visit(node.annotation, ctx, True)
            if node.value:
                self.visit(node.value, ctx)
        elif isinstance(node, _Func):
            for d in node.decorator_list:
                self.visit(d, ctx)
            self.visit(node.args, ctx)
            if node.returns:
                self.visit(node.returns, ctx, True)
            saved = self.self_param
            if ctx[1]:
                first = [*node.args.posonlyargs, *node.args.args][:1]
                static = any(_dotted(d) == "staticmethod" for d in node.decorator_list)
                ok = self.depth == 1 and first and not static
                self.self_param = first[0].arg if ok else None
            elif ctx[0] is None:
                self.self_param = None
            for s in node.body:
                self.visit(s, (ctx[0], False))
            self.self_param = saved
        elif isinstance(node, ast.ClassDef):
            for e in (*node.decorator_list, *node.bases, *node.keywords):
                self.visit(e, ctx)
            self.depth += 1
            for s in node.body:
                self.visit(s, (ctx[0] or node.name, True))
            self.depth -= 1
        else:
            self.children(node, ctx, ann)

    def children(self, node: ast.AST, ctx: _Ctx, ann: bool = False) -> None:
        for child in ast.iter_child_nodes(node):
            self.visit(child, ctx, ann)


def collect_occurrences(text: str, tree: ast.Module | None) -> tuple[Occurrence, ...]:
    """All occurrences, sorted by (line, name, form).

    Text containing `# type:` is re-parsed with ``type_comments=True`` (`tree` is the fallback).
    """
    text = text.replace("\r\n", "\n")
    if tree is not None and "# type:" in text:
        try:
            tree = _parse(text, type_comments=True)
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            pass
    found: list[Occurrence] | None = None
    if tree is not None:
        collector = _Collector()
        try:
            collector.visit(tree, (None, False))
            found = collector.out
        except RecursionError:
            found = None
    if found is None:
        found = _tokens(text)
    return tuple(sorted(found, key=lambda o: (o.line, o.name, o.form)))
