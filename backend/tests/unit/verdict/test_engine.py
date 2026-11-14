from datetime import UTC, datetime, timedelta

import pytest

from graveyard import config
from graveyard.models import Candidate, CommitInfo, Flag
from graveyard.verdict.engine import Judgement, judge

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def commit_aged(days: int, boundary: bool = False) -> CommitInfo:
    return CommitInfo("a" * 40, NOW - timedelta(days=days), "dev", boundary)


OLD = commit_aged(config.OLD_AGE_DAYS + 1)
RECENT = commit_aged(10)
SHALLOW = commit_aged(10, boundary=True)

# (row, flags, coverage, commit, kind, (confidence, verdict, reason_id))
ROWS = [
    (
        "1",
        {Flag.DYNAMIC_IMPORT},
        "unknown",
        OLD,
        "function",
        ("low", "revive", "RV_DYNAMIC_IMPORT"),
    ),
    ("2", {Flag.IN_DUNDER_ALL}, "unknown", OLD, "function", ("low", "revive", "RV_DUNDER_ALL")),
    ("3", {Flag.LIBRARY_API}, "unknown", OLD, "function", ("low", "revive", "RV_LIBRARY_API")),
    ("4", {Flag.STRING_MATCH}, "unknown", OLD, "function", ("low", "revive", "RV_STRING_MATCH")),
    ("5", {Flag.UNKNOWN_DECORATOR}, "unknown", OLD, "function", ("low", "unsure", "UN_DECORATOR")),
    (
        "6",
        {Flag.EXTERNAL_BASE_CLASS},
        "unknown",
        OLD,
        "function",
        ("low", "unsure", "UN_BASE_CLASS"),
    ),
    ("7", {Flag.SCRIPT_GLOBAL}, "unknown", OLD, "function", ("low", "unsure", "UN_SCRIPT_GLOBAL")),
    ("8", {Flag.EXPORTED}, "unknown", OLD, "function", ("medium", "bury", "BM_EXPORTED")),
    (
        "9",
        {Flag.DYNAMIC_PATTERN_IN_FILE},
        "unknown",
        OLD,
        "function",
        ("medium", "bury", "BM_DYNAMIC_FILE"),
    ),
    (
        "10",
        {Flag.REPO_HAS_REFLECTION},
        "unknown",
        OLD,
        "function",
        ("medium", "bury", "BM_REFLECTION"),
    ),
    ("10a", {Flag.ARITY_MISMATCH}, "unknown", OLD, "function", ("medium", "bury", "BM_ARITY")),
    (
        "11",
        {Flag.SIDE_EFFECT_IMPORT},
        "unknown",
        OLD,
        "import",
        ("medium", "bury", "BM_SIDE_EFFECT"),
    ),
    (
        "12",
        {Flag.CONDITIONAL_IMPORT},
        "unknown",
        OLD,
        "import",
        ("medium", "bury", "BM_CONDITIONAL"),
    ),
    ("13", set(), "covered", OLD, "function", ("medium", "bury", "BM_TEST_ONLY")),
    ("14", set(), "unknown", None, "function", ("medium", "bury", "BM_NO_HISTORY")),
    ("15", set(), "unknown", SHALLOW, "function", ("medium", "bury", "BM_SHALLOW_HISTORY")),
    ("16", set(), "unknown", RECENT, "function", ("medium", "bury", "BM_RECENT")),
    ("17", set(), "not_covered", OLD, "function", ("high", "bury", "BH_FUNCTION")),
    ("18", set(), "not_covered", OLD, "import", ("high", "bury", "BH_IMPORT")),
]
BY_ROW = {r[0]: r for r in ROWS}


def cand(flags=(), coverage="unknown", kind="function") -> Candidate:
    return Candidate(
        name="f",
        qualified_name="f",
        kind=kind,
        language="python",
        file_path="a.py",
        start_line=1,
        end_line=2,
        code_snippet="def f(): pass",
        snippet_truncated=False,
        test_coverage=coverage,
        flags=frozenset(flags),
    )


@pytest.mark.parametrize(("row", "flags", "cov", "commit", "kind", "expected"), ROWS)
def test_each_row(row, flags, cov, commit, kind, expected):
    assert judge(cand(flags, cov, kind), commit, NOW) == Judgement(*expected)


# Rows 14/15 (no commit vs a commit), 16/17 (recent vs old) and 17/18 (kind) cannot both hold,
# so those pairs are covered by the dedicated tests below.
_PAIRED = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "10a", "11", "12", "13"]
_ORDER = [r[0] for r in ROWS]


@pytest.mark.parametrize("upper", _PAIRED)
def test_earlier_row_wins_when_next_row_also_true(upper):
    lower = _ORDER[_ORDER.index(upper) + 1]
    u, lo = BY_ROW[upper], BY_ROW[lower]
    flags = u[1] | lo[1]
    coverage = "covered" if "covered" in (u[2], lo[2]) else "unknown"
    commit = None if lower == "14" else u[3]
    assert judge(cand(flags, coverage, u[4]), commit, NOW) == Judgement(*u[5])


def test_recent_import_is_row_16_not_row_18():
    assert judge(cand(kind="import"), RECENT, NOW).reason_id == "BM_RECENT"


def test_row_17_and_18_differ_only_by_kind():
    assert judge(cand(kind="function"), OLD, NOW).reason_id == "BH_FUNCTION"
    assert judge(cand(kind="import"), OLD, NOW).reason_id == "BH_IMPORT"


def test_all_flags_and_coverage_row_1_wins():
    assert judge(cand(set(Flag), "covered"), None, NOW) == Judgement(
        "low", "revive", "RV_DYNAMIC_IMPORT"
    )


def test_age_180_is_recent_181_is_high():
    assert judge(cand(), commit_aged(180), NOW).reason_id == "BM_RECENT"
    assert judge(cand(), commit_aged(181), NOW).reason_id == "BH_FUNCTION"
    assert judge(cand(), commit_aged(180, boundary=True), NOW).reason_id == "BM_SHALLOW_HISTORY"
    assert judge(cand(), commit_aged(181, boundary=True), NOW).reason_id == "BH_FUNCTION"


def test_age_is_floored_to_whole_days():
    almost_181 = CommitInfo("a" * 40, NOW - timedelta(days=181) + timedelta(hours=1), "d")
    assert judge(cand(), almost_181, NOW).reason_id == "BM_RECENT"


def test_future_commit_clamps_to_zero_age():
    future = CommitInfo("a" * 40, NOW + timedelta(days=3), "d")
    assert judge(cand(), future, NOW).reason_id == "BM_RECENT"


@pytest.mark.parametrize(
    ("flag", "reason_id"),
    [(Flag.ZOMBIE_SKIPPED, "BM_ZOMBIE_SKIPPED"), (Flag.ZOMBIE_EMPTY, "BM_ZOMBIE_EMPTY")],
)
def test_zombie_rows_for_test_kind(flag, reason_id):
    assert judge(cand({flag}, kind="test"), OLD, NOW) == Judgement("medium", "bury", reason_id)


def test_zombie_precedes_row_8_but_not_row_7():
    both = {Flag.ZOMBIE_SKIPPED, Flag.EXPORTED}
    assert judge(cand(both, kind="test"), OLD, NOW).reason_id == "BM_ZOMBIE_SKIPPED"
    blind = {Flag.ZOMBIE_SKIPPED, Flag.SCRIPT_GLOBAL}
    assert judge(cand(blind, kind="test"), OLD, NOW).reason_id == "UN_SCRIPT_GLOBAL"


def test_zombie_flags_ignored_for_non_test_kind():
    assert judge(cand({Flag.ZOMBIE_SKIPPED}), OLD, NOW).reason_id == "BH_FUNCTION"
