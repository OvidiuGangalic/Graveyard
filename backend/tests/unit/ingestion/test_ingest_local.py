import os
import subprocess

from graveyard.ingestion import ingest_local

ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(cwd, *args):
    cfg = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", *cfg, *args], cwd=cwd, env=ENV, check=True, capture_output=True)


def test_folder_without_git(tmp_path):
    snap = ingest_local(tmp_path)
    assert (snap.commit, snap.has_git, snap.history_depth) == ("", False, None)


def test_full_and_shallow_history(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    for i in range(3):
        (repo / "a.py").write_text(f"x = {i}")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", f"c{i}")
    assert ingest_local(repo).history_depth is None
    git(tmp_path, "clone", "-q", "--depth", "1", repo.as_uri(), "shallow")
    shallow = ingest_local(tmp_path / "shallow")
    assert shallow.has_git and shallow.history_depth == 1
