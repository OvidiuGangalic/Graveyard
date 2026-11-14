"""The verdict decision table: evidence in, confidence / verdict / reason ID out."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from graveyard import config
from graveyard.models import Candidate, CommitInfo, Confidence, Flag, Verdict


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
