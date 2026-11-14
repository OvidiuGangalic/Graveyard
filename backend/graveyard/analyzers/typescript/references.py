"""Raw per-file facts for the TypeScript analyzer: occurrences, specifiers, strings."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from tree_sitter import Node, Tree

from graveyard.analyzers.typescript.parser import line, text

Form = Literal["name", "member", "jsx", "type", "specifier", "token"]
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


@dataclass(frozen=True)
class TsOccurrence:
    name: str
    line: int
    form: Form
    receiver: str | None = None
    enclosing_class: str | None = None
    call_args: int | None = None
    call_has_spread: bool = False


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
