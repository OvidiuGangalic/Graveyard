# Requirements Document: 02 Python Analyzer

## Introduction

The Python analyser reads every Python Source file in a `RepoSnapshot` with the stdlib `ast` module and returns `Candidate`s: functions and imports that have no direct production reference. It does not decide verdicts. It gathers evidence (weak references, flags, static test coverage) and hands that to the verdict engine (spec 05).

The analysis is **scope-aware where the code makes the target certain, and name-based everywhere else**. A reference is tied to one definition when imports, module-level bindings or `self` show which definition it means; two functions with the same name in different modules or classes are then separate items, and using one does not keep the other alive. When the target cannot be known without type inference (for example `obj.save()` on an arbitrary object), the reference keeps every function of that name alive, unless its arguments cannot fit a definition's signature. Any doubt resolves towards "still used".

Priority: P0 (Requirements 1–8), P1 (Requirement 9).

## Glossary

- **Analyser**: `backend/graveyard/analyzers/python/`.
- **Analysable function**: a `def` or `async def` that is a direct child of a module body or of a class body that is itself a direct child of a module body. Nested functions, lambdas, and functions inside `if`/`try` blocks are not analysable and are never reported.
- **Span**: the lines from the first decorator (or the `def` line when there is none) to the function's last line, inclusive.
- **Production file**: a Python Source file with `is_test = false`. **Test file**: `is_test = true`.
- **Occurrence**: a name found by rules PY-R1 to PY-R6 in `design.md`.
- **Resolved occurrence**: an Occurrence that rules PY-S1 to PY-S6 tie to specific definitions (possibly none in the repo). **Unresolved occurrence**: any other (PY-S7).
- **Direct reference** to a function: an Occurrence in a Production file, outside the function's own Span, that either resolves to that function, or is unresolved, has the function's name and is not excluded by the arity rule PY-A1.
- **Test reference**: the same, in a Test file.
- **Weak reference**: a string or text mention found by rules PY-W1 to PY-W2.
- **Exempt**: a function that is a framework entry point by rules PY-E1 to PY-E9; never reported.
- **Candidate**: an Analysable function that is not Exempt and has zero Direct references; or an import by Requirement 6.

## Requirements

### Requirement 1: Find analysable functions

**User Story:** As a developer, I want every top-level function and class method considered, so that dead code in classes is not missed.

#### Acceptance Criteria

1. THE Analyser SHALL collect every Analysable function in every Python Source file, recording name, qualified name (`Class.method` for methods), file path, Span, and whether it is a method.
2. THE Analyser SHALL NOT collect nested functions, lambdas, or functions defined under `if`, `try`, `with`, `for` or `while` at module or class level.
3. WHEN several Analysable functions in one scope share a name (for example `@overload` stubs, or `@property` with its setter), THE Analyser SHALL treat them as one definition whose Span is that of the last one, and SHALL report at most one Candidate for them. (Python has no overloading by parameter list: a second `def x` in the same scope replaces the first. Functions named `x` in different modules or classes are separate definitions; see Requirement 2.)
4. THE Analyser SHALL NOT collect functions from Test files as Candidates in P0.

### Requirement 2: Decide whether a function is referenced

**User Story:** As a developer, I want a function reported when nothing uses *that* function, even if another function elsewhere shares its name, so that the report is both trustworthy and complete.

#### Acceptance Criteria

1. THE Analyser SHALL build one repo-wide index of Occurrences across all Python Source files using rules PY-R1 to PY-R6, recording for each its file, line, form (bare name, attribute with its receiver, import), enclosing class if any, and call shape if it is the callee of a call.
2. WHEN an Analysable function has at least one Direct reference, THE Analyser SHALL NOT report it.
3. THE Analyser SHALL exclude from Direct references every occurrence inside the function's own Span (its definition, its docstring, and recursive calls).
4. THE Analyser SHALL resolve each Occurrence with rules PY-S1 to PY-S6, and a Resolved occurrence SHALL count as a Direct reference only to the definitions it resolves to: `apply_discount` in `pricing.py` and `apply_discount` in `pricing_v1.py` are separate, and `from inventory.pricing import apply_discount` keeps only the first alive.
5. WHEN an Analysable function has zero Direct references and one or more Test references, THE Analyser SHALL report it with `test_coverage = "covered"` and each Test reference listed as a caller of kind `test_reference`.
6. WHEN a Python Source file fails to parse, THE Analyser SHALL collect no definitions from it, SHALL still add every identifier-shaped token in it to the reference index as an Unresolved occurrence, SHALL count it in `files_skipped`, and SHALL continue.
7. WHEN an Occurrence is unresolved (PY-S7), THE Analyser SHALL count it as a reference to every Analysable function with that name, except as excluded by criterion 8.
8. WHEN an Unresolved occurrence is a call whose arguments a definition's signature cannot accept (rule PY-A1), THE Analyser SHALL NOT count it as a reference to that definition; IF the definition is reported as a result, THEN THE Analyser SHALL set flag `ARITY_MISMATCH` with the location of the first such call.
9. IF any precondition of a resolution rule is uncertain (star import, ambiguous module path, dynamic lookup in the file, module-level `__getattr__`, parse failure), THEN THE Analyser SHALL treat the Occurrence as unresolved.
10. THE Analyser SHALL report every function that pure name matching (every Occurrence unresolved, no arity rule) would report: resolution may only add Candidates, never remove one.

Judge check: in the sample graveyard, `export_legacy_csv` is a tombstone and `build_report` (which is called) is not. `apply_discount` in `inventory/pricing_v1.py` is a tombstone, while the `apply_discount` in `inventory/pricing.py` is not.

### Requirement 3: Never report framework entry points

**User Story:** As a developer, I want route handlers, CLI commands and other framework-called functions left alone, so that the report is not full of obvious false positives.

#### Acceptance Criteria

1. THE Analyser SHALL treat as Exempt any function matching one of the rules PY-E1 to PY-E9 in `design.md`, which cover: `main` and `__main__`; test functions and test infrastructure; Flask and FastAPI route handlers and lifecycle hooks; Django views, admin, signals and management commands; CLI entry points (`click`, `typer`, `argparse` dispatch via `[project.scripts]`, `setup.py`/`setup.cfg` `console_scripts`); every dunder method and module-level dunder function; abstract and overload stubs; Celery tasks and similar registered callables.
2. THE Analyser SHALL NOT report an Exempt function under any circumstances, whatever its references.
3. THE rule list in `design.md` SHALL be the complete and only source of exemptions; each rule SHALL have a unit test named after its rule ID.

### Requirement 4: Collect weak evidence for the verdict engine

**User Story:** As a developer, I want to see why something that looks dead might still be used, so that I can make the call myself.

#### Acceptance Criteria

1. WHEN a Candidate's name appears as a whole string literal, or as a whole identifier-shaped token inside a string literal, in any Python Source file, THE Analyser SHALL add a caller of kind `string_match` with file, line and the line's text, and set flag `STRING_MATCH`.
2. WHEN a Candidate's name appears as a whole word in any Text-reference file, THE Analyser SHALL add a caller of kind `string_match` and set flag `STRING_MATCH`.
3. WHEN a Candidate's name is listed in an `__all__` assignment in its module or its package `__init__.py`, THE Analyser SHALL set flag `IN_DUNDER_ALL` and add a caller of kind `reexport`.
4. WHEN a Candidate has a decorator that is neither an exempting decorator (PY-E rules) nor in the benign list (PY-F1), THE Analyser SHALL set flag `UNKNOWN_DECORATOR` and record the decorator's source text.
5. WHEN a Candidate is a method of a class that has at least one base class not defined in the repo (other than `object`), THE Analyser SHALL set flag `EXTERNAL_BASE_CLASS` and record the base's source text.
6. WHEN the file defining a Candidate contains any dynamic-lookup construct listed in PY-F3, THE Analyser SHALL set flag `DYNAMIC_PATTERN_IN_FILE`.
7. WHEN a Candidate is a method and any Python Source file in the repo calls `getattr` with a non-literal second argument, THE Analyser SHALL set flag `REPO_HAS_REFLECTION`.
8. THE Analyser SHALL cap the callers recorded per Candidate at 20, keeping the first 20 by (file path, line).

### Requirement 5: Static test coverage

**User Story:** As a developer, I want to know whether tests mention an item, so that I know whether deleting it will break the test suite.

#### Acceptance Criteria

1. WHEN at least one Test file references a Candidate function's name, THE Analyser SHALL set `test_coverage = "covered"`.
2. WHEN the repo has at least one Python Test file and none references the name, THE Analyser SHALL set `test_coverage = "not_covered"`.
3. WHEN the repo has no Python Test files, THE Analyser SHALL set `test_coverage = "unknown"`.
4. THE Analyser SHALL set `test_coverage = "unknown"` for every import Candidate.
5. THE Analyser SHALL NOT run tests or coverage tools.

### Requirement 6: Dead imports

**User Story:** As a developer, I want unused imports listed, so that I can remove them with confidence.

#### Acceptance Criteria

1. THE Analyser SHALL report an import binding as a Candidate of kind `import` WHEN the bound name has no occurrence in the same file by rules PY-R1 to PY-R6 other than the import statement itself.
2. THE Analyser SHALL treat names inside string annotations and `# type:` comments as occurrences.
3. THE Analyser SHALL NOT report imports that match any rule PY-I1 to PY-I7 in `design.md`: imports in `__init__.py`; names in the module's `__all__`; `from __future__` imports; star imports; imports on a line carrying `# noqa`; imports whose bound name is imported from this module by another module in the repo; `import a.b.c` forms where any dotted prefix is used.
4. WHEN an unused import is a plain `import module` of a module that is not in `sys.stdlib_module_names`, THE Analyser SHALL set flag `SIDE_EFFECT_IMPORT`.
5. WHEN an unused import sits inside a `try` block whose handlers catch `ImportError` or `ModuleNotFoundError`, or under an `if` statement, THE Analyser SHALL set flag `CONDITIONAL_IMPORT`.
6. THE Analyser SHALL name an import Candidate by its bound name, and set its line range to the whole import statement.
7. WHEN an import statement binds several names and not all are unused, THE Analyser SHALL set flag `PARTIAL_STATEMENT` on each unused one.

Judge check: in the sample graveyard, the tombstone `json` (import) points at `inventory/reports.py` line 1.

### Requirement 7: Robustness

**User Story:** As the operator, I want the analyser to survive any input, so that one odd file cannot fail an analysis.

#### Acceptance Criteria

1. THE Analyser SHALL NOT raise for any file content, including invalid syntax, Python 2 syntax, null bytes, and very large files.
2. THE Analyser SHALL be a pure function of the `RepoSnapshot`: no network, no subprocess, no clock, no global state; two runs on the same snapshot SHALL return equal results in the same order.
3. THE Analyser SHALL return Candidates sorted by (file path, start line, name).
4. THE Analyser SHALL call the progress callback after each file is parsed.
5. THE Analyser SHALL check the pipeline deadline between files and stop with `AnalysisTimeout` when it has passed.

### Requirement 8: Snippets

#### Acceptance Criteria

1. THE Analyser SHALL attach to each Candidate the exact source lines of its line range as `code_snippet`.
2. WHEN the range exceeds `SNIPPET_MAX_LINES` (200), THE Analyser SHALL keep the first 200 lines and set `snippet_truncated = true`.

### Requirement 9 (P1, do not start without owner approval): Zombie tests

**User Story:** As a developer, I want tests that no longer test anything flagged, so that the test suite stops lying about coverage.

#### Acceptance Criteria

1. THE Analyser SHALL report a test function as a Candidate of kind `test` WHEN it is decorated with an unconditional `pytest.mark.skip` or `unittest.skip`, or WHEN its body consists only of a docstring, `pass` or `...`.
2. THE Analyser SHALL set flag `ZOMBIE_SKIPPED` or `ZOMBIE_EMPTY` accordingly.

## Assumptions (flagged; see docs/open-decisions.md)

- A1. Owner decision (14 Nov 2026): matching is scope-aware (Requirement 2.4). Resolution uses imports, module-level bindings and `self`/class names only; there is no type inference, so `obj.method()` on an arbitrary object falls back to name matching plus the argument-count check (Requirement 2.8). A Candidate found only through the argument-count check is capped at `medium`. See D4.
- A2. An import of a function (`from m import f`) counts as a Direct reference to `f`, even if that import is itself unused. The unused import is reported; once the user removes it, the next run reports `f`.
- A3. "Dunder methods that are overrides" is implemented as "all dunder names are exempt", because every dunder is an implicit protocol hook.
- A4. Mentions in `.md`/`.rst`/`.txt` are ignored (docs are not evidence of use). Config and template mentions count. See D5.
- A5. Functions in Test files are not Candidates in P0; unused test helpers are out of scope.
- A6. `test_coverage` is static (name mentioned in a test file), not measured coverage. The UI labels it accordingly.
