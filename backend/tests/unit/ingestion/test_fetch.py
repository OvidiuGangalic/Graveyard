from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from graveyard import config
from graveyard.ingestion import fetch
from graveyard.models import IngestError, RepoRef

REF = RepoRef("o", "r")


def _git(cwd: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _make_repo(path: Path, commits: int, branch: str = "main") -> str:
    path.mkdir()
    _git(path, "init", "-b", branch)
    for i in range(commits):
        (path / f"f{i}.txt").write_text(f"{i}\n")
        _git(path, "add", ".")
        _git(path, "commit", "-m", f"c{i}")
    return _git(path, "rev-parse", "HEAD")


@pytest.fixture(autouse=True)
def _allow_file_protocol(monkeypatch):
    # Test helper only: production leaves _EXTRA_CONFIG empty.
    monkeypatch.setattr(fetch, "_EXTRA_CONFIG", ("protocol.file.allow=always",))


def _url(path: Path) -> str:
    return path.resolve().as_uri()


def test_clone_returns_head_and_is_shallow(tmp_path, monkeypatch):
    # git writes .git/shallow only when history is actually cut, so depth is below 3 here.
    head = _make_repo(tmp_path / "work", 3)
    monkeypatch.setattr(config, "CLONE_DEPTH", 2)
    dest = fetch.new_clone_dir()
    assert fetch.shallow_clone(REF, "main", dest, url=_url(tmp_path / "work")) == head
    assert (dest / ".git" / "shallow").is_file()


def test_depth_is_respected(tmp_path, monkeypatch):
    # Depth 2 on 5 commits is cheaper than building 501 commits; it exercises the same flag.
    _make_repo(tmp_path / "work", 5)
    monkeypatch.setattr(config, "CLONE_DEPTH", 2)
    dest = fetch.new_clone_dir()
    fetch.shallow_clone(REF, "main", dest, url=_url(tmp_path / "work"))
    assert _git(dest, "rev-list", "--count", "HEAD") == "2"


def test_non_default_branch(tmp_path):
    work = tmp_path / "work"
    _make_repo(work, 1)
    _git(work, "checkout", "-b", "dev")
    (work / "d.txt").write_text("d\n")
    _git(work, "add", ".")
    _git(work, "commit", "-m", "dev")
    dev_head = _git(work, "rev-parse", "HEAD")
    _git(work, "checkout", "main")
    dest = fetch.new_clone_dir()
    assert fetch.shallow_clone(REF, "dev", dest, url=_url(work)) == dev_head


def test_bad_url_is_github_unavailable_and_dest_removed(tmp_path):
    dest = fetch.new_clone_dir()
    with pytest.raises(IngestError) as exc:
        fetch.shallow_clone(REF, "main", dest, url=_url(tmp_path / "missing"))
    assert exc.value.code == "github_unavailable"
    assert str(tmp_path) not in exc.value.message
    assert not dest.exists()


def test_timeout(monkeypatch):
    monkeypatch.setattr(config, "CLONE_TIMEOUT_S", 1)

    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired("git", 1)

    monkeypatch.setattr(subprocess, "run", boom)
    dest = fetch.new_clone_dir()
    with pytest.raises(IngestError) as exc:
        fetch.shallow_clone(REF, "main", dest, url="file:///x")
    assert exc.value.code == "clone_timeout"
    assert not dest.exists()


def test_disk_limit_exceeded(tmp_path, monkeypatch):
    _make_repo(tmp_path / "work", 2)
    monkeypatch.setattr(config, "MAX_CLONE_DISK_MB", 1)
    monkeypatch.setattr(fetch, "_dir_size_bytes", lambda p: 5 * 1024 * 1024)
    dest = fetch.new_clone_dir()
    with pytest.raises(IngestError) as exc:
        fetch.shallow_clone(REF, "main", dest, url=_url(tmp_path / "work"))
    assert exc.value.code == "repo_too_large"
    assert "5 MB" in exc.value.message and "1 MB" in exc.value.message
    assert not dest.exists()


def test_disk_limit_not_exceeded(tmp_path, monkeypatch):
    _make_repo(tmp_path / "work", 1)
    monkeypatch.setattr(config, "MAX_CLONE_DISK_MB", 100)
    dest = fetch.new_clone_dir()
    fetch.shallow_clone(REF, "main", dest, url=_url(tmp_path / "work"))
    assert dest.exists()


def test_new_clone_dir_is_random_hex_under_clones_dir():
    a, b = fetch.new_clone_dir(), fetch.new_clone_dir()
    assert a != b
    for d in (a, b):
        assert d.parent == fetch.clones_dir()
        assert re.fullmatch(r"[0-9a-f]{16}", d.name)


def test_cleanup_and_cleanup_all():
    a, b = fetch.new_clone_dir(), fetch.new_clone_dir()
    (b / "x").mkdir()
    (b / "x" / "y.txt").write_text("y")
    fetch.cleanup(a)
    assert not a.exists() and b.exists()
    fetch.new_clone_dir()
    fetch.cleanup_all()
    assert list(fetch.clones_dir().iterdir()) == []


def test_cleanup_all_without_clones_dir():
    fetch.cleanup_all()
