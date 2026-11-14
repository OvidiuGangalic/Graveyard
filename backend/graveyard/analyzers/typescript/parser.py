"""Parse TypeScript, TSX and JavaScript with tree-sitter and walk the tree iteratively."""

from __future__ import annotations

import posixpath
from collections.abc import Iterator
from functools import cache

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser, Tree

_TS = {".ts"}
_TSX = {".tsx"}


@cache
def _language(kind: str) -> Language:
    if kind == "tsx":
        return Language(tree_sitter_typescript.language_tsx())
    if kind == "ts":
        return Language(tree_sitter_typescript.language_typescript())
    return Language(tree_sitter_javascript.language())


@cache
def _parser(kind: str) -> Parser:
    return Parser(_language(kind))


def grammar_for(path: str) -> str:
    """Grammar name for a path: `ts`, `tsx`, or `js` for .js/.jsx/.mjs/.cjs and anything else."""
    ext = posixpath.splitext(path)[1].lower()
    if ext in _TS:
        return "ts"
    if ext in _TSX:
        return "tsx"
    return "js"


def parse(path: str, data: bytes) -> Tree | None:
    """Parse source bytes with the grammar for `path`; None only if the parser raises."""
    try:
        return _parser(grammar_for(path)).parse(data)
    except Exception:
        return None


def has_error(tree: Tree) -> bool:
    """True when the tree contains any ERROR or MISSING node."""
    return tree.root_node.has_error


def walk(node: Node) -> Iterator[Node]:
    """Pre-order traversal of `node` and its descendants, using a cursor (no recursion)."""
    cursor = node.walk()
    while True:
        yield cursor.node
        if cursor.goto_first_child():
            continue
        while not cursor.goto_next_sibling():
            if not cursor.goto_parent() or cursor.node == node:
                return


def text(node: Node) -> str:
    return (node.text or b"").decode("utf-8", errors="replace")


def line(node: Node) -> int:
    return node.start_point[0] + 1


def end_line(node: Node) -> int:
    return node.end_point[0] + 1
