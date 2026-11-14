"""Helpers shared by the Python and TypeScript analysers."""

from __future__ import annotations

import time
from collections.abc import Iterable, Sequence

from graveyard import config
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
