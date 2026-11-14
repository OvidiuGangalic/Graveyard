"""Turns samples/<name>/ into a real git repository with scripted, backdated history.

The sample then goes through exactly the same walker, analysers, archaeology and verdict
code as a cloned repo (spec 01, Requirement 6). Nothing about its results is hard-coded.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from graveyard import config
from graveyard.models import RepoSnapshot

SampleName = Literal["haunted", "living"]
SAMPLE_DIRS: dict[str, str] = {"haunted": "haunted-repo", "living": "living-repo"}
NOT_PART_OF_REPO = frozenset({"history.json", "expected.json"})

_MARKER = re.compile(r"^\s*(?:#|//)\s*graveyard:commit\s+(\d+)\s*$")


class SampleError(Exception):
    """The sample sources are inconsistent. A programming error, not a user error."""


def _git(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise SampleError(f"git {' '.join(args[:2])} failed: {result.stderr.strip()[:300]}")
    return result.stdout


def _force_remove(func, path, _exc) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onexc=_force_remove)


def split_regions(text: str, first_commit: int) -> list[tuple[int, str]]:
    """Return (commit number, line) pairs with marker lines removed."""
    current = first_commit
    out: list[tuple[int, str]] = []
    for line in text.splitlines():
        match = _MARKER.match(line)
        if match:
            current = int(match.group(1))
            continue
        out.append((current, line))
    return out


def _list_source_files(src: Path) -> list[str]:
    files = []
    for path in sorted(src.rglob("*")):
        if path.is_file():
            rel = path.relative_to(src).as_posix()
            if rel not in NOT_PART_OF_REPO and "__pycache__" not in rel:
                files.append(rel)
    return files


def materialise(src: Path, dest: Path, now: datetime | None = None) -> None:
    """Replay ``src/history.json`` into a fresh git repository at ``dest``."""
    now = now or datetime.now(UTC)
    history = json.loads((src / "history.json").read_text(encoding="utf-8"))
    commits = history["commits"]

    first_commit: dict[str, int] = {}
    listed_in: dict[str, set[int]] = {}
    for number, commit in enumerate(commits, start=1):
        for rel in commit["files"]:
            first_commit.setdefault(rel, number)
            listed_in.setdefault(rel, set()).add(number)

    on_disk = _list_source_files(src)
    missing = [rel for rel in on_disk if rel not in first_commit]
    if missing:
        raise SampleError(f"files not in any commit of history.json: {missing}")
    unknown = [rel for rel in first_commit if rel not in on_disk]
    if unknown:
        raise SampleError(f"history.json lists files that do not exist: {unknown}")

    regions: dict[str, list[tuple[int, str]]] = {}
    for rel in on_disk:
        text = (src / rel).read_text(encoding="utf-8")
        regions[rel] = split_regions(text, first_commit[rel])
        used = {number for number, _ in regions[rel]}
        if not used <= listed_in[rel]:
            raise SampleError(f"{rel} has a marker for a commit that does not list it")

    remove_tree(dest)
    dest.mkdir(parents=True)
    _git(["init", "-q", "-b", "main"], dest)

    for number, commit in enumerate(commits, start=1):
        for rel in commit["files"]:
            lines = [line for region, line in regions[rel] if region <= number]
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
            _git(["add", "--", rel], dest)
        when = (now - timedelta(days=int(commit["days_ago"]))).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        author = commit["author"]
        email = re.sub(r"[^a-z]+", ".", author.lower()).strip(".") + "@graveyard.invalid"
        _git(
            [
                "-c",
                f"user.name={author}",
                "-c",
                f"user.email={email}",
                "commit",
                "-q",
                "--no-verify",
                "-m",
                commit["message"],
            ],
            dest,
            env={"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when},
        )


def sample_root(name: SampleName, data_dir: Path | None = None) -> Path:
    return (data_dir or config.data_dir()) / "samples" / SAMPLE_DIRS[name]


def materialise_samples(data_dir: Path | None = None, now: datetime | None = None) -> None:
    """Called once at startup. Rebuilds both samples so their ages are relative to now."""
    for name, folder in SAMPLE_DIRS.items():
        src = config.samples_dir() / folder
        if src.is_dir():
            materialise(src, sample_root(name, data_dir), now)  # type: ignore[arg-type]


def sample_snapshot(name: SampleName, data_dir: Path | None = None) -> RepoSnapshot:
    from graveyard.ingestion import ingest_local

    root = sample_root(name, data_dir)
    if not (root / ".git").is_dir():
        materialise(config.samples_dir() / SAMPLE_DIRS[name], root)
    snapshot = ingest_local(root)
    return RepoSnapshot(
        root=snapshot.root,
        repo_url=f"sample://{SAMPLE_DIRS[name]}",
        repo_name=f"graveyard/{SAMPLE_DIRS[name]}",
        branch=snapshot.branch,
        commit=snapshot.commit,
        is_sample=True,
        has_git=True,
        history_depth=None,
        source_files=snapshot.source_files,
        text_files=snapshot.text_files,
        files_skipped=snapshot.files_skipped,
        warnings=(config.SAMPLE_WARNING,),
    )
