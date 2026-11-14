from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from graveyard import config
from graveyard.git.archaeology import _clean_author, age_days, dig, parse_blame_porcelain
from graveyard.ingestion.samples import sample_snapshot
from graveyard.models import Candidate, RepoSnapshot

NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
D1, D2, D3 = (NOW - timedelta(days=n) for n in (400, 200, 10))


def _git(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    base = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    base.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, **(env or {}))
    out = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        env=base,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return out.stdout


def make_repo(tmp_path: Path, commits: list[tuple[datetime, str, dict[str, str]]]) -> list[str]:
    """Build a repo in tmp_path/repo. Each commit is (author date, author, {path: text})."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init", "-q", "-b", "main"], root)
    hashes = []
    for i, (when, author, files) in enumerate(commits):
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
            _git(["add", "--", rel], root)
        stamp = when.isoformat()
        identity = ["-c", f"user.name={author}", "-c", "user.email=who@graveyard.invalid"]
        _git(
            [*identity, "commit", "-q", "--no-verify", "-m", f"c{i}"],
            root,
            env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
        )
        hashes.append(_git(["rev-parse", "HEAD"], root).strip())
    return hashes


def snap(root: Path, has_git: bool = True, depth: int | None = None) -> RepoSnapshot:
    return RepoSnapshot(root, "", "t", "main", "", False, has_git, depth, (), (), 0)


def cand(path: str, start: int, end: int, name: str = "f") -> Candidate:
    return Candidate(name, name, "function", "python", path, start, end, "", False)


def key(c: Candidate):
    return (c.language, c.file_path, c.start_line, c.qualified_name)


def test_newest_commit_in_range_and_untouched_neighbour(tmp_path):
    h = make_repo(
        tmp_path,
        [(D1, "Ann", {"a.py": "one\ntwo\nthree\n"}), (D2, "Bob", {"a.py": "one\nTWO\nthree\n"})],
    )
    wide, old = cand("a.py", 1, 3, "wide"), cand("a.py", 1, 1, "old")
    result = dig(snap(tmp_path / "repo"), [wide, old], NOW)
    assert result.commits[key(wide)].hash == h[1]
    assert result.commits[key(wide)].author == "Bob"
    assert result.commits[key(wide)].date == D2
    assert result.commits[key(old)].hash == h[0]
    assert result.warnings == ()


def test_tie_on_author_time_picks_smallest_hash(tmp_path):
    h = make_repo(
        tmp_path,
        [
            (D1, "Ann", {"a.py": "one\ntwo\n"}),
            (D2, "Bob", {"a.py": "ONE\ntwo\n"}),
            (D2, "Cy", {"a.py": "ONE\nTWO\n"}),
        ],
    )
    c = cand("a.py", 1, 2)
    assert dig(snap(tmp_path / "repo"), [c], NOW).commits[key(c)].hash == min(h[1], h[2])


@pytest.fixture
def shallow_clone(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    make_repo(
        src,
        [
            (D1, "Ann", {"a.py": "one\ntwo\n"}),
            (D2, "Bob", {"a.py": "one\nTWO\n", "b.py": "x\n"}),
            (D3, "Cy", {"b.py": "y\n"}),
        ],
    )
    dest = tmp_path / "clone"
    _git(["clone", "-q", "--depth", "2", (src / "repo").as_uri(), str(dest)], tmp_path)
    return dest


def test_boundary_via_blame_porcelain(shallow_clone):
    c = cand("a.py", 1, 1)
    result = dig(snap(shallow_clone, depth=2), [c], NOW)
    assert result.commits[key(c)].is_boundary is True
    assert result.warnings == (
        "Git history limited to the last 2 commits; ages shown as 'at least' are lower bounds",
    )


def test_boundary_via_shallow_file_on_fallback(shallow_clone, monkeypatch):
    monkeypatch.setattr(config, "MAX_BLAME_ITEMS", 0)
    c = cand("a.py", 1, 1)
    info = dig(snap(shallow_clone), [c], NOW).commits[key(c)]
    assert info is not None and info.is_boundary is True


def test_cap_uses_per_file_date_and_warns(tmp_path, monkeypatch):
    h = make_repo(
        tmp_path, [(D1, "Ann", {"a.py": "one\ntwo\n"}), (D2, "Bob", {"a.py": "one\nTWO\n"})]
    )
    new, old = cand("a.py", 2, 2, "new"), cand("a.py", 1, 1, "old")
    assert dig(snap(tmp_path / "repo"), [new, old], NOW).commits[key(old)].hash == h[0]
    monkeypatch.setattr(config, "MAX_BLAME_ITEMS", 1)
    result = dig(snap(tmp_path / "repo"), [new, old], NOW)
    assert result.commits[key(new)].hash == h[1]
    assert result.commits[key(old)].hash == h[1]
    assert result.warnings == ("Ages for some items are per file, not per line range",)


def test_blame_failure_falls_back_to_file_log(tmp_path):
    h = make_repo(tmp_path, [(D1, "Ann", {"a.py": "one\n"})])
    (tmp_path / "repo" / "a.py").unlink()
    c = cand("a.py", 1, 1)
    assert dig(snap(tmp_path / "repo"), [c], NOW).commits[key(c)].hash == h[0]


def test_unknown_file_and_bad_range_give_none_without_raising(tmp_path):
    make_repo(tmp_path, [(D1, "Ann", {"a.py": "one\n"})])
    cands = [cand("missing.py", 1, 1, "m"), cand("a.py", 50, 60, "r")]
    result = dig(snap(tmp_path / "repo"), cands, NOW)
    assert result.commits[key(cands[0])] is None
    assert result.commits[key(cands[1])] is not None  # per-file fallback


def test_no_git_snapshot(tmp_path):
    c = cand("a.py", 1, 1)
    result = dig(snap(tmp_path, has_git=False), [c], NOW)
    assert result.commits == {key(c): None}
    assert result.warnings == ("No git history available, so ages are unknown",)


def test_zero_budget_stops_git(tmp_path, monkeypatch):
    make_repo(tmp_path, [(D1, "Ann", {"a.py": "one\n"})])
    monkeypatch.setattr(config, "ARCHAEOLOGY_BUDGET_S", 0)
    c = cand("a.py", 1, 1)
    result = dig(snap(tmp_path / "repo"), [c], NOW)
    assert result.commits == {key(c): None}
    assert result.warnings == ("Git history lookup ran out of time for some items",)


def test_unicode_and_spaced_paths(tmp_path):
    h = make_repo(tmp_path, [(D1, "Zoë", {"my dir/café.py": "one\n"})])
    c = cand("my dir/café.py", 1, 1)
    info = dig(snap(tmp_path / "repo"), [c], NOW).commits[key(c)]
    assert (info.hash, info.author) == (h[0], "Zoë")


def test_empty_author_is_unknown():
    assert _clean_author("") == _clean_author("  ") == "Unknown"  # git itself refuses empty names


def test_long_author_is_truncated(tmp_path):
    author, expected = "x" * 150, "x" * 100
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init", "-q", "-b", "main"], root)
    (root / "a.py").write_text("one\n", encoding="utf-8")
    _git(["add", "--", "a.py"], root)
    _git(
        ["commit", "-q", "--no-verify", "--allow-empty-message", "-m", "c"],
        root,
        env={
            "GIT_AUTHOR_NAME": author,
            "GIT_AUTHOR_EMAIL": "who@graveyard.invalid",
            "GIT_COMMITTER_NAME": "Cy",
            "GIT_COMMITTER_EMAIL": "cy@graveyard.invalid",
        },
    )
    c = cand("a.py", 1, 1)
    assert dig(snap(root), [c], NOW).commits[key(c)].author == expected


def test_uncommitted_lines_are_ignored():
    zero = "0" * 40
    text = f"{zero} 1 1 1\nauthor Not Committed Yet\nauthor-time 9999999999\n\tx\n"
    assert [c.hash for c in parse_blame_porcelain(text)] == [zero]
    assert parse_blame_porcelain("garbage\nauthor-time x\n") == []


def test_age_days_floor_and_clamp():
    assert age_days(NOW - timedelta(days=3, hours=23), NOW) == 3
    assert age_days(NOW + timedelta(days=2), NOW) == 0
    assert age_days(NOW, NOW) == 0


def test_haunted_sample_ages(tmp_path):
    snapshot, now = sample_snapshot("haunted", tmp_path), datetime.now(UTC)
    wanted = {"round_half_up_v2": 20, "export_legacy_csv": 730}
    cands = [
        cand("inventory/pricing.py", 1, 400, "round_half_up_v2"),
        cand("inventory/reports.py", 1, 400, "export_legacy_csv"),
    ]
    for c, name in zip(cands, wanted, strict=True):
        text = (snapshot.root / c.file_path).read_text(encoding="utf-8").splitlines()
        start = next(i for i, line in enumerate(text, 1) if f"def {name}" in line)
        cands[cands.index(c)] = cand(c.file_path, start, start, name)
    result = dig(snapshot, cands, now)
    for c in cands:
        info = result.commits[key(c)]
        assert abs(age_days(info.date, now) - wanted[c.name]) <= 1
