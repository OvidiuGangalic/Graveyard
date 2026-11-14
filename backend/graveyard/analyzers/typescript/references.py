"""Raw per-file facts for the TypeScript analyzer: occurrences, specifiers, strings."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from tree_sitter import Node, Tree

from graveyard.analyzers.typescript.parser import line, text, walk

Form = Literal["name", "member", "jsx", "type", "specifier", "token"]
SpecKind = Literal["static", "reexport", "reexport_all", "require", "dynamic"]

_TOKEN = re.compile(rb"[A-Za-z_$][A-Za-z0-9_$]*")
_DEFINING = {
    "function_declaration",
    "generator_function_declaration",
    "class_declaration",
    "abstract_class_declaration",
    "interface_declaration",
    "type_alias_declaration",
}
_CLASSES = {"class_declaration", "abstract_class_declaration", "class"}
_JSX_OPEN = {"jsx_opening_element", "jsx_self_closing_element"}
_GLOBAL_OBJECTS = {"this", "window", "globalThis", "global", "exports", "module.exports"}
_LITERAL_KEYS = {"string", "number"}


@dataclass(frozen=True)
class TsOccurrence:
    name: str
    line: int
    form: Form
    receiver: str | None = None
    enclosing_class: str | None = None
    call_args: int | None = None
    call_has_spread: bool = False


@dataclass(frozen=True)
class TsSpecifier:
    spec: str
    line: int
    kind: SpecKind
    names: tuple[tuple[str, str], ...] = ()


def _receiver(obj: Node | None) -> str | None:
    """Dotted text of an identifier / this / super / member chain of identifiers, else None."""
    parts: list[str] = []
    while obj is not None and obj.type == "member_expression":
        prop = obj.child_by_field_name("property")
        if prop is None:
            return None
        parts.append(text(prop))
        obj = obj.child_by_field_name("object")
    if obj is None or obj.type not in {"identifier", "this", "super"}:
        return None
    parts.append(text(obj))
    return ".".join(reversed(parts))


def _callee_of(node: Node) -> Node | None:
    """The call_expression whose callee is `node`, or None."""
    parent = node.parent
    if parent is not None and parent.type == "call_expression":
        if parent.child_by_field_name("function") == node:
            return parent
    return None


def _jsx_name_root(node: Node) -> Node | None:
    """The opening / self-closing element when `node` is part of its name, else None."""
    cur = node
    while cur.parent is not None and cur.parent.type == "member_expression":
        cur = cur.parent
    parent = cur.parent
    if (
        parent is not None
        and parent.type in _JSX_OPEN
        and parent.child_by_field_name("name") == cur
    ):
        return parent
    return None


def _occ(node: Node, form: Form, cls: str | None, name: str | None = None) -> TsOccurrence:
    receiver = None
    target = node
    if form == "member" and node.parent is not None and node.parent.type == "member_expression":
        receiver = _receiver(node.parent.child_by_field_name("object"))
        target = node.parent
    elif (
        form == "jsx"
        and node.parent is not None
        and node.parent.child_by_field_name("property") == node
    ):
        receiver = _receiver(node.parent.child_by_field_name("object"))
    call = _callee_of(target)
    args = call.child_by_field_name("arguments") if call is not None else None
    items = [c for c in args.named_children if c.type != "comment"] if args is not None else []
    return TsOccurrence(
        name if name is not None else text(node),
        line(node),
        form,
        receiver,
        cls,
        len(items) if args is not None else None,
        any(c.type == "spread_element" for c in items),
    )


def _classify(node: Node, cls: str | None, skip: frozenset[tuple[str, int]]) -> TsOccurrence | None:
    kind, parent = node.type, node.parent
    if kind == "identifier":
        if parent is None or (text(node), line(node)) in skip:
            return None
        if parent.type in _DEFINING and parent.child_by_field_name("name") == node:
            return None
        if parent.type == "jsx_closing_element":
            return None
        if _jsx_name_root(node) is not None:
            return (
                _occ(node, "jsx", cls)
                if not text(node)[:1].islower() or parent.type == "member_expression"
                else None
            )
        return _occ(node, "type" if parent.type == "type_query" else "name", cls)
    if kind == "property_identifier" and parent is not None and parent.type == "member_expression":
        if parent.child_by_field_name("property") != node:
            return None
        return _occ(node, "jsx" if _jsx_name_root(parent) is not None else "member", cls)
    if kind == "shorthand_property_identifier":
        return _occ(node, "name", cls)
    if kind == "shorthand_property_identifier_pattern":
        return _occ(node, "member", cls)
    if kind == "type_identifier":
        if (
            parent is not None
            and parent.type in _DEFINING
            and parent.child_by_field_name("name") == node
        ):
            return None
        return _occ(node, "type", cls)
    return None


def collect_occurrences(
    tree: Tree, data: bytes, skip: frozenset[tuple[str, int]] = frozenset()
) -> tuple[TsOccurrence, ...]:
    """TS-R1..TS-R6 occurrences; parse-error trees fall back to identifier-like tokens."""
    if tree.root_node.has_error:
        out = []
        pos, ln = 0, 1
        for m in _TOKEN.finditer(data):
            ln += data.count(b"\n", pos, m.start())
            pos = m.start()
            out.append(TsOccurrence(m.group().decode(), ln, "token", None, None, None, False))
        return tuple(out)
    out = []
    stack: list[tuple[Node, str | None]] = [(tree.root_node, None)]
    while stack:
        node, cls = stack.pop()
        kind = node.type
        if kind in {"import_specifier", "export_specifier"}:
            name = node.child_by_field_name("name")
            if name is not None:
                out.append(_occ(name, "specifier", cls))
            continue
        if kind in {"namespace_import", "import_require_clause", "namespace_export"}:
            continue
        if kind == "import_clause":
            stack.extend((c, cls) for c in reversed(node.children) if c.type == "named_imports")
            continue
        if kind in _CLASSES:
            name = node.child_by_field_name("name")
            cls = text(name) if name is not None else cls
        found = _classify(node, cls, skip)
        if found is not None:
            out.append(found)
        stack.extend((c, cls) for c in reversed(node.children))
    return tuple(out)


def _fragment(string: Node | None) -> str | None:
    if string is None or string.type != "string":
        return None
    return "".join(text(c) for c in string.children if c.type == "string_fragment")


def _first_arg(call: Node) -> Node | None:
    args = call.child_by_field_name("arguments")
    return args.named_children[0] if args is not None and args.named_children else None


def _call_target(call: Node) -> str | None:
    fn = call.child_by_field_name("function")
    if fn is None:
        return None
    return "import" if fn.type == "import" else text(fn) if fn.type == "identifier" else None


def _pattern_names(pattern: Node) -> tuple[tuple[str, str], ...]:
    names = []
    for c in pattern.named_children:
        if c.type in {"shorthand_property_identifier_pattern"}:
            names.append((text(c), text(c)))
        elif c.type == "object_assignment_pattern":
            left = c.child_by_field_name("left")
            if left is not None:
                names.append((text(left), text(left)))
        elif c.type == "pair_pattern":
            key, value = c.child_by_field_name("key"), c.child_by_field_name("value")
            if key is not None and value is not None and value.type == "identifier":
                names.append((text(key), text(value)))
    return tuple(names)


def _clause_names(clause: Node) -> tuple[tuple[str, str], ...]:
    names = []
    for c in clause.children:
        if c.type == "identifier":
            names.append(("default", text(c)))
        elif c.type == "namespace_import":
            ident = next((i for i in c.children if i.type == "identifier"), None)
            if ident is not None:
                names.append(("*", text(ident)))
        elif c.type in {"named_imports", "export_clause"}:
            for s in c.children:
                if s.type in {"import_specifier", "export_specifier"}:
                    n, a = s.child_by_field_name("name"), s.child_by_field_name("alias")
                    if n is not None:
                        names.append((text(n), text(a if a is not None else n)))
        elif c.type == "namespace_export":
            ident = next((i for i in c.children if i.type == "identifier"), None)
            if ident is not None:
                names.append(("*", text(ident)))
    return tuple(names)


def collect_specifiers(tree: Tree) -> tuple[TsSpecifier, ...]:
    """Module specifiers from static imports, re-exports, require() and import("literal")."""
    out = []
    for node in walk(tree.root_node):
        kind = node.type
        if kind in {"import_statement", "export_statement"}:
            spec = _fragment(node.child_by_field_name("source"))
            if spec is None:
                continue
            if kind == "import_statement":
                clause = next((c for c in node.children if c.type == "import_clause"), None)
                require = next(
                    (c for c in node.children if c.type == "import_require_clause"), None
                )
                if require is not None:
                    ident = next((c for c in require.children if c.type == "identifier"), None)
                    names = (("*", text(ident)),) if ident is not None else ()
                    out.append(TsSpecifier(spec, line(node), "require", names))
                else:
                    names = _clause_names(clause) if clause is not None else ()
                    out.append(TsSpecifier(spec, line(node), "static", names))
            else:
                clause = next(
                    (c for c in node.children if c.type in {"export_clause", "namespace_export"}),
                    None,
                )
                if clause is None:
                    out.append(TsSpecifier(spec, line(node), "reexport_all"))
                else:
                    names = _clause_names(node)
                    out.append(TsSpecifier(spec, line(node), "reexport", names))
        elif kind == "call_expression":
            target = _call_target(node)
            spec = _fragment(_first_arg(node)) if target in {"import", "require"} else None
            if spec is None:
                continue
            names: tuple[tuple[str, str], ...] = ()
            parent = node.parent
            if target == "require" and parent is not None and parent.type == "variable_declarator":
                bound = parent.child_by_field_name("name")
                if bound is not None and bound.type == "identifier":
                    names = (("*", text(bound)),)
                elif bound is not None and bound.type == "object_pattern":
                    names = _pattern_names(bound)
            out.append(
                TsSpecifier(
                    spec, line(node), "require" if target == "require" else "dynamic", names
                )
            )
    return tuple(out)


def collect_strings(tree: Tree) -> tuple[tuple[str, int], ...]:
    """(text, line) of string fragments, minus specifiers and import()/require() args (TS-F5)."""
    out = []
    for node in walk(tree.root_node):
        if node.type != "string_fragment":
            continue
        string = node.parent
        owner = string.parent if string is not None else None
        if string is not None and string.type == "string" and owner is not None:
            if owner.type in {"import_statement", "export_statement", "import_require_clause"}:
                continue
            call = owner.parent if owner.type == "arguments" else None
            if (
                call is not None
                and call.type == "call_expression"
                and _call_target(call) in {"import", "require"}
            ):
                continue
        out.append((text(node), line(node)))
    return tuple(out)


def _is_literal(node: Node | None) -> bool:
    if node is None:
        return False
    return node.type in _LITERAL_KEYS or (
        node.type == "template_string"
        and not any(c.type == "template_substitution" for c in node.children)
    )


def dynamic_patterns(tree: Tree) -> tuple[bool, bool]:
    """(TS-F6 dynamic pattern in file, computed member call `obj[expr](...)` for TS-F7)."""
    pattern = computed_call = False
    for node in walk(tree.root_node):
        kind = node.type
        if kind == "call_expression":
            fn = node.child_by_field_name("function")
            if fn is None:
                continue
            if fn.type == "identifier" and text(fn) == "eval":
                pattern = True
            elif fn.type == "import" and not _is_literal(_first_arg(node)):
                pattern = True
            elif fn.type == "subscript_expression" and not _is_literal(
                fn.child_by_field_name("index")
            ):
                computed_call = True
        elif kind == "new_expression":
            ctor = node.child_by_field_name("constructor")
            pattern = pattern or (
                ctor is not None and ctor.type == "identifier" and text(ctor) == "Function"
            )
        elif kind == "subscript_expression":
            obj = node.child_by_field_name("object")
            key = node.child_by_field_name("index")
            if obj is not None and text(obj) in _GLOBAL_OBJECTS and not _is_literal(key):
                pattern = True
    return pattern, computed_call
