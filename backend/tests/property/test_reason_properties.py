from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from graveyard.models import Caller, Candidate, CommitInfo, Flag
from graveyard.verdict.reasons import TEMPLATES, render

NOW = datetime(2026, 1, 1, tzinfo=UTC)
TEXT = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=300) | st.just(
    "{a}\n}"
)
CALLERS = st.lists(
    st.builds(
        Caller,
        file_path=TEXT,
        line=st.integers(1, 10_000),
        kind=st.sampled_from(["test_reference", "string_match", "dynamic_import", "reexport"]),
        snippet=st.just("x"),
    ),
    max_size=3,
).map(tuple)
CANDIDATES = st.builds(
    Candidate,
    name=st.just("f"),
    qualified_name=st.just("f"),
    kind=st.just("function"),
    language=st.just("python"),
    file_path=st.just("a.py"),
    start_line=st.just(1),
    end_line=st.just(2),
    code_snippet=st.just(""),
    snippet_truncated=st.just(False),
    callers=CALLERS,
    flags=st.frozensets(st.sampled_from(list(Flag))),
    flag_details=st.dictionaries(st.sampled_from(list(Flag)), TEXT),
)
COMMITS = st.none() | st.builds(
    lambda days, boundary: CommitInfo("h", NOW - timedelta(days=days), "a", boundary),
    st.integers(0, 5000),
    st.booleans(),
)


@pytest.mark.property
@settings(max_examples=100)
@given(CANDIDATES, COMMITS, st.sampled_from(sorted(TEMPLATES)))
def test_p17_reasons_are_well_formed(c, commit, reason_id):
    """P17 (reasons are well-formed). For any candidate and commit, the reason is
    non-empty, one line, ends with ".", is at most 240 characters, has no unreplaced
    `{`, and says "at least" for boundary ages.

    **Validates: Requirements 3.2, 3.6.**
    """
    text = render(reason_id, c, commit, NOW)
    assert text
    assert len(text.splitlines()) == 1
    assert text.endswith(".")
    assert len(text) <= 240
    assert "{" not in text
    if commit is not None and commit.is_boundary and "{age}" in TEMPLATES[reason_id]:
        assert "at least" in text
