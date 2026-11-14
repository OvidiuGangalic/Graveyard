"""The verdict decision table: evidence in, confidence / verdict / reason ID out."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from graveyard import config
from graveyard.git.archaeology import age_days
from graveyard.models import (
    CallerFound,
    Candidate,
    CommitInfo,
    Confidence,
    DeadItem,
    Flag,
    LastCommit,
    Verdict,
)
from graveyard.verdict.reasons import render

MAX_CALLERS = 20


@dataclass(frozen=True)
class Judgement:
    confidence: Confidence
    verdict: Verdict
    reason_id: str


# Rows 1-7 (low confidence), then the caution rows 8-12 including 10a, in table order.
_LOW_ROWS: tuple[tuple[Flag, Verdict, str], ...] = (
    (Flag.DYNAMIC_IMPORT, "revive", "RV_DYNAMIC_IMPORT"),
    (Flag.IN_DUNDER_ALL, "revive", "RV_DUNDER_ALL"),
    (Flag.LIBRARY_API, "revive", "RV_LIBRARY_API"),
    (Flag.STRING_MATCH, "revive", "RV_STRING_MATCH"),
    (Flag.UNKNOWN_DECORATOR, "unsure", "UN_DECORATOR"),
    (Flag.EXTERNAL_BASE_CLASS, "unsure", "UN_BASE_CLASS"),
    (Flag.SCRIPT_GLOBAL, "unsure", "UN_SCRIPT_GLOBAL"),
)
_ZOMBIE_ROWS: tuple[tuple[Flag, str], ...] = (
    (Flag.ZOMBIE_SKIPPED, "BM_ZOMBIE_SKIPPED"),
    (Flag.ZOMBIE_EMPTY, "BM_ZOMBIE_EMPTY"),
)
_CAUTION_ROWS_BEFORE_COVERAGE: tuple[tuple[Flag, str], ...] = (
    (Flag.EXPORTED, "BM_EXPORTED"),
    (Flag.DYNAMIC_PATTERN_IN_FILE, "BM_DYNAMIC_FILE"),
    (Flag.REPO_HAS_REFLECTION, "BM_REFLECTION"),
    (Flag.ARITY_MISMATCH, "BM_ARITY"),
    (Flag.SIDE_EFFECT_IMPORT, "BM_SIDE_EFFECT"),
    (Flag.CONDITIONAL_IMPORT, "BM_CONDITIONAL"),
)


def _age_days(commit: CommitInfo, created_at: datetime) -> int:
    """Whole days between the commit and ``created_at``, never negative."""
    try:
        return max(0, (created_at - commit.date).days)
    except TypeError:  # naive vs aware datetimes: treat as brand new, never raise
        return 0


def judge(c: Candidate, commit: CommitInfo | None, created_at: datetime) -> Judgement:
    for flag, verdict, reason_id in _LOW_ROWS:
        if flag in c.flags:
            return Judgement("low", verdict, reason_id)
    if c.kind == "test":
        for flag, reason_id in _ZOMBIE_ROWS:
            if flag in c.flags:
                return Judgement("medium", "bury", reason_id)
    for flag, reason_id in _CAUTION_ROWS_BEFORE_COVERAGE:
        if flag in c.flags:
            return Judgement("medium", "bury", reason_id)
    if c.test_coverage == "covered":
        return Judgement("medium", "bury", "BM_TEST_ONLY")
    if commit is None:
        return Judgement("medium", "bury", "BM_NO_HISTORY")
    if _age_days(commit, created_at) <= config.OLD_AGE_DAYS:
        if commit.is_boundary:
            return Judgement("medium", "bury", "BM_SHALLOW_HISTORY")
        return Judgement("medium", "bury", "BM_RECENT")
    if c.kind == "import":
        return Judgement("high", "bury", "BH_IMPORT")
    return Judgement("high", "bury", "BH_FUNCTION")


def _digest(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]  # noqa: S324 - not security


def _key(language: str, kind: str, file_path: str, qualified_name: str, start_line: int) -> str:
    return f"{language}:{kind}:{file_path}:{qualified_name}:{start_line}"


def item_id(c: Candidate) -> str:
    return _digest(_key(c.language, c.kind, c.file_path, c.qualified_name, c.start_line))


def assemble(
    c: Candidate, commit: CommitInfo | None, j: Judgement, created_at: datetime
) -> DeadItem:
    last_commit = (
        LastCommit(
            hash=commit.hash, date=commit.date, author=commit.author, is_boundary=commit.is_boundary
        )
        if commit
        else None
    )
    return DeadItem(
        id=item_id(c),
        name=c.qualified_name,
        kind=c.kind,
        language=c.language,
        file_path=c.file_path,
        start_line=c.start_line,
        end_line=c.end_line,
        last_commit=last_commit,
        age_days=age_days(commit.date, created_at) if commit else None,
        callers_found=[
            CallerFound(file_path=x.file_path, line=x.line, kind=x.kind, snippet=x.snippet)
            for x in c.callers[:MAX_CALLERS]
        ],
        test_coverage=c.test_coverage,
        confidence=j.confidence,
        verdict=j.verdict,
        verdict_reason=render(j.reason_id, c, commit, created_at),
        code_snippet=c.code_snippet,
        snippet_truncated=c.snippet_truncated,
        deletable_as_whole_lines=Flag.PARTIAL_STATEMENT not in c.flags,
    )


_VERDICT_RANK = {"bury": 0, "unsure": 1, "revive": 2}
_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}


def _dedupe(items: list[DeadItem]) -> list[DeadItem]:
    """Make ids unique by re-hashing with ``:2``, ``:3``, ... appended to the key."""
    ordered = sorted(items, key=lambda i: (i.file_path, i.start_line, i.name, i.kind, i.language))
    seen: set[str] = set()
    out: list[DeadItem] = []
    for item in ordered:
        new_id = item.id
        if new_id in seen:
            key = _key(item.language, item.kind, item.file_path, item.name, item.start_line)
            n = 2
            while new_id in seen:
                new_id = _digest(f"{key}:{n}")
                n += 1
            item = item.model_copy(update={"id": new_id})
        seen.add(new_id)
        out.append(item)
    return out


def finalise(items: list[DeadItem]) -> tuple[list[DeadItem], list[str]]:
    """Unique ids, Requirement 4.4 order, then the optional MAX_ITEMS cap."""
    out = sorted(
        _dedupe(items),
        key=lambda i: (
            _VERDICT_RANK[i.verdict],
            _CONFIDENCE_RANK[i.confidence],
            i.age_days is None,
            -(i.age_days or 0),
            i.file_path,
            i.start_line,
            i.name,
        ),
    )
    warnings: list[str] = []
    cap = config.MAX_ITEMS
    if cap is not None and len(out) > cap:
        warnings.append(f"Showing the first {cap} of {len(out)} items")
        out = out[:cap]
    return out, warnings
