# Implementation Plan: 02 Python Analyzer

Depends on spec 01 tasks 1–6 (types, walker, sample repos, CLI stub).

- [ ] 1. Add the shared analyser contract
  - `Flag`, `Caller`, `Candidate`, `AnalyserResult`, `ProgressFn`, `AnalysisTimeout` in `models.py`, exactly as in `design.md`
  - _Requirements: 4.1–4.8, 7.2_

- [ ] 2. Collect definitions
  - [ ] 2.1 `definitions.py`: Analysable functions with name, qualified name, Span (decorators included), method flag, decorator source text, class bases, and the parameter list (positional count, names, defaults, `*args`, `**kwargs`); module-level bindings per file (defs, classes, assignments, imports, star imports)
    - _Requirements: 1.1, 1.2_
  - [ ] 2.2 Merge same-name definitions in one scope
    - _Requirements: 1.3_
  - [ ] 2.3 Unit tests: nested functions ignored, decorated Span, async functions, overloads, property + setter
    - _Requirements: 1.1–1.4_

- [ ] 3. Collect references
  - [ ] 3.1 `references.py`: rules PY-R1 to PY-R5 as an `ast.NodeVisitor` producing `Occurrence` records
    - _Requirements: 2.1_
  - [ ] 3.2 PY-R6: string annotations and `# type:` comments
    - _Requirements: 6.2_
  - [ ] 3.3 Fallback tokenisation for unparseable files
    - _Requirements: 2.6, 7.1_
  - [ ] 3.4 Repo-wide `ReferenceIndex` (capped at 50 occurrences per name)
    - _Requirements: 2.1_
  - [ ] 3.5 Unit tests, one per PY-R rule
    - _Requirements: 2.1, 2.6_
  - [ ] 3.6 Pure name-matching join first (every occurrence unresolved): this is the `resolve_all_unresolved=True` path and the day-2 fallback if resolution slips
    - _Requirements: 2.7, 2.10_
  - [ ] 3.7 `resolve.py`: `ModuleIndex` and module resolution (relative imports, dotted-suffix match, re-export following, star imports); rules PY-S1, PY-S2, PY-S3, PY-S6
    - _Requirements: 2.4, 2.9_
  - [ ] 3.8 `ClassIndex` and class families; rules PY-S4, PY-S5
    - _Requirements: 2.4_
  - [ ] 3.9 Arity rule PY-A1 and flag `ARITY_MISMATCH` (PY-F7)
    - _Requirements: 2.8_
  - [ ] 3.10 Unit tests, one per PY-S rule and for PY-A1 (too many positionals, unknown keyword, missing required, `*args` call skipped, decorated definition skipped, method `self` dropped)
    - _Requirements: 2.4, 2.7–2.9_

- [ ] 4. Join definitions with references
  - [ ] 4.1 Direct-reference test (resolved, or unresolved and arity-compatible) with own-Span exclusion; Test references become callers of kind `test_reference`
    - _Requirements: 2.2–2.5, 2.7_
  - [ ] 4.2 `test_coverage` for functions
    - _Requirements: 5.1–5.3_
  - [ ] 4.3 Snippet extraction and truncation
    - _Requirements: 8.1, 8.2_
  - [ ] 4.4 Wire `analyse_python` into the CLI; run it on `samples/haunted-repo` and eyeball the output
    - _Requirements: 7.3, 7.4_

- [ ] 5. Exemptions
  - [ ] 5.1 `entrypoints.py`: PY-E1, PY-E2, PY-E7 (names and stubs)
    - _Requirements: 3.1_
  - [ ] 5.2 PY-E3, PY-E8 (decorator tables)
    - _Requirements: 3.1_
  - [ ] 5.3 PY-E4 (tests), PY-E9 (protocol method names)
    - _Requirements: 3.1_
  - [ ] 5.4 PY-E5 (Django)
    - _Requirements: 3.1_
  - [ ] 5.5 PY-E6 (CLI): `pyproject.toml` via `tomllib`, `setup.py`/`setup.cfg` via regex for `name = module:function`
    - _Requirements: 3.1_
  - [ ] 5.6 One unit test per PY-E rule, named after the rule ID
    - _Requirements: 3.2, 3.3_

- [ ] 6. Flags and weak references
  - [ ] 6.1 PY-F1 `UNKNOWN_DECORATOR` and PY-F2 `EXTERNAL_BASE_CLASS`
    - _Requirements: 4.4, 4.5_
  - [ ] 6.2 PY-F3 `DYNAMIC_PATTERN_IN_FILE` and PY-F4 `REPO_HAS_REFLECTION`
    - _Requirements: 4.6, 4.7_
  - [ ] 6.3 PY-F5 `IN_DUNDER_ALL`
    - _Requirements: 4.3_
  - [ ] 6.4 PY-W1 string literals in Python files; PY-W2 Text-reference files (shared helper in `analyzers/common.py`, reused by spec 03)
    - _Requirements: 4.1, 4.2, 4.8_
  - [ ] 6.5 One unit test per PY-F and PY-W rule
    - _Requirements: 4.1–4.8_

- [ ] 7. Dead imports
  - [ ] 7.1 `imports.py`: collect ImportBindings with bound name and statement line range
    - _Requirements: 6.1, 6.6_
  - [ ] 7.2 Same-file usage check, including PY-R6 names
    - _Requirements: 6.1, 6.2_
  - [ ] 7.3 Exclusions PY-I1 to PY-I7
    - _Requirements: 6.3_
  - [ ] 7.4 Flags `SIDE_EFFECT_IMPORT`, `CONDITIONAL_IMPORT`, `PARTIAL_STATEMENT`
    - _Requirements: 6.4, 6.5, 6.7_
  - [ ] 7.5 One unit test per PY-I rule and per flag
    - _Requirements: 6.1–6.7_

- [ ] 8. Robustness
  - Per-file exception containment, deadline check between files, sorted output, progress callback
  - Tests: null bytes, Python 2 file, 5 MB file, deadline already passed
  - _Requirements: 7.1–7.5_

- [ ] 9. Property tests
  - [ ] 9.1 `strategies.py`: `python_repo()`, `identifier()`, `exempt_function()`
    - _Requirements: 7.2_
  - [ ] 9.2 P1 never crashes, P2 bounded
    - _Requirements: 7.1, 1.1, 8.1_
  - [ ] 9.3 P3 caller flips, P5 adding files never kills
    - _Requirements: 2.1, 2.2, 2.4_
  - [ ] 9.5 P24 same name in two modules, P25 resolution only adds, P26 arity never hides a compatible call
    - _Requirements: 2.4, 2.8–2.10_
  - [ ] 9.4 P6 exempt never reported, P13 import use revives, P4a deterministic
    - _Requirements: 3.2, 6.1, 7.2_

- [ ] 10. Regression corpus harness
  - Parametrised test over `cases/*.py` with `# expect:` headers; seed with 10 cases taken from the living repo patterns
  - _Requirements: 3.3_

- [ ] 11. Python half of the accuracy gate
  - Compare `analyse_python` Candidates on both sample repos against the Python entries of `expected.json` (names, kinds, flags; verdicts are checked later in spec 05)
  - _Requirements: 2.2, 3.2, 6.1_

- [ ]* 12. (P1, needs owner approval) Zombie tests
  - `ZOMBIE_SKIPPED` and `ZOMBIE_EMPTY` Candidates of kind `test`, with unit tests
  - _Requirements: 9.1, 9.2_
