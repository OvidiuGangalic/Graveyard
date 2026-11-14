# Design Document: 05 Verdict Engine

## Overview

```
Candidate + CommitInfo|None + created_at
        │
        ▼
 judge(candidate, commit, created_at) -> Judgement(confidence, verdict, reason_id, reason)
        │
        ▼
 assemble(...) -> DeadItem          pipeline.run(snapshot, created_at, progress) -> PipelineResult
```

`judge` is a pure function over a small input, which makes it exhaustively testable: the flag set, three coverage values, and four age classes (none, ≤180, >180, boundary variants) give a finite space.

## Decision table

Evaluate top to bottom; the first matching row decides. `age` is the CommitInfo's age in days, or absent.

| Row | Condition | Confidence | Verdict | Reason ID |
|---|---|---|---|---|
| 1 | `DYNAMIC_IMPORT` | low | revive | `RV_DYNAMIC_IMPORT` |
| 2 | `IN_DUNDER_ALL` | low | revive | `RV_DUNDER_ALL` |
| 3 | `LIBRARY_API` | low | revive | `RV_LIBRARY_API` |
| 4 | `STRING_MATCH` | low | revive | `RV_STRING_MATCH` |
| 5 | `UNKNOWN_DECORATOR` | low | unsure | `UN_DECORATOR` |
| 6 | `EXTERNAL_BASE_CLASS` | low | unsure | `UN_BASE_CLASS` |
| 7 | `SCRIPT_GLOBAL` | low | unsure | `UN_SCRIPT_GLOBAL` |
| 8 | `EXPORTED` | medium | bury | `BM_EXPORTED` |
| 9 | `DYNAMIC_PATTERN_IN_FILE` | medium | bury | `BM_DYNAMIC_FILE` |
| 10 | `REPO_HAS_REFLECTION` | medium | bury | `BM_REFLECTION` |
| 10a | `ARITY_MISMATCH` | medium | bury | `BM_ARITY` |
| 11 | `SIDE_EFFECT_IMPORT` | medium | bury | `BM_SIDE_EFFECT` |
| 12 | `CONDITIONAL_IMPORT` | medium | bury | `BM_CONDITIONAL` |
| 13 | `test_coverage == covered` | medium | bury | `BM_TEST_ONLY` |
| 14 | no CommitInfo | medium | bury | `BM_NO_HISTORY` |
| 15 | `age ≤ 180` and `is_boundary` | medium | bury | `BM_SHALLOW_HISTORY` |
| 16 | `age ≤ 180` | medium | bury | `BM_RECENT` |
| 17 | otherwise, kind `function` | high | bury | `BH_FUNCTION` |
| 18 | otherwise, kind `import` | high | bury | `BH_IMPORT` |

P1 only: kind `test` with `ZOMBIE_SKIPPED` / `ZOMBIE_EMPTY` → medium / bury / `BM_ZOMBIE_SKIPPED` / `BM_ZOMBIE_EMPTY`, evaluated before row 8.

## Reason templates

`{age}` renders as `N` or, for a boundary commit, `at least N`. `{loc}` renders as `path:line` of the first relevant caller. Every template is one sentence.

| Reason ID | Template |
|---|---|
| `RV_DYNAMIC_IMPORT` | Its file is loaded with a dynamic import at {loc}, so it is probably used at runtime. |
| `RV_DUNDER_ALL` | It is listed in `__all__` at {loc}, so it is part of the public API and may be used by code outside this repo. |
| `RV_LIBRARY_API` | It is exported from a published package ({detail}), and code outside this repo may import it, which this analysis cannot see. |
| `RV_STRING_MATCH` | Nothing calls it directly, but its name appears as a string at {loc}, which suggests it is looked up by name at runtime. |
| `UN_DECORATOR` | Nothing calls it directly, but the decorator `{detail}` may register it with a framework, which static analysis cannot confirm. |
| `UN_BASE_CLASS` | Nothing calls it directly, but its class extends `{detail}` from outside this repo, which may call this method itself. |
| `UN_SCRIPT_GLOBAL` | Nothing calls it, but this file is a plain script whose functions are global and may be called from HTML or other scripts. |
| `BM_EXPORTED` | It is exported but nothing in this repo imports it, so it is safe to delete unless code outside this repo uses it. |
| `BM_DYNAMIC_FILE` | No references were found, but its file uses dynamic lookups ({detail}), so a call at runtime cannot be ruled out. |
| `BM_REFLECTION` | No references were found, but this repo calls methods by computed name, so a call at runtime cannot be ruled out. |
| `BM_ARITY` | Other code calls something with this name at {detail}, but with arguments this definition cannot accept, so that call is taken to mean a different function. |
| `BM_SIDE_EFFECT` | It is never used in this file, but importing `{detail}` may have side effects, so check before removing it. |
| `BM_CONDITIONAL` | It is never used in this file, but it is imported conditionally, which is often a deliberate availability check. |
| `BM_TEST_ONLY` | Only tests reference it ({n} place(s), first at {loc}), so delete it together with those tests. |
| `BM_NO_HISTORY` | No references were found, but its age is unknown because git history was unavailable. |
| `BM_SHALLOW_HISTORY` | No references were found, but the available git history only shows it is {age} days old. |
| `BM_RECENT` | No references were found, but it was touched {age} days ago, so it may be work in progress. |
| `BH_FUNCTION` | No references anywhere in this repo, no test mentions it, it has been untouched for {age} days, and its file has no dynamic lookups. |
| `BH_IMPORT` | It is never used in this file, it has been untouched for {age} days, and the file has no dynamic lookups. |

`{detail}` comes from `Candidate.flag_details` and is truncated to 60 characters. If a required placeholder has no value (for example no caller location), the fragment "at {loc}" is replaced by "in this repo".

## Components and Interfaces

```python
# verdict/engine.py
def judge(c: Candidate, commit: CommitInfo | None, created_at: datetime) -> Judgement: ...
def assemble(c: Candidate, commit: CommitInfo | None, j: Judgement, created_at: datetime) -> DeadItem: ...
def finalise(items: list[DeadItem]) -> tuple[list[DeadItem], list[str]]:   # id dedup, sort, cap, warnings

# verdict/reasons.py
TEMPLATES: Mapping[str, str]
def render(reason_id: str, c: Candidate, commit: CommitInfo | None, created_at: datetime) -> str: ...

# pipeline.py
def run(snapshot: RepoSnapshot, created_at: datetime, progress: ProgressFn, deadline: float) -> PipelineResult: ...
# PipelineResult: items, total_files_scanned, files_skipped, items_by_language, items_by_verdict, total_dead_items, warnings
```

## Error Handling

- `judge` cannot fail: every input maps to a row (rows 17/18 are the default).
- `render` with an unknown reason ID is a programming error and raises in tests; in production it returns "No references were found." and logs an error.
- `pipeline.run` lets only `AnalysisTimeout` and `IngestError` escape; any other exception from a stage is wrapped as `PipelineError("internal_error")` with the original logged.

## Correctness Properties

Strategy `candidate()` draws any subset of flags, any coverage value, either kind, 0–3 callers; `commit()` draws `None` or a CommitInfo with age 0–5,000 days and a boundary flag.

- **Property P7 (high is safe).** For any generated candidate and commit: confidence `high` implies no Revive, Blind or Caution flag, coverage ≠ `covered`, commit present, and age > 180. **Validates: Requirements 1.3, 1.4.**
- **Property P7b (verdict and confidence agree).** `bury` ⇔ confidence ∈ {medium, high}; `revive`/`unsure` ⇔ confidence `low`. **Validates: Requirement 2.4.**
- **Property P8 (evidence only lowers confidence).** For any candidate and any flag not already present, adding the flag never raises confidence (`low < medium < high`); changing coverage to `covered` never raises it; reducing age never raises it. **Validates: Requirements 1.1, 1.2.**
- **Property P17 (reasons are well-formed).** For any candidate and commit, the reason is non-empty, a single line, ends with ".", has at most 240 characters, contains no unreplaced `{`, and contains "at least" whenever it states an age from a boundary commit. **Validates: Requirements 3.2, 3.6.**
- **Property P4 (pipeline is deterministic and order-independent).** For any generated repo (from the spec 02 and 03 strategies), running the pipeline twice, and with `source_files` shuffled, yields equal item lists, including ids. **Validates: Requirements 4.2, 4.4.**
- **Property P18 (ids are unique).** In any pipeline result, item ids are pairwise distinct. **Validates: Requirement 4.3.**

## Testing Strategy

- Decision-table test: one case per row, plus one per adjacent-row priority (row n and row n+1 both true → row n wins).
- Reason snapshot test: render every template with a fixed candidate; the snapshot file is reviewed by a human for tone and truthfulness.
- Accuracy gate: `backend/tests/acceptance/test_sample_repos.py`, marked `acceptance`, as Requirement 6.
