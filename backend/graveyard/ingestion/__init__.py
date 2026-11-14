"""Repo ingestion: the only entry points other packages call."""

from __future__ import annotations

import subprocess
from pathlib import Path

from graveyard.ingestion.walker import walk
from graveyard.models import RepoSnapshot


def _git_out(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def ingest_local(path: Path | str) -> RepoSnapshot:
    """Snapshot a local folder, with or without a .git directory."""
    root = Path(path).resolve()
    walked = walk(root)
    has_git = (root / ".git").exists()
    commit = _git_out(root, "rev-parse", "HEAD") if has_git else ""
    branch = _git_out(root, "rev-parse", "--abbrev-ref", "HEAD") if has_git else ""
    shallow = has_git and (root / ".git" / "shallow").exists()
    return RepoSnapshot(
        root=root,
        repo_url=root.as_uri(),
        repo_name=root.name,
        branch=branch,
        commit=commit,
        is_sample=False,
        has_git=bool(has_git and commit),
        history_depth=0 if shallow else None,
        source_files=walked.source_files,
        text_files=walked.text_files,
        files_skipped=walked.files_skipped,
        warnings=(),
    )
