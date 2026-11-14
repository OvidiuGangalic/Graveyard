import re
from datetime import UTC, datetime, timedelta

from graveyard import config
from graveyard.models import Caller, Candidate, CommitInfo, Flag
from graveyard.verdict import engine
from graveyard.verdict.engine import Judgement, assemble, finalise, item_id

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
J = Judgement("high", "bury", "BH_FUNCTION")


def cand(**kw) -> Candidate:
    base = dict(
        name="f",
        qualified_name="S.f",
        kind="function",
        language="python",
        file_path="a.py",
        start_line=3,
        end_line=5,
        code_snippet="def f(): pass",
        snippet_truncated=False,
    )
    return Candidate(**{**base, **kw})


def commit(days=400, boundary=False) -> CommitInfo:
    return CommitInfo("b" * 40, NOW - timedelta(days=days), "dev", boundary)


def test_assemble_with_commit():
    c = cand(
        callers=(Caller("t.py", 9, "test_reference", "f()"),),
        test_coverage="covered",
        snippet_truncated=True,
    )
    item = assemble(c, commit(), Judgement("medium", "bury", "BM_TEST_ONLY"), NOW)
    assert item.id == item_id(c)
    assert (item.name, item.kind, item.language) == ("S.f", "function", "python")
    assert (item.file_path, item.start_line, item.end_line) == ("a.py", 3, 5)
    assert item.last_commit is not None
    assert item.last_commit.hash == "b" * 40
    assert item.last_commit.author == "dev"
    assert item.age_days == 400
    assert [x.file_path for x in item.callers_found] == ["t.py"]
    assert item.test_coverage == "covered"
    assert (item.confidence, item.verdict) == ("medium", "bury")
    assert "t.py:9" in item.verdict_reason
    assert item.code_snippet == "def f(): pass"
    assert item.snippet_truncated is True
    assert item.deletable_as_whole_lines is True


def test_assemble_boundary_commit():
    j = Judgement("medium", "bury", "BM_SHALLOW_HISTORY")
    item = assemble(cand(), commit(10, boundary=True), j, NOW)
    assert item.last_commit is not None and item.last_commit.is_boundary
    assert item.age_days == 10


def test_assemble_no_commit():
    item = assemble(cand(), None, Judgement("medium", "bury", "BM_NO_HISTORY"), NOW)
    assert item.last_commit is None
    assert item.age_days is None


def test_partial_statement_not_deletable():
    item = assemble(cand(flags=frozenset({Flag.PARTIAL_STATEMENT})), commit(), J, NOW)
    assert item.deletable_as_whole_lines is False


def test_callers_capped_at_20():
    callers = tuple(Caller("t.py", i + 1, "string_match", "x") for i in range(30))
    assert len(assemble(cand(callers=callers), commit(), J, NOW).callers_found) == 20


def test_id_is_12_hex_and_stable():
    a, b = item_id(cand()), item_id(cand())
    assert a == b
    assert re.fullmatch(r"[0-9a-f]{12}", a)
    assert a != item_id(cand(start_line=4))


def mk(name="f", file="a.py", line=1, verdict="bury", conf="high", age=None):
    c = cand(qualified_name=name, file_path=file, start_line=line, end_line=line)
    return assemble(
        c, None if age is None else commit(age), Judgement(conf, verdict, "BH_FUNCTION"), NOW
    )


def test_collision_rehashes_with_suffix():
    items, warnings = finalise([mk(), mk()])
    ids = [i.id for i in items]
    assert len(set(ids)) == 2
    assert all(re.fullmatch(r"[0-9a-f]{12}", i) for i in ids)
    key = engine._key("python", "function", "a.py", "f", 1)
    assert engine._digest(key + ":2") in ids
    assert warnings == []


def test_collision_forced_by_constant_hash(monkeypatch):
    real = engine._digest
    # Base keys have 4 colons; suffixed keys have 5. Only the base hash collides.
    monkeypatch.setattr(engine, "_digest", lambda k: "0" * 12 if k.count(":") == 4 else real(k))
    out, _ = finalise([mk(name="a"), mk(name="b"), mk(name="c")])
    assert len({i.id for i in out}) == 3


def test_sort_order():
    items = [
        mk("revive_low", verdict="revive", conf="low", age=900),
        mk("unsure", verdict="unsure", conf="low", age=900),
        mk("bury_med", conf="medium", age=900),
        mk("bury_high_young", age=10),
        mk("bury_high_old_b", age=500, file="b.py"),
        mk("bury_high_old_a_l9", age=500, line=9),
        mk("bury_high_old_a_l2_y", age=500, line=2),
        mk("bury_high_old_a_l2_x", age=500, line=2),
        mk("bury_high_none"),
    ]
    out, _ = finalise(list(reversed(items)))
    assert [i.name for i in out] == [
        "bury_high_old_a_l2_x",
        "bury_high_old_a_l2_y",
        "bury_high_old_a_l9",
        "bury_high_old_b",
        "bury_high_young",
        "bury_high_none",
        "bury_med",
        "unsure",
        "revive_low",
    ]


def test_max_items_unset_keeps_all(monkeypatch):
    monkeypatch.setattr(config, "MAX_ITEMS", None)
    out, warnings = finalise([mk(line=n) for n in range(1, 6)])
    assert len(out) == 5 and warnings == []


def test_max_items_cuts_and_warns(monkeypatch):
    monkeypatch.setattr(config, "MAX_ITEMS", 2)
    out, warnings = finalise([mk(line=n) for n in range(1, 6)])
    assert [i.start_line for i in out] == [1, 2]
    assert warnings == ["Showing the first 2 of 5 items"]
