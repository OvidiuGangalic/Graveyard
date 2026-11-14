"""Collect functions and classes (TS-D1 to TS-D4) and their exported status from one file."""

from __future__ import annotations

import posixpath

from tree_sitter import Node, Tree

from graveyard.analyzers.typescript.parser import end_line, has_error, line, text, walk
from graveyard.analyzers.typescript.records import TsClass, TsFileFacts, TsFunction, TsParams

_FUNC_VALUES = {"arrow_function", "function_expression", "generator_function"}
_FUNC_DECLS = {"function_declaration", "generator_function_declaration"}
_CLASSES = {"class_declaration", "abstract_class_declaration", "class"}
_OTHER_DECLS = {"interface_declaration", "type_alias_declaration", "enum_declaration"}
_BINDINGS = {"identifier", "shorthand_property_identifier_pattern"}
_MODULE_EXTS = {".ts", ".tsx", ".mjs"}


def _params(node: Node | None) -> TsParams:
    total = required = 0
    rest = False
    for p in node.named_children if node else ():
        pattern = p.child_by_field_name("pattern")
        kind = pattern.type if pattern is not None else ""
        if p.type not in {"required_parameter", "optional_parameter"} or kind == "this":
            continue
        rest = rest or kind == "rest_pattern"
        if kind != "rest_pattern":
            total += 1
            required += p.type == "required_parameter" and p.child_by_field_name("value") is None
    return TsParams(total, required, rest)


def _is_stub(body: Node | None) -> bool:
    if body is None or body.type != "statement_block":
        return body is None
    stmts = [c for c in body.named_children if c.type != "comment"]
    return not stmts or (len(stmts) == 1 and stmts[0].type == "throw_statement")


def _decorators(first: Node, own: Node) -> list[Node]:
    """Decorator siblings written directly before `first`, then decorator children of `own`."""
    lead: list[Node] = []
    prev = first.prev_sibling
    while prev is not None and prev.type == "decorator":
        lead.insert(0, prev)
        prev = prev.prev_sibling
    return lead + [c for c in own.children if c.type == "decorator"]


def _cjs_exports(root: Node) -> set[str]:
    names: set[str] = set()
    for stmt in root.named_children:
        expr = stmt.named_children[0] if stmt.type == "expression_statement" else None
        if expr is None or expr.type != "assignment_expression":
            continue
        left, right = expr.child_by_field_name("left"), expr.child_by_field_name("right")
        target = text(left) if left is not None else ""
        if right is not None and target == "module.exports" and right.type == "object":
            for c in right.named_children:
                value = c.child_by_field_name("value") if c.type == "pair" else c
                if value is not None and value.type.endswith("identifier"):
                    names.add(text(value))
        elif right is not None and right.type == "identifier":
            if target == "module.exports" or target.startswith(("module.exports.", "exports.")):
                names.add(text(right))
    return names


def _import_names(node: Node) -> set[str]:
    names: set[str] = set()
    for n in walk(node):
        if n.type == "import_specifier":
            names.add(text(n.child_by_field_name("alias") or n.child_by_field_name("name")))
        elif n.type == "identifier" and n.parent.type in {"import_clause", "namespace_import"}:
            names.add(text(n))
    return names


def _extends(cls: Node) -> tuple[str | None, str | None]:
    heritage = next((c for c in cls.named_children if c.type == "class_heritage"), None)
    if heritage is None or not heritage.named_children:
        return None, None
    first = heritage.named_children[0]  # JavaScript: the expression; TypeScript: extends_clause
    expr = first.child_by_field_name("value") if first.type == "extends_clause" else first
    if expr is None or first.type == "implements_clause":
        return None, None
    return text(expr), text(expr.child_by_field_name("property") or expr)


class _Collector:
    def __init__(self, path: str, base: str, exported: set[str]) -> None:
        self.path, self.base, self.exported = path, base, exported
        self.functions: list[TsFunction] = []
        self.classes: list[TsClass] = []
        self.overloads: set[tuple[str, int]] = set()
        self.pending: list[Node] = []  # overload signatures awaiting their implementation

    def signature(self, node: Node, outer: Node) -> None:
        name = node.child_by_field_name("name")
        if name is not None:
            self.overloads.add((text(name), line(name)))
            self.pending.append(outer)

    def function(
        self, node: Node, outer: Node, name: str, exported: bool, cls: str | None = None, **kw: bool
    ) -> None:
        """Record one function; pending overload signatures are merged into its Span."""
        first = self.pending[0] if self.pending else outer
        self.pending.clear()
        decos = _decorators(first, outer) if cls else []
        start = min([first, *decos], key=lambda n: n.start_byte)
        if cls is None and exported:
            self.exported.add(name)
        self.functions.append(
            TsFunction(
                name=name,
                qualified_name=f"{cls}.{name}" if cls else name,
                file_path=self.path,
                class_name=cls,
                start_line=line(start),
                end_line=end_line(outer),
                is_exported=exported,
                is_default=kw.get("default", False),
                is_method=cls is not None,
                is_async_or_generator=any(c.type == "async" for c in node.children)
                or "generator" in node.type,
                decorators=tuple(text(d) for d in decos),
                params=_params(node.child_by_field_name("parameters")),
                body_kind="stub" if _is_stub(node.child_by_field_name("body")) else "normal",
                is_abstract=kw.get("abstract", False),
            )
        )

    def klass(self, node: Node, outer: Node, in_export: bool) -> None:
        name_node = node.child_by_field_name("name")
        name = text(name_node) if name_node is not None else self.base
        exported = in_export or name in self.exported
        decos = _decorators(outer, outer) if in_export else []
        decos += [c for c in node.children if c.type == "decorator"]
        start = min([outer, *decos], key=lambda n: n.start_byte)
        methods: list[str] = []
        self.pending.clear()
        for member in (node.child_by_field_name("body") or node).named_children:
            kind, mname = member.type, member.child_by_field_name("name")
            value = member.child_by_field_name("value")
            if mname is None or mname.type == "computed_property_name":
                self.pending.clear()
            elif kind == "method_signature":
                self.signature(member, member)
            elif kind == "abstract_method_signature" or (
                kind == "method_definition"
                and text(mname) != "constructor"
                and not any(c.type in {"get", "set"} for c in member.children)
            ):
                methods.append(text(mname))
                abstract = kind == "abstract_method_signature"
                self.function(member, member, text(mname), exported, name, abstract=abstract)
            elif kind == "public_field_definition" and value and value.type == "arrow_function":
                methods.append(text(mname))
                self.function(value, member, text(mname), exported, name)
            else:
                self.pending.clear()
        extends, extends_name = _extends(node)
        self.classes.append(
            TsClass(
                name=name,
                file_path=self.path,
                start_line=line(start),
                end_line=end_line(outer),
                extends=extends,
                extends_name=extends_name,
                implements=any(n.type == "implements_clause" for n in walk(node)),
                decorators=tuple(text(d) for d in decos),
                method_names=tuple(methods),
                is_exported=exported,
            )
        )


def collect_definitions(path: str, data: bytes, tree: Tree | None) -> TsFileFacts:
    """Collect definitions from one file; no tree or a tree with errors gives `parsed=False`."""
    lines = tuple(data.decode("utf-8", errors="replace").splitlines())
    if tree is None or has_error(tree):
        return TsFileFacts(path=path, parsed=False, lines=lines)
    root = tree.root_node
    base, ext = posixpath.splitext(posixpath.basename(path))
    exported = _cjs_exports(root)
    top: set[str] = set()
    has_default = False
    items: list[tuple[Node, Node]] = []  # (declaration, statement that carries it)
    for stmt in root.named_children:
        if stmt.type == "import_statement":
            top |= _import_names(stmt)
        elif stmt.type != "export_statement":
            items.append((stmt, stmt))
            continue
        has_default = has_default or any(c.type == "default" for c in stmt.children)
        clause = next((c for c in stmt.named_children if c.type == "export_clause"), None)
        if clause is not None and stmt.child_by_field_name("source") is None:
            exported |= {text(s.child_by_field_name("name")) for s in clause.named_children}
        value = stmt.child_by_field_name("value")
        if value is not None and value.type == "identifier":
            exported.add(text(value))
        items += [(n, stmt) for f in ("declaration", "value") if (n := stmt.child_by_field_name(f))]

    c = _Collector(path, base, exported)
    for node, outer in items:
        in_export, kind = outer is not node, node.type
        name_node = node.child_by_field_name("name")
        if kind != "function_signature" and kind not in _FUNC_DECLS:
            c.pending.clear()
        if kind == "function_signature":
            c.signature(node, outer)
        elif kind in _FUNC_DECLS:
            name = text(name_node) if name_node is not None else base
            top.add(name)
            default = in_export and any(x.type == "default" for x in outer.children)
            c.function(node, outer, name, in_export or name in exported, default=default)
        elif kind in _FUNC_VALUES:  # TS-D4: only reachable through an export statement
            c.function(node, outer, base, True, default=True)
        elif kind in {"lexical_declaration", "variable_declaration"}:
            decls = [d for d in node.named_children if d.type == "variable_declarator"]
            for d in decls:
                target, value = d.child_by_field_name("name"), d.child_by_field_name("value")
                top |= {text(n) for n in walk(target) if n.type in _BINDINGS}
                if target.type == "identifier" and value is not None and value.type in _FUNC_VALUES:
                    name = text(target)
                    span = outer if len(decls) == 1 else d
                    c.function(value, span, name, in_export or name in exported)
        elif kind in _CLASSES:
            top |= {text(name_node)} if name_node is not None else set()
            c.klass(node, outer, in_export)
        elif kind in _OTHER_DECLS and name_node is not None:
            top.add(text(name_node))

    return TsFileFacts(
        path=path,
        parsed=True,
        is_es_module=ext.lower() in _MODULE_EXTS
        or any(n.type in {"import_statement", "export_statement"} for n in root.children),
        functions=tuple(c.functions),
        classes=tuple(c.classes),
        top_level_names=frozenset(top),
        exported_names=frozenset(exported),
        has_default_export=has_default,
        overload_name_lines=frozenset(c.overloads),
        lines=lines,
    )
