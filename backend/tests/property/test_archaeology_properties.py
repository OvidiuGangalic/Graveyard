from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from graveyard.git.archaeology import BlameCommit, age_days, newest_commit, parse_blame_porcelain

INSTANTS = st.datetimes(
    min_value=datetime(1990, 1, 1), max_value=datetime(2100, 1, 1), timezones=st.just(UTC)
)
HASHES = st.text("0123456789abcdef", min_size=40, max_size=40).filter(lambda h: set(h) != {"0"})
COMMITS = st.lists(
    st.builds(
        BlameCommit,
        HASHES,
        st.integers(0, 4_000_000_000),
        st.text("abc XYZ", min_size=1, max_size=8).filter(lambda s: s.strip() == s),
        st.booleans(),
    ),
    min_size=1,
    max_size=6,
    unique_by=lambda c: c.hash,
)


def render(commits: list[BlameCommit], order: list[int]) -> str:
    """Porcelain text: first line of a commit carries its fields, later lines the header."""
    out, seen = [], set()
    for n, i in enumerate(order, 1):
        c = commits[i % len(commits)]
        out.append(f"{c.hash} {n} {n} 1")
        if c.hash not in seen:
            seen.add(c.hash)
            out += [f"author {c.author}", "author-mail <a@b.c>", f"author-time {c.author_time}"]
            out += ["author-tz +0000", "summary s"] + (["boundary"] if c.boundary else [])
            out.append("filename f.py")
        out.append("\tcode")
    return "\n".join(out) + "\n"


@pytest.mark.property
@given(INSTANTS, INSTANTS, st.timedeltas(min_value=timedelta(0), max_value=timedelta(days=4000)))
def test_p9_age_is_sane(commit_date, created_at, extra):
    """P9 (age is sane). For any two UTC instants, `age_days(d, c) >= 0`; it equals
    `(c - d).days` when `c >= d`; and it never decreases as `c` advances.

    **Validates: Requirements 4.1, 4.2.**
    """
    age = age_days(commit_date, created_at)
    assert age >= 0
    if created_at >= commit_date:
        assert age == (created_at - commit_date).days
    try:
        later = created_at + extra
    except OverflowError:
        return
    assert age_days(commit_date, later) >= age


@pytest.mark.property
@given(COMMITS, st.lists(st.integers(0, 50), min_size=1, max_size=20))
def test_p15_parser_picks_newest(commits, order):
    """P15 (porcelain parser picks the newest). For any generated blame commits rendered
    in any interleaving, the selected commit has the maximum author-time, ties broken by
    smallest hash, and `boundary` matches the generated flag.

    **Validates: Requirements 1.1, 1.4, 2.1.**
    """
    order = list(dict.fromkeys(i % len(commits) for i in order))
    used = [commits[i] for i in order]
    best = newest_commit(parse_blame_porcelain(render(commits, order)))
    expected = min(used, key=lambda c: (-c.author_time, c.hash))
    assert best == expected


@pytest.mark.property
@given(st.text())
def test_p16_parser_never_raises(text):
    """P16 (parser never crashes). For any text, `parse_blame_porcelain` returns a list.

    **Validates: Requirement 3.5.**
    """
    assert isinstance(parse_blame_porcelain(text), list)
