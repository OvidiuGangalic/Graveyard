from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from graveyard import config
from graveyard.ingestion.samples import SampleError, materialise, sample_snapshot, split_regions

NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
REAL_SAMPLES = Path(__file__).resolve().parents[4] / "samples"


def git(root: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    out = subprocess.run(
        ["git", *args], cwd=root, env=env, capture_output=True, text=True, check=True
    )
    return out.stdout


def blame(root: Path, rel: str) -> dict[str, str]:
    """Map line content to the author of the commit that last touched it."""
    result: dict[str, str] = {}
    author = ""
    for line in git(root, "blame", "--line-porcelain", rel).splitlines():
        if line.startswith("author "):
            author = line[7:]
        elif line.startswith("\t"):
            result[line[1:]] = author
    return result


def make_sample(tmp_path: Path, files: dict[str, str], commits: list[dict] | None = None) -> Path:
    src = tmp_path / "src"
    for rel, text in files.items():
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text(text, encoding="utf-8")
    commits = commits or [
        {"days_ago": 400, "author": "Ann One", "message": "one", "files": ["a.py", "b.py"]},
        {"days_ago": 10, "author": "Bob Two", "message": "two", "files": ["a.py"]},
    ]
    (src / "history.json").write_text(json.dumps({"commits": commits}), encoding="utf-8")
    return src


A_PY = "old = 1\n# graveyard:commit 2\nnew = 2\n"


@pytest.mark.parametrize(
    "marker", ["# graveyard:commit 3", "// graveyard:commit 3", "    # graveyard:commit 3"]
)
def test_split_regions_switches_and_removes_markers(marker):
    text = f"a\n{marker}\nb\n"
    assert split_regions(text, 1) == [(1, "a"), (3, "b")]


def test_materialise_builds_scripted_history(tmp_path):
    src = make_sample(tmp_path, {"a.py": A_PY, "b.py": "x = 1\n"})
    dest = tmp_path / "out"
    materialise(src, dest, NOW)

    log = git(dest, "log", "--format=%an|%at").splitlines()
    assert log == [
        f"Bob Two|{int((NOW - timedelta(days=10)).timestamp())}",
        f"Ann One|{int((NOW - timedelta(days=400)).timestamp())}",
    ]
    assert blame(dest, "a.py") == {"old = 1": "Ann One", "new = 2": "Bob Two"}
    assert (dest / "a.py").read_text(encoding="utf-8") == "old = 1\nnew = 2\n"

    materialise(src, dest, NOW)
    assert (dest / "a.py").read_text(encoding="utf-8") == "old = 1\nnew = 2\n"
    assert len(git(dest, "log", "--format=%H").splitlines()) == 2


def test_unlisted_file_on_disk_is_an_error(tmp_path):
    src = make_sample(tmp_path, {"a.py": A_PY, "b.py": "x\n", "extra.py": "y\n"})
    with pytest.raises(SampleError, match="extra.py"):
        materialise(src, tmp_path / "out", NOW)


def test_history_listing_missing_file_is_an_error(tmp_path):
    src = make_sample(tmp_path, {"a.py": A_PY})
    with pytest.raises(SampleError, match="b.py"):
        materialise(src, tmp_path / "out", NOW)


def test_marker_for_commit_not_listing_file_is_an_error(tmp_path):
    src = make_sample(tmp_path, {"a.py": "x\n# graveyard:commit 2\ny\n", "b.py": "z\n"})
    (src / "history.json").write_text(
        json.dumps(
            {
                "commits": [
                    {"days_ago": 5, "author": "A", "message": "m", "files": ["a.py", "b.py"]},
                    {"days_ago": 1, "author": "A", "message": "n", "files": ["b.py"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SampleError, match="marker"):
        materialise(src, tmp_path / "out", NOW)


def test_real_haunted_sample(monkeypatch):
    monkeypatch.setenv("GRAVEYARD_SAMPLES_DIR", str(REAL_SAMPLES))
    snap = sample_snapshot("haunted")
    assert snap.is_sample
    assert snap.repo_url == "sample://haunted-repo"
    assert snap.warnings == (config.SAMPLE_WARNING,)
    assert len(git(snap.root, "log", "--format=%H").splitlines()) == 6
    assert {f.path for f in snap.source_files if f.is_test} == {
        "tests/test_pricing.py",
        "web/src/lib/api.test.ts",
    }
    lines = git(snap.root, "blame", "--line-porcelain", "inventory/pricing.py").splitlines()
    times: dict[str, int] = {}
    current = ""
    for line in lines:
        if line.startswith("author-time "):
            current = line.split()[1]
        elif line.startswith("\t"):
            times[line[1:]] = int(current)
    age = {k: (datetime.now(UTC).timestamp() - v) / 86400 for k, v in times.items()}
    assert round(age["def round_half_up_v2(value):"]) == 20
    assert round(age["def apply_discount(price, percent):"]) == 730
