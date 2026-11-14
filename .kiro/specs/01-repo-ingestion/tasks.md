# Implementation Plan: 01 Repo Ingestion

Tasks 1–6 need no network and unblock specs 02–05. Tasks 7–11 add GitHub and are done on day 7.

- [ ] 1. Create the backend skeleton
  - `backend/pyproject.toml` with the approved dependencies and a `dev` extra; `ruff` config (line length 100, exclude `samples/`); `pytest` markers `property`, `acceptance`, `network`
  - Empty package `backend/graveyard/` with the sub-packages from `steering/structure.md`
  - `backend/graveyard/config.py` with every constant from the Limits table
  - _Requirements: 4.1, 5.4, 5.6_

- [ ] 2. Define the internal types
  - `RepoRef`, `SourceFile`, `RepoSnapshot`, `IngestError` in `backend/graveyard/models.py`, exactly as in `design.md`
  - _Requirements: 5.9, 6.4_

- [ ] 3. Implement the walker
  - [ ] 3.1 `walk(root)` with directory and file exclusions, size skip, generated-file header check, symlink containment
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 7.3_
  - [ ] 3.2 Language classification and `is_test` rules; text-reference file listing
    - _Requirements: 5.5, 5.9_
  - [ ] 3.3 `too_many_files` error and empty-result behaviour
    - _Requirements: 5.6, 5.7_
  - [ ] 3.4 Unit tests on `tmp_path` trees, one per exclusion rule
    - _Requirements: 5.1–5.9_
  - [ ] 3.5 Property test P14 (walker containment)
    - _Requirements: 5.1, 5.2_

- [ ] 4. Write the haunted sample repo
  - Source files for all 19 ground-truth items and the live controls, with `graveyard:commit N` markers
  - `history.json`, `expected.json`, `README.md`
  - Exclude `samples/` from ruff, eslint, prettier and tsconfig
  - _Requirements: 6.1_

- [ ] 5. Write the living sample repo
  - One file per pattern in "Living repo contents"; `history.json` with all commits older than 400 days (so age never rescues a false positive); `expected.json` with `forbidden`
  - _Requirements: 6.2_

- [ ] 6. Implement sample materialisation and local ingestion
  - [ ] 6.1 `materialise_samples`: replay `history.json` into a real git repo with backdated author and committer dates; strip markers; fail if any file is uncommitted
    - _Requirements: 6.3_
  - [ ] 6.2 `sample_snapshot` and `ingest_local(path)` (works with and without `.git`)
    - _Requirements: 6.4, 6.5, 6.7_
  - [ ] 6.3 Tests: commit count, blame attribution of marker-split regions, idempotent re-materialisation
    - _Requirements: 6.3_
  - [ ] 6.4 CLI stub `python -m graveyard.cli analyse <path>` that prints the `RepoSnapshot` file list as JSON
    - _Requirements: 6.7_

- [ ] 7. Implement URL parsing
  - [ ] 7.1 `parse_repo_url` for every accepted form; `invalid_url` for the rest
    - _Requirements: 1.1–1.6_
  - [ ] 7.2 Table-driven unit tests (at least 20 cases)
    - _Requirements: 1.1–1.5_
  - [ ] 7.3 Property tests P10 and P10b
    - _Requirements: 1.1, 1.3, 1.4_

- [ ] 8. Implement `ls_remote`
  - Parse `--symref` output for branch and commit; map failures to `repo_not_found_or_private`, `repo_empty`, `github_unavailable`
  - Tests against a local bare repo and an empty bare repo
  - _Requirements: 2.1–2.5_

- [ ] 9. Implement the GitHub size pre-check
  - One request, optional token, 5 s timeout; `None` on 403/429/timeout/error
  - Tests with `httpx.MockTransport`
  - _Requirements: 3.1–3.4_

- [ ] 10. Implement the shallow clone
  - [ ] 10.1 `shallow_clone` with the exact flags, env vars and timeout; partial directory removed on failure
    - _Requirements: 4.1, 4.2, 7.1, 7.2_
  - [ ] 10.2 Post-clone disk-size check and `rev-parse HEAD`
    - _Requirements: 4.3, 4.4_
  - [ ] 10.3 Clone cleanup on completion and at startup
    - _Requirements: 4.5, 4.6_
  - [ ] 10.4 Tests against a local bare repo with more than 500 commits (assert depth is 500)
    - _Requirements: 4.1_

- [ ] 11. Wire `preflight` and `ingest_remote`
  - Compose tasks 7–10 and 3; pass discovered-file count to the progress callback; collect warnings
  - Test each error code end to end with local fixtures
  - _Requirements: 3.3, 5.8, and every error code in design.md_
