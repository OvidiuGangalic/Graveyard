# Design Document: 02 Python Analyzer

## Overview

Two passes over the Python Source files, then a join.

```
pass 1 (per file):  parse ──► definitions.py  → FunctionDef records, ClassInfo, ImportBinding records
                          ──► references.py   → Occurrence records (name, file, line, kind)
                          ──► entrypoints.py  → exempt set, per-file flags
pass 2 (repo-wide): build ReferenceIndex {name → [Occurrence]}, ModuleIndex {dotted suffix → files}, ClassIndex {class name → bases, methods}
resolve:            each Occurrence → set of FunctionDefs, or "unresolved" (rules PY-S1..S7), then arity filter PY-A1
join:               for each FunctionDef: exempt? → drop. direct refs outside span? → drop. else Candidate + Evidence
                    for each ImportBinding: used in file / excluded? → drop. else Candidate + Evidence
```

Memory: ASTs are not kept after pass 1; only the records are. The reference index stores at most 50 occurrences per name (the join only needs "any" plus a few examples).

## Shared analyser contract (used by specs 02, 03, 04, 05)

Defined once in `backend/graveyard/models.py`:

```python
class Flag(StrEnum):
    # positive evidence of use → verdict revive
    STRING_MATCH = "string_match"
    IN_DUNDER_ALL = "in_dunder_all"
    LIBRARY_API = "library_api"              # TS only
    DYNAMIC_IMPORT = "dynamic_import"        # TS only
    # analysis is blind here → verdict unsure
    UNKNOWN_DECORATOR = "unknown_decorator"
    EXTERNAL_BASE_CLASS = "external_base_class"
    SCRIPT_GLOBAL = "script_global"          # TS only
    # caps confidence at medium
    EXPORTED = "exported"                    # TS only
    DYNAMIC_PATTERN_IN_FILE = "dynamic_pattern_in_file"
    REPO_HAS_REFLECTION = "repo_has_reflection"
    ARITY_MISMATCH = "arity_mismatch"        # dead only because same-named calls do not fit its signature
    SIDE_EFFECT_IMPORT = "side_effect_import"
    CONDITIONAL_IMPORT = "conditional_import"
    # informational
    PARTIAL_STATEMENT = "partial_statement"
    ZOMBIE_SKIPPED = "zombie_skipped"        # P1
    ZOMBIE_EMPTY = "zombie_empty"            # P1

@dataclass(frozen=True)
class Caller:
    file_path: str
    line: int
    kind: Literal["test_reference", "string_match", "dynamic_import", "reexport"]
    snippet: str            # the source line, stripped, max 200 chars

@dataclass(frozen=True)
class Candidate:
    name: str               # "recount", "json"
    qualified_name: str     # "Stock.recount"
    kind: Literal["function", "import", "test"]
    language: Literal["python", "typescript"]
    file_path: str
    start_line: int         # 1-based, inclusive
    end_line: int
    code_snippet: str
    snippet_truncated: bool
    callers: tuple[Caller, ...]
    test_coverage: Literal["covered", "not_covered", "unknown"]
    flags: frozenset[Flag]
    flag_details: Mapping[Flag, str]   # e.g. UNKNOWN_DECORATOR → "@registry.register"
```

Entry point: `analyse_python(snapshot: RepoSnapshot, progress: ProgressFn, deadline: float) -> AnalyserResult` where `AnalyserResult = (candidates, functions_defined, files_parsed, files_failed)`.

## Reference rules (what counts as an occurrence of a name)

| ID | AST construct | Name recorded |
|---|---|---|
| PY-R1 | `ast.Name` in any context except the `Store` target of the definition itself | `id` |
| PY-R2 | `ast.Attribute` | `attr` (so `obj.recount`, `module.func`, `self.helper` all count) |
| PY-R3 | `ast.ImportFrom` alias | `alias.name` (the imported name, before `as`) |
| PY-R4 | `ast.Import` alias | every dotted segment of `alias.name` |
| PY-R5 | keyword argument names and `ast.arg` names are **not** occurrences | – |
| PY-R6 | String annotations and `# type:` comments: parse the string with `ast.parse(mode="eval")`; on success apply PY-R1/R2 to it; on failure record every identifier-shaped token | names inside |

Fallback for unparseable files: every match of `[A-Za-z_][A-Za-z0-9_]*` in the file text is recorded as an occurrence (Requirement 2.6).

Each occurrence also records: its form (bare name, attribute plus the receiver expression when the receiver is a plain name, import alias), the enclosing top-level class if any, and, when it is the callee of an `ast.Call`, the call shape (number of positional arguments, keyword names, whether `*`/`**` unpacking is used).

## Resolution rules (which definition an occurrence means)

"Scope-aware" here means: use what the file itself states (imports, module-level bindings, `self`) to decide which `x` an occurrence of `x` refers to. There is no type inference. Rules are tried in order; `F` is the file containing the occurrence.

| ID | Occurrence | Resolves to |
|---|---|---|
| PY-S1 | Bare name `x`, and `F` binds `x` at module level with `def`, `class`, an assignment or a `global x` statement | `F`'s own module-level `x` only. |
| PY-S2 | Bare name `x`, and `F` binds `x` with `from M import x` or `from M import y as x`. The import alias itself (PY-R3) resolves the same way. | Module-level `y` (or `x`) in the file(s) `M` resolves to (see "Module resolution"). |
| PY-S3 | Attribute `m.x` where `m` is bound in `F` by `import a.m`, `import a.m as m` or `from a import m`, and that module resolves to repo file(s) | Module-level `x` in those files. |
| PY-S4 | `self.x` or `cls.x` inside a method of class `C`; `super().x` inside `C`; `C.x` where bare `C` resolves by PY-S1/S2 to a repo class | Method `x` of every class in `C`'s family: `C`, its ancestors and its descendants, linked by base-class name among repo classes. |
| PY-S5 | Bare name `x` directly in the body of class `C` (for example `total = property(_get_total)`) and `C` defines `x` | Method `x` of `C`. |
| PY-S6 | Bare name `x`, `F` has no module-level binding of `x`, no star import, and no PY-F3 dynamic pattern | No repo function: it is a local variable, a parameter or a builtin. |
| PY-S7 | Everything else: an attribute on any other receiver (`obj.x`, `a.b().x`, `items[0].x`); a bare name in a file with a star import or a PY-F3 pattern; every token of a file that failed to parse; a name inside a string annotation that no rule above resolves | **Unresolved.** A bare name refers to every module-level function named `x`; an attribute refers to every method and every module-level function named `x`. Subject to PY-A1. |

When `F` binds `x` in more than one way (a `def` and an import, two imports), the occurrence resolves to the union of the targets.

### Module resolution

A relative import is first made absolute against `F`'s package directory. A dotted path `a.b.c` then resolves to every Python Source file whose path without extension ends with the segments `a/b/c` or `a/b/c/__init__`.

- No match: the module is outside the repo; the occurrence refers to no repo function.
- Several matches: it refers to all of them.
- **Following re-exports.** If the target module binds the name by import instead of defining it (`pkg/__init__.py` with `from .mod import x`), follow that import, at most 5 steps. If the target module has no binding of the name but has star imports, follow each star import. If the chain ends without a definition, or any module on the chain has a module-level `__getattr__`, the occurrence is unresolved (PY-S7).
- `from a import m` where `a/m.py` exists **and** `a/__init__.py` binds `m`: both readings apply (union).

### Arity rule

| ID | Rule |
|---|---|
| PY-A1 | Applies only to unresolved (PY-S7) occurrences that are the callee of a call with no `*`/`**` unpacking. Let `p` be the number of positional arguments and `K` the keyword names. The call is **incompatible** with definition `d` when `d` has no decorator outside the PY-F1 benign list (a wrapper may change the signature) and, after dropping the first parameter of a method that is not a `staticmethod`, any of: `p` exceeds `d`'s positional parameters and `d` has no `*args`; a name in `K` is not a parameter of `d` and `d` has no `**kwargs`; a parameter of `d` without a default is supplied neither by position nor by keyword. An incompatible call is not a reference to `d`. |

Rationale: such a call would raise `TypeError` if it reached `d`, so it must be meant for another function of the same name. Occurrences that are not calls (`callback=obj.x`) always count. Example: with `Stock.adjust(self, sku, delta)` and `StockV1.adjust(self, sku)`, the call `stock.adjust(sku, 5)` keeps only `Stock.adjust` alive.

### Direct and Test references

An occurrence is a **Direct reference** to function `f` if its file is a Production file, it is not inside `f`'s Span, and it either resolves to `f` or is unresolved, carries `f`'s name and is not excluded by PY-A1. It is a **Test reference** under the same rule when its file is a Test file.

Consequences to state in the README: same-named functions in different modules or classes are judged separately when imports or `self` identify the target. Method calls on arbitrary objects are matched by name and argument count only, so two classes with a method of the same name and a compatible signature still keep each other alive.

`resolve_all_unresolved=True` (a test-only switch on the join) treats every occurrence as PY-S7 and disables PY-A1. It exists for Property P25.

## Weak-reference rules

| ID | Where | Match |
|---|---|---|
| PY-W1 | `ast.Constant` with `str` value in any Python Source file, excluding docstrings and excluding strings inside the Candidate's own Span | the string equals the name, or the name appears in it as a whole identifier token (`(?<![A-Za-z0-9_])name(?![A-Za-z0-9_])`) |
| PY-W2 | Text-reference files (listed by the walker) | same whole-token regex |

Names of 3 characters or fewer are not searched in Text-reference files (too noisy) and get flag `STRING_MATCH` only from PY-W1.

## Exemption rules (framework entry points: never reported)

| ID | Rule |
|---|---|
| PY-E1 | Module-level function named `main`; any function in a file named `__main__.py`. |
| PY-E2 | Any name that starts and ends with double underscores (`__init__`, `__repr__`, `__getattr__`, `__enter__`, ...), at module or class level. |
| PY-E3 | **Routes and app hooks.** A decorator whose final attribute name is one of: `route`, `get`, `post`, `put`, `patch`, `delete`, `head`, `options`, `trace`, `websocket`, `api_route`, `on_event`, `middleware`, `exception_handler`, `errorhandler`, `before_request`, `after_request`, `teardown_request`, `before_first_request`, `teardown_appcontext`, `context_processor`, `template_filter`, `template_global`, `url_value_preprocessor`, `shell_context_processor`, `cli`, `lifespan`, `dependency`, `validator`, `field_validator`, `model_validator`, `root_validator`, `field_serializer`, `model_serializer`, `computed_field`. Applies to `@x.name` and `@x.name(...)`. |
| PY-E4 | **Tests and test infrastructure.** Any function in a Test file. Outside Test files: functions named `test_*`; methods of a class named `Test*` or with a base whose name ends in `TestCase`; `setUp`, `tearDown`, `setUpClass`, `tearDownClass`, `setUpModule`, `tearDownModule`, `setup_method`, `teardown_method`, `setup_class`, `teardown_class`, `setup_function`, `teardown_function`; any function with a decorator ending in `fixture`; functions named `pytest_*`. |
| PY-E5 | **Django.** Module-level function whose first parameter is named `request` in a file named `views.py`, or in any file under a directory named `views`; any method of a class with a base whose name ends in `View`, `ViewSet`, `Mixin`, `ModelAdmin`, `Serializer`, `Form`, `Model`, `Middleware`, `AppConfig`, `BaseCommand`, `Migration`, `TestCase`; any decorator ending in `receiver`, `register`-on-`admin` (`@admin.register`), `action`, `api_view`, `login_required`, `permission_required`, `csrf_exempt`, `require_http_methods`, `require_GET`, `require_POST`; any function in a file under `management/commands/`; any function in `urls.py`, `admin.py`, `apps.py`, `settings.py`, `wsgi.py`, `asgi.py`, `manage.py`, `conftest.py`. |
| PY-E6 | **CLI.** A decorator whose final attribute name is `command`, `group`, `callback`, `argument`, `option` (click, typer); any function named as `module:function` in `pyproject.toml` `[project.scripts]`, `[project.gui-scripts]`, `[project.entry-points.*]`, `[tool.poetry.scripts]`, or in a `console_scripts`/`gui_scripts` string in `setup.py` or `setup.cfg`. The module part must match the function's file by dotted-path suffix. |
| PY-E7 | **Stubs.** A decorator ending in `abstractmethod`, `overload`; a function whose body is only `...`, `pass`, a docstring, or `raise NotImplementedError` (interface stub: nothing to bury). |
| PY-E8 | **Task queues and schedulers.** A decorator whose final attribute name is `task`, `shared_task`, `periodic_task`, `job`, `scheduled_job`, `listens_for`, `event`, `hookimpl`, `hookspec`, `tool`, `resource`, `prompt`. |
| PY-E9 | **Protocol method names** on any class: `run` on a class with a base ending in `Thread` or `Process`; methods named `visit_*`, `generic_visit`, `leave_*`, `do_*`, `handle`, `handle_*` on a class with any base class. |

PY-E5's Django list is name-based and broad on purpose. Being wrong here means a missed dead function, not a false "bury".

## Flag rules

| ID | Flag | Rule |
|---|---|---|
| PY-F1 | `UNKNOWN_DECORATOR` | The function has at least one decorator, none exempts it, and at least one is **not** in the benign list: `staticmethod`, `classmethod`, `property`, `*.setter`, `*.getter`, `*.deleter`, `cached_property`, `lru_cache`, `cache`, `wraps`, `contextmanager`, `asynccontextmanager`, `singledispatch`, `singledispatchmethod`, `total_ordering`, `final`, `override`, `deprecated`, `no_type_check`, `typing.*`, `functools.*`, `contextlib.*`, `dataclass`. Matching is on the final attribute name (and on the module prefix for the starred entries). |
| PY-F2 | `EXTERNAL_BASE_CLASS` | Method of a class with a base expression whose final name is not `object`, not a class defined in any Python Source file of the repo, and not `Generic`/`Protocol`/`ABC`/`NamedTuple`/`TypedDict`/`Enum`/`IntEnum`/`StrEnum`/`Exception`/`BaseException`/`dict`/`list`/`set`/`tuple`/`str`/`int`. |
| PY-F3 | `DYNAMIC_PATTERN_IN_FILE` | The defining file contains any of: a call to `getattr`/`setattr`/`hasattr` with a non-literal name argument; `globals()`; `locals()`; `vars()`; `eval(`; `exec(`; `__import__(`; `importlib.import_module(`; a module-level `__getattr__`; `sys.modules[`. |
| PY-F4 | `REPO_HAS_REFLECTION` | Candidate is a method, and any Python Source file calls `getattr` with a non-literal second argument. |
| PY-F5 | `IN_DUNDER_ALL` | Name is a string element of a list/tuple assigned (or `+=`) to `__all__` in the defining module or in the `__init__.py` of the same directory. |
| PY-F6 | `STRING_MATCH` | Any PY-W1 or PY-W2 hit. |
| PY-F7 | `ARITY_MISMATCH` | The Candidate has no Direct reference, and at least one unresolved call with its name in a Production file was excluded by PY-A1. Detail: `path:line` of the first such call. |

## Import rules

An **ImportBinding** is one name bound by one alias of an `import` or `from ... import` statement at module level (including inside module-level `try` and `if`). Imports inside functions are not analysed. The bound name is `alias.asname`, else the first dotted segment for `import a.b`, else `alias.name`.

Used: the bound name has at least one occurrence (PY-R1, PY-R2 base name, PY-R6) in the same file, excluding the import statement.

Never reported:

| ID | Rule |
|---|---|
| PY-I1 | The file is `__init__.py`. |
| PY-I2 | The bound name is in the module's `__all__`. |
| PY-I3 | `from __future__ import ...`. |
| PY-I4 | Star imports. |
| PY-I5 | The statement's first or last physical line contains `# noqa` (with or without a code) or `# type: ignore`. |
| PY-I6 | Another Python Source file has `from <M> import <name>` where `<M>`'s last dotted segment equals this file's module name (re-export through this module). |
| PY-I7 | The file failed to parse. |

Import flags: `SIDE_EFFECT_IMPORT` (Requirement 6.4), `CONDITIONAL_IMPORT` (6.5), `PARTIAL_STATEMENT` (6.7), plus `DYNAMIC_PATTERN_IN_FILE` when PY-F3 holds for the file.

## Error Handling

- `SyntaxError`, `ValueError` (null bytes), `RecursionError` and `MemoryError` from `ast.parse` are caught per file → file counted as failed, fallback tokenisation applied.
- `tomllib.TOMLDecodeError` when reading `pyproject.toml` → PY-E6 script lookup yields nothing, warning recorded.
- Any other exception inside one file's pass is caught, logged with the file path, and treated like a parse failure. The analyser as a whole never raises except `AnalysisTimeout`.

## Correctness Properties

Generators live in `backend/tests/property/strategies.py`. `python_repo()` builds a small repo from templates: 1–5 modules, 1–8 functions each (names unique by default, with an option to repeat a name across modules), and a random call graph expressed as `from m import f` plus a call. It is written with plain Hypothesis strategies; no extra dependency.

- **Property P1 (never crashes).** For any text (Hypothesis `text()` and `binary()` decoded with replacement) placed in a `.py` file, `analyse_python` returns without raising. **Validates: Requirement 7.1.**
- **Property P2 (bounded and well-formed).** For any generated repo, the number of function Candidates is ≤ `functions_defined`; every Candidate has `1 ≤ start_line ≤ end_line ≤` the file's line count; `code_snippet` equals those lines. **Validates: Requirements 1.1, 8.1.**
- **Property P3 (a caller flips the result).** For any generated repo with an uncalled, non-exempt function `f` in module `m`: `f` is reported. Adding `from m import f` and `f()` to another production module makes `f` unreported. Removing both again makes `f` reported. **Validates: Requirements 2.2, 2.4.**
- **Property P24 (same name, different module).** For any generated repo in which two modules each define a function `f`, and a third module imports and calls exactly one of them: exactly the other one is reported. Switching the import to the other module switches the result. **Validates: Requirement 2.4.**
- **Property P25 (resolution only adds).** For any generated repo, every function reported with `resolve_all_unresolved=True` is also reported by the normal analysis. **Validates: Requirements 2.9, 2.10.**
- **Property P26 (arity never hides a compatible call).** For any generated signature and any generated call that Python would accept for it (checked with `inspect.signature(...).bind` on a stub built from the same parameter list), PY-A1 does not mark the call incompatible. **Validates: Requirement 2.8.**
- **Property P5 (adding files never kills).** For any generated repo `R` and any extra generated Python file `x`, every function Candidate of `R ∪ {x}` located in `R`'s files is also a Candidate of `R`. **Validates: Requirement 2.1.**
- **Property P6 (exempt names are never reported).** For any generated function given a name or decorator drawn from the PY-E tables, it is not reported, whatever the call graph. **Validates: Requirement 3.2.**
- **Property P13 (using an import revives it).** For any generated module with an unused `from m import n`, `n` is reported; appending a statement that reads `n` makes it unreported. **Validates: Requirement 6.1.**
- **Property P4a (deterministic).** Shuffling the order of `source_files` in the snapshot does not change the returned list. **Validates: Requirements 7.2, 7.3.**

## Testing Strategy

- One unit test per rule ID, named `test_<RULE_ID>_<what>`. Each test is a tiny inline repo written to `tmp_path`.
- Regression corpus: `backend/tests/unit/analyzers/python/cases/*.py`, each with a header comment `# expect: dead=<names> live=<names>`; one parametrised test reads them. New false positives found in the real-repo sweep are added here first, then fixed.
- The accuracy gate (spec 05, task 7) is the acceptance test for this spec.
