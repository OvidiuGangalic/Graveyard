# Implementation Plan: 04 Git Archaeology

Depends on spec 01 task 6 (materialised sample repos) and spec 02 task 1 (`Candidate`).

- [ ] 1. Types and pure helpers
  - [ ] 1.1 `CommitInfo`, `ArchaeologyResult`, constants in `config.py`
    - _Requirements: 1.2, 1.3_
  - [ ] 1.2 `age_days` with clamping at 0
    - _Requirements: 4.1–4.3_
  - [ ] 1.3 Property test P9
    - _Requirements: 4.1, 4.2_

- [ ] 2. Porcelain parser
  - [ ] 2.1 `parse_blame_porcelain` and newest-commit selection with the tie-break
    - _Requirements: 1.1, 1.4, 2.1_
  - [ ] 2.2 Property tests P15 and P16
    - _Requirements: 1.4, 3.5_

- [ ] 3. Git runner
  - One private `_git(args, cwd, timeout)` helper: argument list, env vars, `--no-pager`, `core.quotepath=off`, returns `(ok, stdout)` and never raises
  - _Requirements: 5.1, 5.2, 3.5_

- [ ] 4. Blame per Candidate
  - [ ] 4.1 `dig`: blame each Candidate's line range, build `CommitInfo`, never include emails
    - _Requirements: 1.1–1.3_
  - [ ] 4.2 Test fixture `make_repo` and tests: two commits in range, untouched neighbour, odd file paths
    - _Requirements: 1.1, 5.2_

- [ ] 5. Fallbacks
  - [ ] 5.1 Per-file `git log -1` with a per-file cache; used on blame failure, timeout, and beyond the 300-item cap
    - _Requirements: 3.1, 3.2_
  - [ ] 5.2 No-git and git-missing paths return `None` with a warning
    - _Requirements: 3.3_
  - [ ] 5.3 Time budget
    - _Requirements: 3.4_
  - [ ] 5.4 Tests for each fallback
    - _Requirements: 3.1–3.5_

- [ ] 6. Boundary handling
  - Set `is_boundary`; emit the history-limit warning once
  - Test on a `--depth 2` clone of a local fixture repo
  - _Requirements: 2.1–2.4_

- [ ] 7. Sample-repo check
  - Assert expected ages (±1 day) for haunted-repo items 1 and 4 after materialisation
  - _Requirements: 1.1, 4.1_
