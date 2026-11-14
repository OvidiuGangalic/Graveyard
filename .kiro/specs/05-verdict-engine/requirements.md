# Requirements Document: 05 Verdict Engine

## Introduction

The verdict engine turns a `Candidate` (evidence from an analyser) plus a `CommitInfo` (from archaeology) into a `DeadItem` with a confidence, a verdict and a one-sentence reason. It is a pure, deterministic decision table: no heuristics that are not written down here, no free text, no model calls.

It also owns the **accuracy gate**: the test that runs the whole pipeline over both sample repos and compares the result with their ground truth. No UI work starts until the gate is green.

Priority: P0.

## Glossary

- **Engine**: `backend/graveyard/verdict/`.
- **Confidence**: how sure Graveyard is that the item is dead: `high`, `medium` or `low`.
- **Verdict**: `bury` (delete it), `revive` (there is positive evidence it is used), `unsure` (the analysis is blind to how it might be used).
- **Revive flags**: `DYNAMIC_IMPORT`, `IN_DUNDER_ALL`, `LIBRARY_API`, `STRING_MATCH`.
- **Blind flags**: `UNKNOWN_DECORATOR`, `EXTERNAL_BASE_CLASS`, `SCRIPT_GLOBAL`.
- **Caution flags**: `EXPORTED`, `DYNAMIC_PATTERN_IN_FILE`, `REPO_HAS_REFLECTION`, `ARITY_MISMATCH`, `SIDE_EFFECT_IMPORT`, `CONDITIONAL_IMPORT`.
- **Old**: age strictly greater than `OLD_AGE_DAYS` (180).

## Requirements

### Requirement 1: Confidence

**User Story:** As a developer, I want a confidence level I can act on, so that I delete the `high` items first and review the rest.

#### Acceptance Criteria

1. WHEN a Candidate has any Revive flag or any Blind flag, THE Engine SHALL set confidence `low`.
2. WHEN a Candidate has no Revive or Blind flag and at least one of the following holds, THE Engine SHALL set confidence `medium`: it has a Caution flag; `test_coverage` is `covered`; it has no CommitInfo; its age is 180 days or less.
3. WHEN a Candidate has no Revive, Blind or Caution flag, `test_coverage` is `not_covered` or `unknown`, it has a CommitInfo, and it is Old, THE Engine SHALL set confidence `high`.
4. THE Engine SHALL NOT set confidence `high` in any other case.
5. WHEN the CommitInfo is a boundary commit, THE Engine SHALL treat its age as the item's age (a lower bound); an item whose lower bound is Old may be `high`.

### Requirement 2: Verdict

**User Story:** As a developer, I want a clear recommendation per item.

#### Acceptance Criteria

1. WHEN a Candidate has any Revive flag, THE Engine SHALL set verdict `revive`.
2. WHEN a Candidate has no Revive flag and has any Blind flag, THE Engine SHALL set verdict `unsure`.
3. WHEN confidence is `medium` or `high`, THE Engine SHALL set verdict `bury`.
4. THE Engine SHALL NOT produce `bury` with confidence `low`, nor `revive` or `unsure` with confidence `medium` or `high`.

### Requirement 3: Reason

**User Story:** As a developer, I want one plain sentence that explains the verdict and says what the analysis could not see, so that I can check it myself.

#### Acceptance Criteria

1. THE Engine SHALL produce `verdict_reason` from exactly one template in `design.md`, chosen by the priority order given there.
2. THE reason SHALL be one sentence, end with a full stop, contain no line breaks, and be at most 240 characters after substitution.
3. THE reason for every `bury` verdict with confidence `medium` SHALL name the specific thing that prevented `high`.
4. THE reason for every `high` verdict SHALL state that no dynamic lookups were found in the item's file, so the reader knows what was checked.
5. THE reason for every `revive` verdict SHALL cite the evidence location (file and line) when one exists.
6. WHEN the CommitInfo is a boundary commit, THE reason SHALL say "at least N days" wherever it states an age.
7. THE Engine SHALL NOT call any network service or language model.

Judge check: open three tombstones with different badges in the sample graveyard; each has a one-sentence reason that mentions a concrete fact (a file, an age, a decorator) and not a generic phrase.

### Requirement 4: DeadItem assembly

**User Story:** As a frontend developer, I want every item delivered in one stable shape.

#### Acceptance Criteria

1. THE Engine SHALL build a `DeadItem` with every field of the data model in spec 07, copying `name` from the Candidate's qualified name, and setting `deletable_as_whole_lines` to false exactly when the Candidate has flag `PARTIAL_STATEMENT`.
2. THE item `id` SHALL be the first 12 hex characters of SHA-1 over `"{language}:{kind}:{file_path}:{qualified_name}:{start_line}"`, so that the same repo at the same commit always yields the same ids.
3. IF two items would share an id, THEN THE Engine SHALL append `-2`, `-3`, ... in output order.
4. THE Engine SHALL sort items by verdict (`bury`, `unsure`, `revive`), then confidence (`high`, `medium`, `low`), then age descending (null last), then file path, then start line.
5. WHERE `MAX_ITEMS` is set (default: unset, every item is kept), WHEN more than `MAX_ITEMS` items exist, THE Engine SHALL keep the first `MAX_ITEMS` in that order and add the warning "Showing the first M of N items"; the Analysis totals SHALL count all N.

### Requirement 5: Pipeline

**User Story:** As a developer, I want one function that takes a snapshot and returns the finished analysis, so that the CLI, the tests and the API all run the same code.

#### Acceptance Criteria

1. THE pipeline SHALL run, in order: Python analyser, TypeScript analyser, archaeology, verdict engine; and SHALL return the items, the Analysis totals and the merged warnings.
2. THE pipeline SHALL skip an analyser when the snapshot has no Source files of its language.
3. THE pipeline SHALL report progress through a callback as `(phase, files_done)`, with phases `cloning`, `scanning`, `python`, `typescript`, `history`, `verdicts`.
4. WHERE `ANALYSIS_TIMEOUT_S` is set (default: unset, no time limit), IF the total run time exceeds it, THEN THE pipeline SHALL stop and raise `AnalysisTimeout`.
5. THE CLI command `python -m graveyard.cli analyse <path>` SHALL print the same JSON the API would serve for that snapshot.

### Requirement 6: Accuracy gate

**User Story:** As the product owner, I want proof that the analyser finds known dead code and spares known live code before any UI is built, because false positives are the biggest risk.

#### Acceptance Criteria

1. THE acceptance test SHALL run the full pipeline on the materialised Haunted repo and SHALL pass only if the reported items match `expected.json` exactly: same set of (name, kind, language, file path), and for each the same verdict and confidence.
2. THE acceptance test SHALL run the full pipeline on the materialised Living repo and SHALL pass only if no item has verdict `bury`, no item has confidence `high`, and the set of reported items equals the set listed in its `expected.json`.
3. THE acceptance test SHALL print, on failure, a table of missing items, unexpected items and mismatched verdicts.
4. THE CI workflow SHALL run the accuracy gate on every push, and a red gate SHALL block merging.
5. Spec 06 tasks SHALL NOT be started while the accuracy gate is failing.

## Assumptions (flagged; see docs/open-decisions.md)

- A1. The brief gives confidence for three situations; this spec fills the gaps: unknown age → `medium`; exported in an application package with no importers → `medium` (D3); a test-only reference → `medium` with a "delete with its tests" reason.
- A2. `verdict = bury` at `medium` means "delete after the one check named in the reason". The UI words the badge and the export accordingly.
- A3. The 180-day threshold is taken from the brief and is a constant, not user-configurable in P0.
- A4. An item with both Revive and Blind flags is `revive` (positive evidence outranks blindness).
