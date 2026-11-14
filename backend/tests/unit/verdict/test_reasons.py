# ruff: noqa: E501  (snapshot sentences are one line each)
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from graveyard.models import Caller, Candidate, CommitInfo, Flag
from graveyard.verdict import reasons
from graveyard.verdict.reasons import TEMPLATES, render

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def commit(days: int = 400, boundary: bool = False) -> CommitInfo:
    return CommitInfo("abc", NOW - timedelta(days=days), "a", boundary)


CALLERS = (
    Caller("src/a.py", 3, "dynamic_import", "x"),
    Caller("src/b.py", 7, "reexport", "x"),
    Caller("src/c.py", 9, "string_match", "x"),
    Caller("tests/test_d.py", 11, "test_reference", "x"),
    Caller("tests/test_e.py", 12, "test_reference", "x"),
)
CAND = Candidate(
    name="recount",
    qualified_name="recount",
    kind="function",
    language="python",
    file_path="src/stock.py",
    start_line=1,
    end_line=2,
    code_snippet="def recount(): ...",
    snippet_truncated=False,
    callers=CALLERS,
    flag_details={f: f"detail-{f.value}" for f in Flag},
)

SNAPSHOT = {
    "RV_DYNAMIC_IMPORT": "Its file is loaded with a dynamic import at src/a.py:3, so it is probably used at runtime.",
    "RV_DUNDER_ALL": "It is listed in `__all__` at src/b.py:7, so it is part of the public API and may be used by code outside this repo.",
    "RV_LIBRARY_API": "It is exported from a published package (detail-library_api), and code outside this repo may import it, which this analysis cannot see.",
    "RV_STRING_MATCH": "Nothing calls it directly, but its name appears as a string at src/c.py:9, which suggests it is looked up by name at runtime.",
    "UN_DECORATOR": "Nothing calls it directly, but the decorator `detail-unknown_decorator` may register it with a framework, which static analysis cannot confirm.",
    "UN_BASE_CLASS": "Nothing calls it directly, but its class extends `detail-external_base_class` from outside this repo, which may call this method itself.",
    "UN_SCRIPT_GLOBAL": "Nothing calls it, but this file is a plain script whose functions are global and may be called from HTML or other scripts.",
    "BM_EXPORTED": "It is exported but nothing in this repo imports it, so it is safe to delete unless code outside this repo uses it.",
    "BM_DYNAMIC_FILE": "No references were found, but its file uses dynamic lookups (detail-dynamic_pattern_in_file), so a call at runtime cannot be ruled out.",
    "BM_REFLECTION": "No references were found, but this repo calls methods by computed name, so a call at runtime cannot be ruled out.",
    "BM_ARITY": "Other code calls something with this name at detail-arity_mismatch, but with arguments this definition cannot accept, so that call is taken to mean a different function.",
    "BM_SIDE_EFFECT": "It is never used in this file, but importing `detail-side_effect_import` may have side effects, so check before removing it.",
    "BM_CONDITIONAL": "It is never used in this file, but it is imported conditionally, which is often a deliberate availability check.",
    "BM_TEST_ONLY": "Only tests reference it (2 place(s), first at tests/test_d.py:11), so delete it together with those tests.",
    "BM_NO_HISTORY": "No references were found, but its age is unknown because git history was unavailable.",
    "BM_SHALLOW_HISTORY": "No references were found, but the available git history only shows it is 400 days old.",
    "BM_RECENT": "No references were found, but it was touched 400 days ago, so it may be work in progress.",
    "BH_FUNCTION": "No references anywhere in this repo, no test mentions it, it has been untouched for 400 days, and its file has no dynamic lookups.",
    "BH_IMPORT": "It is never used in this file, it has been untouched for 400 days, and the file has no dynamic lookups.",
    "BM_ZOMBIE_SKIPPED": "This test is permanently skipped, so it never runs and guards nothing.",
    "BM_ZOMBIE_EMPTY": "This test has no assertions, so it passes without checking anything.",
}


def test_snapshot_covers_every_template():
    assert set(SNAPSHOT) == set(TEMPLATES)


@pytest.mark.parametrize("reason_id", sorted(SNAPSHOT))
def test_render_matches_snapshot(reason_id):
    assert render(reason_id, CAND, commit(), NOW) == SNAPSHOT[reason_id]


def test_missing_caller_falls_back_to_this_repo():
    c = replace(CAND, callers=())
    assert "dynamic import in this repo," in render("RV_DYNAMIC_IMPORT", c, None, NOW)
    assert "as a string in this repo," in render("RV_STRING_MATCH", c, None, NOW)
    assert "(0 place(s), first in this repo)" in render("BM_TEST_ONLY", c, None, NOW)
    assert "at {" not in render("BM_ARITY", c, None, NOW)
    bare = replace(c, flag_details={})
    assert "name in this repo, but" in render("BM_ARITY", bare, None, NOW)


def test_boundary_commit_says_at_least():
    text = render("BM_SHALLOW_HISTORY", CAND, commit(30, boundary=True), NOW)
    assert "at least 30 days old" in text


def test_age_floors_and_clamps_at_zero():
    future = CommitInfo("a", NOW + timedelta(days=3), "a")
    assert "touched 0 days ago" in render("BM_RECENT", CAND, future, NOW)


def test_detail_truncated_to_60_and_single_line():
    c = replace(CAND, flag_details={Flag.UNKNOWN_DECORATOR: "x" * 100 + "\n{y}"})
    text = render("UN_DECORATOR", c, None, NOW)
    assert "`" + "x" * 60 + "`" in text
    assert "\n" not in text
    assert "{" not in text


def test_unknown_reason_id(monkeypatch, caplog):
    monkeypatch.setattr(reasons, "STRICT", True)
    with pytest.raises(KeyError):
        render("NOPE", CAND, None, NOW)
    monkeypatch.setattr(reasons, "STRICT", False)
    assert render("NOPE", CAND, None, NOW) == "No references were found."
    assert "NOPE" in caplog.text
