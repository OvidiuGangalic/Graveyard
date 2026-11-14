# Design Document: 04 Git Archaeology

## Overview

```
candidates ──► for each (≤300): git blame --porcelain -L s,e -- file ──► parse ──► newest commit ──► CommitInfo
                      │ fail / timeout / over cap
                      ▼
               git log -1 -- file (cached per file) ──► CommitInfo
                      │ fail / no git
                      ▼
                    None
```

Runs sequentially. On Render's free instance there is a fraction of one CPU, so parallel git processes would not help and would raise peak memory.

## Components and Interfaces

```python
@dataclass(frozen=True)
class CommitInfo:
    hash: str            # 40 hex chars
    date: datetime       # tz-aware, UTC, author date
    author: str          # name only
    is_boundary: bool

def dig(snapshot: RepoSnapshot, candidates: Sequence[Candidate], created_at: datetime,
        budget_s: float = ARCHAEOLOGY_BUDGET_S) -> ArchaeologyResult: ...
# ArchaeologyResult: commits: dict[CandidateKey, CommitInfo | None], warnings: tuple[str, ...]
# CandidateKey = (file_path, start_line, name)

def age_days(commit_date: datetime, created_at: datetime) -> int: ...     # pure

def parse_blame_porcelain(output: str) -> list[BlameCommit]: ...          # pure
```

`parse_blame_porcelain` and `age_days` are pure so they can be property-tested without a repo.

### Porcelain parsing

`git blame --porcelain` emits, for the first line blamed to each commit, a header `<40-hex> <orig-line> <final-line> <count>` followed by key/value lines: `author <name>`, `author-time <unix>`, `author-tz <+hhmm>`, ..., optionally `boundary`, then `filename <path>`, then a tab-prefixed content line. Later lines of the same commit repeat only the header. The parser keeps a dict keyed by hash, fills `author`, `author-time` and `boundary` when present, and ignores every other key and every tab-prefixed line.

`author-time` is seconds since the epoch in UTC, so no timezone arithmetic is needed.

### Constants (`config.py`)

| Constant | Value |
|---|---|
| `MAX_BLAME_ITEMS` | 300 |
| `GIT_CMD_TIMEOUT_S` | 10 |
| `ARCHAEOLOGY_BUDGET_S` | 40 |

## Data Models

`CommitInfo` maps onto the API's `DeadItem.last_commit` object (spec 07): `{hash, date, author, is_boundary}`; `age_days` is a sibling field on `DeadItem`.

## Error Handling

| Situation | Behaviour |
|---|---|
| No `.git` (local folder ingest) | Every Candidate gets `None`; one warning "No git history available" |
| Line range beyond file end (should not happen) | blame fails → per-file fallback |
| File path with spaces, quotes, non-ASCII | passed as one argv element after `--`; `core.quotepath=off` keeps output readable |
| Author name empty | `author = "Unknown"` |
| Author name longer than 100 chars | truncated to 100 |
| git binary missing | every Candidate `None`; warning; logged as an error (deployment bug) |
| Budget exhausted | Requirement 3.4 |

## Correctness Properties

- **Property P9 (age is sane).** For any two UTC instants, `age_days(d, c) ≥ 0`; `age_days(d, c) == (c − d).days` when `c ≥ d`; and for `c1 ≤ c2`, `age_days(d, c1) ≤ age_days(d, c2)`. **Validates: Requirements 4.1, 4.2.**
- **Property P15 (porcelain parser picks the newest).** For any generated list of blame commits (hash, author-time, author, boundary flag) rendered to porcelain text in any interleaving, the selected commit has the maximum author-time, ties broken by smallest hash, and `is_boundary` matches the generated flag. **Validates: Requirements 1.1, 1.4, 2.1.**
- **Property P16 (parser never crashes).** For any text, `parse_blame_porcelain` returns a list without raising. **Validates: Requirement 3.5.**

## Testing Strategy

- Fixture `make_repo(tmp_path, commits)` builds a real repo with backdated commits (same mechanism as the sample materialiser).
- Unit tests: range touched by two commits picks the newer; function untouched while its neighbour changes keeps the old date; file-level fallback; boundary detection on a repo cloned with `--depth 2` from a `file://` remote; no-git folder; path with spaces and non-ASCII characters; blame cap with 301 candidates; budget exhaustion with a zero budget.
- Check on the materialised haunted repo: items 1 and 4 in `expected.json` (730 days and 20 days) get those ages ±1 day.
