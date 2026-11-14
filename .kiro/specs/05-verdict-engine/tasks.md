# Implementation Plan: 05 Verdict Engine

Depends on specs 02, 03 (Candidates) and 04 (`CommitInfo`). The API models `DeadItem` and `Analysis` are defined in spec 07 design; create them here in task 1 if spec 07 has not started.

- [ ] 1. Types
  - `Judgement`, `PipelineResult`, `PipelineError`; pydantic `DeadItem`, `LastCommit`, `CallerOut` exactly as spec 07 design "Data Models"
  - Constants `OLD_AGE_DAYS`, `MAX_ITEMS`, `ANALYSIS_TIMEOUT_S` in `config.py`
  - _Requirements: 4.1_

- [ ] 2. Decision table
  - [ ] 2.1 `judge`: rows 1–18 in order
    - _Requirements: 1.1–1.5, 2.1–2.4_
  - [ ] 2.2 Unit tests: one per row, one per adjacent-row priority
    - _Requirements: 1.1–1.5, 2.1–2.4_

- [ ] 3. Reasons
  - [ ] 3.1 `TEMPLATES` and `render`, with `{age}` boundary wording, `{loc}` fallback and `{detail}` truncation
    - _Requirements: 3.1–3.6_
  - [ ] 3.2 Snapshot test of every rendered template; read the snapshot aloud once and fix any sentence that overclaims
    - _Requirements: 3.3, 3.4, 3.5_

- [ ] 4. Assembly
  - [ ] 4.1 `assemble`: field mapping, stable id
    - _Requirements: 4.1, 4.2_
  - [ ] 4.2 `finalise`: id de-duplication, sort order, 500-item cap with warning
    - _Requirements: 4.3, 4.4, 4.5_
  - [ ] 4.3 Unit tests for sort order, cap and id collisions
    - _Requirements: 4.3–4.5_

- [ ] 5. Pipeline
  - [ ] 5.1 `pipeline.run`: stage order, skipping absent languages, progress phases, warnings merge, totals
    - _Requirements: 5.1–5.3_
  - [ ] 5.2 Deadline and `AnalysisTimeout`; wrapping of unexpected stage errors
    - _Requirements: 5.4_
  - [ ] 5.3 CLI prints the full API-shaped JSON for a local path
    - _Requirements: 5.5_

- [ ] 6. Property tests
  - [ ] 6.1 `candidate()` and `commit()` strategies; P7, P7b
    - _Requirements: 1.3, 1.4, 2.4_
  - [ ] 6.2 P8 (evidence only lowers confidence)
    - _Requirements: 1.1, 1.2_
  - [ ] 6.3 P17 (reasons well-formed)
    - _Requirements: 3.2, 3.6_
  - [ ] 6.4 P4 (pipeline deterministic), P18 (unique ids)
    - _Requirements: 4.2, 4.3, 4.4_

- [ ] 7. Accuracy gate
  - [ ] 7.1 `test_sample_repos.py`: haunted repo exact match against `expected.json`
    - _Requirements: 6.1, 6.3_
  - [ ] 7.2 Living repo: no `bury`, no `high`, exact item set
    - _Requirements: 6.2, 6.3_
  - [ ] 7.3 Fix analysers until both pass. Change `expected.json` only when the ground truth itself was wrong, and say why in the commit message
    - _Requirements: 6.1, 6.2_

- [ ] 8. Gate in CI
  - `.github/workflows/ci.yml`: backend lint, unit tests, property tests, accuracy gate on every push (git must be available on the runner; set `user.name`/`user.email` for the materialiser)
  - Record in `steering/roadmap.md` the date the gate first went green
  - _Requirements: 6.4, 6.5_
