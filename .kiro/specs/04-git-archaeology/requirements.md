# Requirements Document: 04 Git Archaeology

## Introduction

Git archaeology answers one question per Candidate: when were these lines last touched, and by whom? It runs only on Candidates (not on every function), using `git blame` on the item's line range, with `git log` on the file as a fallback. Its output feeds the age rule of the verdict engine and the "last commit" block of the tombstone.

Because the clone is shallow (500 commits), some lines predate the oldest commit available. For those, git can only say "at least this old". The archaeologist reports that honestly as a lower bound and never invents a date.

Priority: P0.

## Glossary

- **Archaeologist**: `backend/graveyard/git/archaeology.py`.
- **CommitInfo**: hash, date (author date, UTC), author name, and `is_boundary`.
- **Boundary commit**: a commit at the edge of the shallow clone; `git blame` attributes to it every line that has not changed within the available history.
- **Age**: whole days between a CommitInfo's date and the Analysis `created_at`.

## Requirements

### Requirement 1: Last commit per item

**User Story:** As a developer, I want to see who last touched a dead item and when, so that I know whom to ask and how stale it is.

#### Acceptance Criteria

1. WHEN the snapshot has git history, THE Archaeologist SHALL run `git blame --porcelain -L <start>,<end> -- <file>` for each Candidate and SHALL select the commit with the latest author time among the commits blamed for those lines.
2. THE Archaeologist SHALL return for that commit: the full 40-character hash, the author date converted to UTC, and the author name.
3. THE Archaeologist SHALL NOT return, store or log author email addresses.
4. WHEN two blamed commits have the same author time, THE Archaeologist SHALL select the one with the lexicographically smaller hash, so that results are deterministic.

Judge check: open any tombstone in the sample graveyard; "Last touched" shows a date, an author name and a 7-character commit hash.

### Requirement 2: Honest ages on shallow history

**User Story:** As a developer, I want to know when an age is only a lower bound, so that I am not misled by a truncated history.

#### Acceptance Criteria

1. WHEN the selected commit is a Boundary commit (porcelain output marks it `boundary`), THE Archaeologist SHALL set `is_boundary = true`.
2. WHEN `is_boundary` is true, THE age SHALL be computed from the Boundary commit's date and SHALL be presented everywhere as "at least N days".
3. WHEN at least one Candidate has `is_boundary = true`, THE pipeline SHALL add the warning "Git history limited to the last 500 commits; ages shown as 'at least' are lower bounds".
4. THE Archaeologist SHALL NOT fetch additional history.

### Requirement 3: Fallbacks

**User Story:** As the operator, I want archaeology to degrade, not fail, so that a git problem never costs the user the whole analysis.

#### Acceptance Criteria

1. WHEN there are more than `MAX_BLAME_ITEMS` (300) Candidates, THE Archaeologist SHALL blame the first 300 in output order and SHALL use `git log -1 --format=%H%x00%aI%x00%an -- <file>` (cached per file) for the rest, adding the warning "Ages for some items are per file, not per line range".
2. IF `git blame` fails or exceeds `GIT_CMD_TIMEOUT_S` (10) for a Candidate, THEN THE Archaeologist SHALL fall back to the per-file `git log` for that Candidate.
3. IF the per-file `git log` also fails, or the snapshot has no git history, THEN THE Archaeologist SHALL return no CommitInfo for that Candidate, and the item's `last_commit` and `age_days` SHALL be null.
4. WHEN the total time spent in archaeology exceeds `ARCHAEOLOGY_BUDGET_S` (40), THE Archaeologist SHALL stop running git commands, return no CommitInfo for the remaining Candidates, and add the warning "Git history lookup ran out of time for some items".
5. THE Archaeologist SHALL NOT raise for any git failure.

### Requirement 4: Age

#### Acceptance Criteria

1. THE age in days SHALL be `floor((created_at − commit_date) / 86,400 s)`, with both instants in UTC.
2. IF the commit date is later than `created_at` (clock skew or a forged date), THEN THE age SHALL be 0.
3. THE Archaeologist SHALL take `created_at` as an argument and SHALL NOT read the system clock.

### Requirement 5: Safety and determinism

#### Acceptance Criteria

1. THE Archaeologist SHALL run git with an argument list, `cwd` set to the snapshot root, `GIT_TERMINAL_PROMPT=0`, `GIT_OPTIONAL_LOCKS=0`, `--no-pager`, and `-c core.quotepath=off`.
2. THE Archaeologist SHALL pass file paths after a `--` separator.
3. THE Archaeologist SHALL return results keyed by Candidate identity, in an order independent of execution order.

## Assumptions (flagged; see docs/open-decisions.md)

- A1. Author **date** is used, not committer date, because it survives rebases and reflects when the code was written.
- A2. Whitespace-only and move-only commits count as "touching" the lines. `git blame -w -M` would look through them at a higher CPU cost; left out for P0.
- A3. The data model gains one field, `last_commit.is_boundary`, which the brief did not list. Without it a truncated history would be presented as fact. See D6.
- A4. The GitHub API is not used for commit data (one request per file would exhaust the anonymous limit of 60/hour).
