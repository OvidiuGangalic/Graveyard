"""Git archaeology: when, and by whom, was each Candidate last touched? (spec 04)

Runs ``git blame`` on a Candidate's line range, falling back to ``git log -1`` on the file.
Never raises, never fetches history, never reads the clock, never returns an email address.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from graveyard import config
from graveyard.models import (
    Candidate,
    CommitInfo,
    Language,
    ProgressFn,
    RepoSnapshot,
    no_progress,
)

CandidateKey = tuple[Language, str, int, str]

NO_GIT_WARNING = "No git history available, so ages are unknown"
PER_FILE_WARNING = "Ages for some items are per file, not per line range"
OUT_OF_TIME_WARNING = "Git history lookup ran out of time for some items"
_ZERO_HASH = "0" * 40
_HEADER = re.compile(r"^([0-9a-f]{40}) \d+ \d+(?: \d+)?$")
_MAX_AUTHOR = 100


@dataclass(frozen=True)
class BlameCommit:
    hash: str
    author_time: int  # seconds since the epoch, UTC
    author: str
    boundary: bool = False


@dataclass(frozen=True)
class ArchaeologyResult:
    commits: dict[CandidateKey, CommitInfo | None]
    warnings: tuple[str, ...]


def candidate_key(candidate: Candidate) -> CandidateKey:
    return (candidate.language, candidate.file_path, candidate.start_line, candidate.qualified_name)


def age_days(commit_date: datetime, created_at: datetime) -> int:
    """Whole days from ``commit_date`` to ``created_at``; 0 if the commit is in the future."""
    return max(0, (created_at - commit_date).days)


def parse_blame_porcelain(output: str) -> list[BlameCommit]:
    """One BlameCommit per distinct commit in ``git blame --porcelain`` output. Never raises."""
    fields: dict[str, dict[str, str | bool]] = {}
    current: dict[str, str | bool] | None = None
    for line in output.splitlines():
        if line.startswith("\t"):
            continue  # source line
        header = _HEADER.match(line)
        if header:
            current = fields.setdefault(header.group(1), {})
        elif current is not None:
            if line == "boundary":
                current["boundary"] = True
            elif line.startswith("author "):
                current.setdefault("author", line[7:])
            elif line.startswith("author-time "):
                current.setdefault("time", line[12:].strip())
    commits = []
    for commit_hash, data in fields.items():
        try:
            when = int(str(data.get("time", "")))
        except ValueError:
            continue
        commits.append(
            BlameCommit(commit_hash, when, str(data.get("author", "")), bool(data.get("boundary")))
        )
    return commits


def newest_commit(commits: Sequence[BlameCommit]) -> BlameCommit | None:
    """Latest author time, ties to the smallest hash. Uncommitted lines are ignored."""
    real = [c for c in commits if c.hash != _ZERO_HASH]
    return min(real, key=lambda c: (-c.author_time, c.hash), default=None)


def _git_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
        GIT_OPTIONAL_LOCKS="0",
    )
    return env


def _git(args: list[str], cwd: Path, timeout: float) -> str | None:
    """Run git; return stdout, or None on any failure (missing binary, timeout, non-zero)."""
    try:
        result = subprocess.run(
            ["git", "--no-pager", "-c", "core.quotepath=off", *args],
            cwd=cwd,
            env=_git_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return result.stdout if result.returncode == 0 else None


def _shallow_hashes(root: Path) -> frozenset[str]:
    try:
        return frozenset((root / ".git" / "shallow").read_text(encoding="ascii").split())
    except (OSError, ValueError):
        return frozenset()


def _clean_author(name: str) -> str:
    return name.strip()[:_MAX_AUTHOR] or "Unknown"


def _utc(epoch: int) -> datetime | None:
    try:
        return datetime.fromtimestamp(epoch, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _from_blame(output: str, shallow: frozenset[str]) -> CommitInfo | None:
    best = newest_commit(parse_blame_porcelain(output))
    when = _utc(best.author_time) if best else None
    if best is None or when is None:
        return None
    # Git also marks a real root commit `boundary`; that is only a lower bound when shallow.
    is_boundary = best.hash in shallow or (best.boundary and bool(shallow))
    return CommitInfo(best.hash, when, _clean_author(best.author), is_boundary)


def _from_log(output: str, shallow: frozenset[str]) -> CommitInfo | None:
    parts = output.strip("\n").split("\x00")
    if len(parts) != 3 or not re.fullmatch(r"[0-9a-f]{40}", parts[0]):
        return None
    try:
        when = datetime.fromisoformat(parts[1]).astimezone(UTC)
    except ValueError:
        return None
    return CommitInfo(parts[0], when, _clean_author(parts[2]), parts[0] in shallow)


def dig(
    snapshot: RepoSnapshot,
    candidates: Sequence[Candidate],
    created_at: datetime,
    progress: ProgressFn = no_progress,
) -> ArchaeologyResult:
    """Find the last commit touching each Candidate.

    ``created_at`` is part of the pipeline signature; ages are derived by the caller with
    :func:`age_days`, so this function never touches a clock for dates.
    """
    del created_at
    keys = [candidate_key(c) for c in candidates]
    if not snapshot.has_git:
        return ArchaeologyResult(dict.fromkeys(keys), (NO_GIT_WARNING,) if keys else ())

    budget = config.ARCHAEOLOGY_BUDGET_S
    deadline = None if budget is None else time.monotonic() + budget
    shallow = _shallow_hashes(snapshot.root)
    file_cache: dict[str, CommitInfo | None] = {}
    commits: dict[CandidateKey, CommitInfo | None] = {}
    per_file = out_of_time = False

    def run(args: list[str]) -> str | None:
        if deadline is None:
            return _git(args, snapshot.root, config.GIT_CMD_TIMEOUT_S)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        return _git(args, snapshot.root, min(config.GIT_CMD_TIMEOUT_S, remaining))

    for index, (candidate, key) in enumerate(zip(candidates, keys, strict=True)):
        progress("archaeology", index)
        try:
            info = None
            if index < config.MAX_BLAME_ITEMS:
                span = f"{candidate.start_line},{candidate.end_line}"
                out = run(["blame", "--porcelain", "-L", span, "--", candidate.file_path])
                info = _from_blame(out, shallow) if out is not None else None
            if info is None:
                per_file = True
                path = candidate.file_path
                if path not in file_cache:
                    log = run(["log", "-1", "--format=%H%x00%aI%x00%an", "--", path])
                    file_cache[path] = _from_log(log, shallow) if log is not None else None
                info = file_cache[path]
        except TimeoutError:
            out_of_time = True
            for rest in keys[index:]:
                commits[rest] = None
            break
        commits[key] = info

    warnings = []
    if per_file:
        warnings.append(PER_FILE_WARNING)
    if any(c is not None and c.is_boundary for c in commits.values()):
        depth = snapshot.history_depth or config.CLONE_DEPTH
        warnings.append(
            f"Git history limited to the last {depth} commits; "
            "ages shown as 'at least' are lower bounds"
        )
    if out_of_time:
        warnings.append(OUT_OF_TIME_WARNING)
    return ArchaeologyResult(commits, tuple(warnings))
