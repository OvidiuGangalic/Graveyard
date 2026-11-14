from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from graveyard import config
from graveyard.models import (
    BLIND_FLAGS,
    CAUTION_FLAGS,
    REVIVE_FLAGS,
    Caller,
    Candidate,
    CommitInfo,
    Flag,
)
from graveyard.verdict.engine import judge

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
RANK = {"low": 0, "medium": 1, "high": 2}
REAL_FLAGS = [f for f in Flag if f not in (Flag.ZOMBIE_SKIPPED, Flag.ZOMBIE_EMPTY)]

CALLER = Caller("t.py", 1, "string_match", "x")


@st.composite
def candidate(draw):
    return Candidate(
        name="f",
        qualified_name="f",
        kind=draw(st.sampled_from(["function", "import"])),
        language="python",
        file_path="a.py",
        start_line=1,
        end_line=2,
        code_snippet="",
        snippet_truncated=False,
        callers=(CALLER,) * draw(st.integers(0, 3)),
        test_coverage=draw(st.sampled_from(["covered", "not_covered", "unknown"])),
        flags=frozenset(draw(st.sets(st.sampled_from(REAL_FLAGS)))),
    )


@st.composite
def commit(draw):
    if draw(st.booleans()):
        return None
    days = draw(st.integers(0, 5000))
    return CommitInfo("a" * 40, NOW - timedelta(days=days), "dev", draw(st.booleans()))


def _age(c: CommitInfo) -> int:
    return (NOW - c.date).days


@pytest.mark.property
@given(candidate(), commit())
def test_p7_high_is_safe(c, ci):
    """P7 (high is safe). For any generated candidate and commit: confidence `high` implies
    no Revive, Blind or Caution flag, coverage is not `covered`, a commit is present and
    age is over 180 days.

    **Validates: Requirements 1.3, 1.4.**
    """
    if judge(c, ci, NOW).confidence == "high":
        assert not c.flags & (REVIVE_FLAGS | BLIND_FLAGS | CAUTION_FLAGS)
        assert c.test_coverage != "covered"
        assert ci is not None
        assert _age(ci) > config.OLD_AGE_DAYS


@pytest.mark.property
@given(candidate(), commit())
def test_p7b_verdict_and_confidence_agree(c, ci):
    """P7b (verdict and confidence agree). `bury` holds exactly when confidence is medium or
    high; `revive` and `unsure` hold exactly when confidence is low.

    **Validates: Requirement 2.4.**
    """
    j = judge(c, ci, NOW)
    assert (j.verdict == "bury") == (j.confidence in ("medium", "high"))
    assert (j.verdict in ("revive", "unsure")) == (j.confidence == "low")


@pytest.mark.property
@given(candidate(), commit(), st.sampled_from(REAL_FLAGS), st.integers(1, 5000))
def test_p8_evidence_only_lowers_confidence(c, ci, extra, fewer_days):
    """P8 (evidence only lowers confidence). Adding a flag, changing coverage to `covered`,
    or reducing age never raises confidence.

    **Validates: Requirements 1.1, 1.2.**
    """
    base = RANK[judge(c, ci, NOW).confidence]
    with_flag = Candidate(**{**c.__dict__, "flags": c.flags | {extra}})
    assert RANK[judge(with_flag, ci, NOW).confidence] <= base
    covered = Candidate(**{**c.__dict__, "test_coverage": "covered"})
    assert RANK[judge(covered, ci, NOW).confidence] <= base
    if ci is not None:
        younger = CommitInfo(
            ci.hash, ci.date + timedelta(days=fewer_days), ci.author, ci.is_boundary
        )
        assert RANK[judge(c, younger, NOW).confidence] <= base
