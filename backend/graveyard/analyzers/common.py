"""Helpers shared by the Python and TypeScript analysers."""

from __future__ import annotations

import re
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

from graveyard import config
from graveyard.ingestion.walker import read_text
from graveyard.models import AnalysisTimeout, Caller


def check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() > deadline:
        raise AnalysisTimeout


def clip(text: str, limit: int = 200) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def snippet_for(lines: Sequence[str], start: int, end: int) -> tuple[str, bool]:
    """Source lines ``start..end`` (1-based, inclusive) and whether they were cut."""
    chosen = lines[start - 1 : end]
    truncated = len(chosen) > config.SNIPPET_MAX_LINES
    return "\n".join(chosen[: config.SNIPPET_MAX_LINES]), truncated


def cap_callers(callers: Iterable[Caller]) -> tuple[Caller, ...]:
    unique = sorted(set(callers), key=lambda c: (c.file_path, c.line, c.kind))
    return tuple(unique[: config.MAX_CALLERS])


PY_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
TS_TOKEN = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")


def whole_token(name: str) -> re.Pattern[str]:
    """Regex matching ``name`` only as a whole identifier token."""
    return re.compile(rf"(?<![A-Za-z0-9_$]){re.escape(name)}(?![A-Za-z0-9_$])")


class TextIndex:
    """Identifier token -> first ``MAX_CALLERS`` (file, line, clipped line) in text files."""

    def __init__(
        self, root: Path, text_files: Iterable[str], token: re.Pattern[str] = PY_TOKEN
    ) -> None:
        self._hits: dict[str, list[tuple[str, int, str]]] = {}
        for rel in sorted(text_files):
            for number, line in enumerate(read_text(root, rel).splitlines(), start=1):
                for name in set(token.findall(line)):
                    hits = self._hits.setdefault(name, [])
                    if len(hits) < config.MAX_CALLERS:
                        hits.append((rel, number, clip(line)))

    def lookup(self, name: str) -> list[tuple[str, int, str]]:
        return self._hits.get(name, [])
