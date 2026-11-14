"""Git archaeology: when, and by whom, was each Candidate last touched? (spec 04)

Runs ``git blame`` on a Candidate's line range, falling back to ``git log -1`` on the file.
Never raises, never fetches history, never reads the clock, never returns an email address.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

_ZERO_HASH = "0" * 40
_HEADER = re.compile(r"^([0-9a-f]{40}) \d+ \d+(?: \d+)?$")


@dataclass(frozen=True)
class BlameCommit:
    hash: str
    author_time: int  # seconds since the epoch, UTC
    author: str
    boundary: bool = False


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
