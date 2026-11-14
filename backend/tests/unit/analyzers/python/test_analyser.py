from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from graveyard import cli
from graveyard.analyzers.python.analyser import analyse_python
from graveyard.ingestion import ingest_local
from graveyard.ingestion.samples import sample_snapshot
from graveyard.models import AnalysisTimeout, Flag, RepoSnapshot


def repo(tmp_path: Path, files: dict[str, str]) -> RepoSnapshot:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return ingest_local(tmp_path)


def names(snapshot: RepoSnapshot) -> list[str]:
    return [c.qualified_name for c in analyse_python(snapshot).candidates]


def test_uncalled_function_reported(tmp_path: Path) -> None:
    assert names(repo(tmp_path, {"a.py": "def dead():\n    return 1\n"})) == ["dead"]


def test_called_from_other_module_not_reported(tmp_path: Path) -> None:
    snap = repo(tmp_path, {"a.py": "def used():\n    return 1\n", "b.py": "import a\na.used()\n"})
    assert names(snap) == []


def test_recursive_only_call_still_reported(tmp_path: Path) -> None:
    assert names(repo(tmp_path, {"a.py": "def f(n):\n    return f(n - 1)\n"})) == ["f"]


def test_test_only_reference_is_covered(tmp_path: Path) -> None:
    snap = repo(tmp_path, {"a.py": "def f():\n    return 1\n", "tests/test_a.py": "f()  # call\n"})
    (cand,) = analyse_python(snap, resolve_all_unresolved=True).candidates
    assert cand.test_coverage == "covered"
    assert [(c.file_path, c.line, c.kind, c.snippet) for c in cand.callers] == [
        ("tests/test_a.py", 1, "test_reference", "f()  # call")
    ]


def test_not_covered_versus_unknown(tmp_path: Path) -> None:
    snap = repo(tmp_path, {"a.py": "def f():\n    return 1\n", "tests/test_a.py": "x = 1\n"})
    assert analyse_python(snap).candidates[0].test_coverage == "not_covered"
    alone = repo(tmp_path / "b", {"a.py": "def f():\n    return 1\n"})
    assert analyse_python(alone).candidates[0].test_coverage == "unknown"


def test_test_file_functions_never_reported(tmp_path: Path) -> None:
    snap = repo(tmp_path, {"tests/test_a.py": "def helper():\n    return 1\n"})
    result = analyse_python(snap)
    assert result.candidates == () and result.functions_defined == 0


def test_unparseable_file_tokens_keep_function_alive(tmp_path: Path) -> None:
    snap = repo(tmp_path, {"a.py": "def f():\n    return 1\n", "bad.py": "def (:\n f()\n"})
    result = analyse_python(snap)
    assert result.candidates == () and result.files_failed == 1


def test_deadline_passed_raises(tmp_path: Path) -> None:
    snap = repo(tmp_path, {"a.py": "x = 1\n"})
    with pytest.raises(AnalysisTimeout):
        analyse_python(snap, deadline=time.monotonic() - 1)


def test_order_independent_of_source_files_order(tmp_path: Path) -> None:
    snap = repo(
        tmp_path, {"a.py": "def a1():\n    return 1\n", "b.py": "def b1():\n    return 1\n"}
    )
    flipped = RepoSnapshot(**{**snap.__dict__, "source_files": snap.source_files[::-1]})
    assert analyse_python(snap) == analyse_python(flipped)


def test_snippet_equals_source_lines(tmp_path: Path) -> None:
    src = "def f(x):\n    return x\n"
    (cand,) = analyse_python(repo(tmp_path, {"a.py": src})).candidates
    assert (cand.code_snippet, cand.snippet_truncated) == (src.rstrip("\n"), False)


def test_cli_on_haunted_sample(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["analyse", "sample:haunted"]) == 0
    found = {c["name"] for c in json.loads(capsys.readouterr().out)["items"]}
    assert {"export_legacy_csv", "Stock.recount"} <= found
    assert "build_report" not in found


def test_same_name_in_two_modules_judged_separately(tmp_path: Path) -> None:  # P24
    d = "def apply(x):\n    return x\n"
    snap = repo(tmp_path, {"p1.py": d, "p2.py": d, "main.py": "from p1 import apply\napply(1)\n"})
    (cand,) = analyse_python(snap).candidates
    assert cand.file_path == "p2.py"


def test_resolution_only_adds_candidates(tmp_path: Path) -> None:  # P25
    snap = repo(
        tmp_path,
        {
            "a.py": "def f():\n    return 1\n\n\nclass C:\n    def m(self):\n        return 1\n",
            "b.py": "def f():\n    return 1\n\n\ndef g():\n    return 1\n",
            "main.py": "import a\nfrom b import g\na.f()\ng()\nf()\nx.m()\n",
        },
    )

    def keys(**kw: bool) -> set[tuple[str, str]]:
        return {(c.file_path, c.qualified_name) for c in analyse_python(snap, **kw).candidates}

    assert keys(resolve_all_unresolved=True) <= keys()


def test_haunted_sample_apply_discount_versions() -> None:
    found = {
        (c.file_path, c.qualified_name)
        for c in analyse_python(sample_snapshot("haunted")).candidates
    }
    assert ("inventory/pricing_v1.py", "apply_discount") in found
    assert ("inventory/pricing.py", "apply_discount") not in found


def test_haunted_sample_stock_adjust_arity_mismatch() -> None:
    cands = {c.qualified_name: c for c in analyse_python(sample_snapshot("haunted")).candidates}
    assert "Stock.adjust" not in cands
    v1 = cands["StockV1.adjust"]
    assert v1.flags == {Flag.ARITY_MISMATCH}
    assert v1.flag_details == {Flag.ARITY_MISMATCH: "inventory/cli.py:10"}


def test_exempt_entry_points_are_never_reported(tmp_path: Path) -> None:
    src = (
        "def main():\n    return 1\n\n\n@app.get('/x')\ndef route():\n    return 1\n\n\n"
        "class C:\n    def __repr__(self):\n        return 'c'\n\n\ndef dead():\n    return 1\n"
    )
    assert names(repo(tmp_path, {"a.py": src})) == ["dead"]


def test_weak_evidence_reaches_the_candidate(tmp_path: Path) -> None:
    files = {
        "a.py": "def hook():\n    return 1\n",
        "b.py": "ACTIONS = ['hook', 'other']\n",
        "conf.yaml": "handler: hook\n",
    }
    (cand,) = analyse_python(repo(tmp_path, files)).candidates
    assert cand.flag_details[Flag.STRING_MATCH] == "b.py:1"
    assert {(c.file_path, c.kind) for c in cand.callers} == {
        ("b.py", "string_match"),
        ("conf.yaml", "string_match"),
    }
