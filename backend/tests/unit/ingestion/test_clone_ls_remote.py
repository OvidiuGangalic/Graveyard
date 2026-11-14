import os
import subprocess
from pathlib import Path

import pytest

from graveyard.ingestion import clone
from graveyard.models import IngestError, RepoRef

REF = RepoRef("o", "r")


def git(cwd: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def make_remote(tmp_path: Path, branch: str = "main", commit: bool = True) -> tuple[Path, str]:
    bare = tmp_path / "remote.git"
    bare.mkdir()
    git(bare, "init", "--bare", "-b", branch)
    sha = ""
    if commit:
        work = tmp_path / "work"
        work.mkdir()
        git(work, "init", "-b", branch)
        (work / "a.py").write_text("x = 1\n")
        git(work, "add", ".")
        git(work, "commit", "-m", "c")
        sha = git(work, "rev-parse", "HEAD")
        git(work, "push", str(bare), branch)
    return bare, sha


def test_main_branch(tmp_path):
    bare, sha = make_remote(tmp_path)
    head = clone.ls_remote(REF, bare.as_uri())
    assert (head.branch, head.commit) == ("main", sha)


def test_non_main_default_branch(tmp_path):
    bare, sha = make_remote(tmp_path, branch="develop")
    git(bare, "symbolic-ref", "HEAD", "refs/heads/trunk")
    git(bare, "branch", "trunk", sha)
    head = clone.ls_remote(REF, bare.as_uri())
    assert (head.branch, head.commit) == ("trunk", sha)


def test_empty_repo(tmp_path):
    bare, _ = make_remote(tmp_path, commit=False)
    with pytest.raises(IngestError) as exc:
        clone.ls_remote(REF, bare.as_uri())
    assert exc.value.code == "repo_empty"
    assert str(tmp_path) not in exc.value.message


def test_missing_path(tmp_path):
    with pytest.raises(IngestError) as exc:
        clone.ls_remote(REF, (tmp_path / "nope.git").as_uri())
    assert exc.value.code == "repo_not_found_or_private"
    assert str(tmp_path) not in exc.value.message
    assert "nope" not in exc.value.message


def test_timeout(monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired("git", 10)

    monkeypatch.setattr(clone.subprocess, "run", boom)
    with pytest.raises(IngestError) as exc:
        clone.ls_remote(REF)
    assert exc.value.code == "github_unavailable"


def test_unknown_failure_is_unavailable(monkeypatch):
    done = subprocess.CompletedProcess([], 128, "", "fatal: unable to access: timed out /x/y")
    monkeypatch.setattr(clone.subprocess, "run", lambda *a, **k: done)
    with pytest.raises(IngestError) as exc:
        clone.ls_remote(REF)
    assert exc.value.code == "github_unavailable"
    assert "/x/y" not in exc.value.message
