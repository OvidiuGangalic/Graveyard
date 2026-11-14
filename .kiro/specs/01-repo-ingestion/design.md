# Design Document: 01 Repo Ingestion

## Overview

Ingestion has a synchronous part and an asynchronous part.

- **Pre-flight (synchronous, inside `POST /api/analyze`, at most ~15 s):** validate URL → `git ls-remote` → GitHub API size check. Failures here return an HTTP error immediately, so the landing page can show them inline.
- **Clone and walk (asynchronous, inside the pipeline job):** shallow clone → disk check → walk → `RepoSnapshot`. Failures here set the analysis to `failed` with an `error_code`.

```
raw input ──► url.parse_repo_url ──► clone.ls_remote ──► github.fetch_repo_size ──► [job queued]
                 │ invalid_url          │ repo_not_found_or_private   │ repo_too_large
                 ▼                      ▼ repo_empty / github_unavailable
[job] clone.shallow_clone ──► walker.walk ──► RepoSnapshot ──► analysers (specs 02, 03)
          │ clone_timeout / repo_too_large      │ too_many_files
```

## Components and Interfaces

All in `backend/graveyard/ingestion/`. Signatures are the contract; bodies are not specified here.

| Module | Function | Notes |
|---|---|---|
| `url.py` | `parse_repo_url(raw: str) -> RepoRef` | Pure. Raises `IngestError("invalid_url")`. |
| `clone.py` | `ls_remote(ref: RepoRef) -> RemoteHead` | Returns `branch`, `commit`. 10 s timeout. |
| `github.py` | `fetch_repo_size_kb(ref: RepoRef) -> int \| None` | `None` when the API is unavailable or rate limited. One request. |
| `clone.py` | `shallow_clone(ref: RepoRef, branch: str, dest: Path) -> None` | Depth from `config.CLONE_DEPTH`. |
| `walker.py` | `walk(root: Path) -> WalkResult` | Pure function of the file tree. |
| `samples.py` | `materialise_samples(data_dir: Path) -> None` | Called once at startup; idempotent. |
| `samples.py` | `sample_snapshot(name: Literal["haunted","living"]) -> RepoSnapshot` | |
| `__init__.py` | `preflight(raw_url) -> PreflightResult`, `ingest_remote(preflight, progress) -> RepoSnapshot`, `ingest_local(path) -> RepoSnapshot` | The only entry points other packages call. |

## Data Models

Internal types (frozen dataclasses in `backend/graveyard/models.py`):

```python
@dataclass(frozen=True)
class RepoRef:
    owner: str
    repo: str
    # canonical_url  -> "https://github.com/{owner}/{repo}"
    # clone_url      -> "https://github.com/{owner}/{repo}.git"
    # repo_name      -> "{owner}/{repo}"

@dataclass(frozen=True)
class SourceFile:
    path: str            # POSIX-style, relative to repo root
    language: Literal["python", "typescript"]
    size_bytes: int
    is_test: bool

@dataclass(frozen=True)
class RepoSnapshot:
    root: Path
    repo_url: str        # canonical URL, or "sample://haunted-repo"
    repo_name: str
    branch: str
    commit: str          # 40-hex, or "" when ingest_local has no .git
    is_sample: bool
    has_git: bool
    history_depth: int | None      # 500 for clones, None for full history
    source_files: tuple[SourceFile, ...]     # sorted by path
    text_files: tuple[str, ...]              # sorted
    files_skipped: int
    warnings: tuple[str, ...]
```

### Test-file rules (`is_test`)

Python: basename matches `test_*.py` or `*_test.py`, or is `conftest.py`, or any path segment is `tests` or `test`.

TypeScript/JavaScript: basename matches `*.test.*` or `*.spec.*`, or any path segment is `__tests__`, `__mocks__`, `e2e`, `cypress`, `tests` or `test`.

### Limits (`config.py`)

Owner decision (14 Nov 2026): no repo-size, file-count, time or item limits for now. Those constants are typed `int | None` and default to `None`, which disables the check. The code paths and error states exist and are tested with explicit values.

| Constant | Default | Enforced in |
|---|---|---|
| `MAX_URL_LENGTH` | 300 | `url.py` |
| `LS_REMOTE_TIMEOUT_S` | 10 | `clone.py` |
| `GITHUB_API_TIMEOUT_S` | 5 | `github.py` |
| `MAX_REPO_SIZE_KB` | unset (no limit) | `github.py` |
| `CLONE_DEPTH` | 500 | `clone.py` |
| `CLONE_TIMEOUT_S` | unset (no limit) | `clone.py` |
| `MAX_CLONE_DISK_MB` | unset (no limit) | `clone.py` |
| `MAX_SOURCE_FILES` | unset (no limit) | `walker.py` |
| `MAX_FILE_BYTES` | unset (no limit) | `walker.py` |
| `MAX_TEXT_FILE_BYTES` | 1,048,576 (text-reference scan only; larger files are not searched for name mentions) | `walker.py` |

Also unset by default: `ANALYSIS_TIMEOUT_S` and `MAX_ITEMS` (spec 05), `RATE_LIMIT_COUNT` (spec 07). Each can also be set through an environment variable of the same name prefixed `GRAVEYARD_`, so a limit can be switched on in the Render dashboard without a deploy.

## Sample repos

### Layout

```
samples/haunted-repo/
  history.json         # scripted commits
  expected.json        # ground truth
  README.md            # explains that the dead code is deliberate
  pyproject.toml       # [project.scripts] inventory = "inventory.cli:main"
  inventory/           # Python package
  tests/               # Python tests
  web/                 # private app package ("private": true)
  packages/sdk/        # library package (has "main", not private)
samples/living-repo/
  (same shape; every function is live or legitimately ambiguous)
```

### `history.json`

```json
{
  "commits": [
    { "days_ago": 730, "author": "Morticia Graves", "message": "Initial inventory service", "files": ["pyproject.toml", "inventory/__init__.py", "inventory/reports.py"] },
    { "days_ago": 20,  "author": "Edgar Poe",       "message": "Add rounding helper",       "files": ["inventory/pricing.py"] }
  ]
}
```

A file listed in several commits is committed as its final content split at marker comments: a line `# graveyard:commit N` (Python) or `// graveyard:commit N` (TS) means "the lines below, until the next marker, first appear in commit N". The materialiser strips the markers. This lets one file contain both a 700-day-old function and a 20-day-old one, which the blame tests need. Every file must appear in at least one commit; the materialiser fails loudly otherwise.

### `expected.json`

```json
{
  "items": [
    { "name": "export_legacy_csv", "kind": "function", "language": "python",
      "file_path": "inventory/reports.py", "verdict": "bury", "confidence": "high" }
  ],
  "forbidden": { "verdicts": [], "confidences": [] }
}
```

The gate (spec 05, task 7) checks an **exact** match: every listed item is reported with that verdict and confidence, and no unlisted item is reported. For the living repo, `forbidden` is `{"verdicts": ["bury"], "confidences": ["high"]}`.

### Haunted repo ground truth (minimum set)

| # | Item | File | Why | Verdict / confidence |
|---|---|---|---|---|
| 1 | `export_legacy_csv` (function) | `inventory/reports.py` | no references, 730 d old | bury / high |
| 2 | `Stock.recount` (method) | `inventory/models.py` | no references, 600 d old, class has no bases | bury / high |
| 3 | `apply_seasonal_discount` (function) | `inventory/pricing.py` | referenced only in `tests/test_pricing.py` | bury / medium |
| 4 | `round_half_up_v2` (function) | `inventory/pricing.py` | no references, 20 d old | bury / medium |
| 5 | `handle_refund` (function) | `inventory/plugins.py` | name appears as a string in a dispatch table, resolved with `globals()[action]` (not `getattr`, which would set `REPO_HAS_REFLECTION` and cap item 2 at medium) | revive / low |
| 6 | `old_webhook` (function) | `inventory/api.py` | unknown decorator `@registry.register` | unsure / low |
| 7 | `import json` (import) | `inventory/reports.py` | stdlib, unused, 730 d old | bury / high |
| 8 | `from typing import Optional` (import) | `inventory/models.py` | unused, 600 d old | bury / high |
| 9 | `import inventory.signals` (import) | `inventory/api.py` | unused, non-stdlib plain import (possible side effect) | bury / medium |
| 10 | `padLeftLegacy` (function) | `web/src/utils/format.ts` | not exported, no references in file, 500 d old | bury / high |
| 11 | `formatCurrencyOld` (function) | `web/src/utils/format.ts` | exported from private app, no importers | bury / medium |
| 12 | `fetchLegacyUsers` (function) | `web/src/lib/api.ts` | referenced only in `api.test.ts` | bury / medium |
| 13 | `OldBanner` (function) | `web/src/components/OldBanner.tsx` | default export, only reached through `const LazyPromo = lazy(() => import('./OldBanner'))`; the name `OldBanner` appears nowhere else | revive / low |
| 14 | `createLegacyClient` (function) | `packages/sdk/src/index.ts` | exported from a library package | revive / low |
| 15 | `useMemo` (import) | `web/src/components/Cart.tsx` | unused, 500 d old | bury / high |
| 16 | `User` type import (import) | `web/src/lib/api.ts` | unused, 20 d old | bury / medium |
| 17 | `apply_discount` (function) | `inventory/pricing_v1.py` | same name as the live `apply_discount` in `inventory/pricing.py`, which `inventory/api.py` imports and calls; nothing imports the `pricing_v1` one; 730 d old (scope-aware matching, PY-S2) | bury / high |
| 18 | `StockV1.adjust` (method) | `inventory/stock_v1.py` | signature `adjust(self, sku)`; every `.adjust(...)` call in the repo passes two arguments and fits `Stock.adjust(self, sku, delta)`; class has no bases; 600 d old (`ARITY_MISMATCH`, PY-A1) | bury / medium |
| 19 | `formatDate` (function) | `web/src/utils/dates-v1.ts` | exported; `web/src/utils/dates.ts` also exports a `formatDate`, and every import of that name uses `./dates` (TS-S2) | bury / medium |

The haunted repo also contains live controls that must not be reported: `main`, a FastAPI route, a used helper, `__repr__`, a used React component, a Next.js `page.tsx` default export.

### Living repo contents (each must NOT be reported as bury or high)

Python: Flask and FastAPI route handlers; a Django function view in `views.py`; a class-based view; a `click` command; a function named in `[project.scripts]`; `main` and an `if __name__ == "__main__"` block; names listed in `__all__`; a function reached through `getattr(module, name)`; a method overriding an external base class (`ast.NodeVisitor.visit_Name`); pytest fixtures and `conftest.py` hooks; dunder methods; a `@property`; two modules that each define `normalise`, both imported and called; a function reached only through a package `__init__.py` re-export; a function reached only through `from helpers import *`; a method `adjust(self, sku, delta=0)` called as `obj.adjust(sku)` (default argument, arity-compatible); an import used only inside a string annotation under `TYPE_CHECKING`; `__init__.py` re-exports; an import inside `try/except ImportError`; a recursive function that is also called from elsewhere.

TypeScript: Next.js `page.tsx`, `layout.tsx`, `route.ts` (`GET`, `POST`), `middleware.ts`; a component used only in JSX; a default export imported under a different local name; a namespace import (`import * as utils`) with `utils.fn()` usage; a `require()` usage; a barrel `index.ts` using `export * from`; two files that each export `format`, both imported; an export imported only through the alias `@/lib/...`; a method with an optional parameter called with fewer arguments; a function used only as a callback argument; a type-only import used in a type position; `React` default import in a `.tsx` file; a CommonJS `module.exports = { fn }`.

## Error Handling

`IngestError(code, message)` is the only exception type ingestion raises on purpose. Codes and where they surface:

| Code | Raised by | Surfaces as |
|---|---|---|
| `invalid_url` | `parse_repo_url` | HTTP 400 from `POST /api/analyze` |
| `repo_not_found_or_private` | `ls_remote` | HTTP 404 |
| `repo_empty` | `ls_remote` | HTTP 422 |
| `github_unavailable` | `ls_remote`, `shallow_clone` | HTTP 503 (pre-flight) or `failed` analysis |
| `repo_too_large` | `fetch_repo_size_kb`, `shallow_clone` | HTTP 413 (pre-flight) or `failed` analysis |
| `clone_timeout` | `shallow_clone` | `failed` analysis |
| `too_many_files` | `walk` | `failed` analysis |

Messages are written for end users, contain the relevant numbers, and never contain filesystem paths or stderr from git. Raw git stderr is logged server-side only.

## Correctness Properties

- **Property P10 (URL normalisation is idempotent).** For any string `s`, if `parse_repo_url(s)` succeeds with ref `r`, then `parse_repo_url(r.canonical_url) == r`; and for any generated valid `(owner, repo)` and any accepted wrapper form, parsing yields exactly that owner and repo. **Validates: Requirements 1.1, 1.4, 1.6.**
- **Property P10b (foreign hosts are rejected).** For any generated host other than `github.com`/`www.github.com`, parsing fails with `invalid_url`. **Validates: Requirement 1.3.**
- **Property P14 (walker containment).** For any generated file tree (including symlinks pointing outside the root), every path in `WalkResult` resolves inside the root and none has an excluded directory segment. **Validates: Requirements 5.1, 5.2.**

## Testing Strategy

- Unit: table-driven tests for `parse_repo_url` (20+ accepted and rejected forms); walker tests on `tmp_path` trees; `ls_remote` and `shallow_clone` tested against a local bare repo created in the test (`file://` URL), so no test needs the network.
- GitHub API client tested with `httpx.MockTransport`: 200 small, 200 too large, 403 rate-limited, timeout.
- Sample materialiser: test that `git log` in the materialised repo has one commit per `history.json` entry and that `git blame` attributes marker-split regions to the right commits.
- One opt-in network test (`-m network`, not in CI) clones a small public repo.
