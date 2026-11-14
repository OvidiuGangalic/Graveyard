# Design Document: 07 API and Deploy

## Overview

```
Browser ──► Vercel (Next.js)  ──/api/* rewrite──►  Render (FastAPI, 1 uvicorn worker)
                                                     ├─ routes.py ── preflight (sync) ── Store
                                                     ├─ JobQueue (1 worker thread) ── pipeline.run ── Store
                                                     └─ Store: dict in memory + JSON files, 24h TTL
```

The browser never calls Render directly, so there is no CORS configuration and no backend URL in client code.

## Hosting decision (backend): Render

| | Render free web service | Fly.io | Cloud Run |
|---|---|---|---|
| Card needed | No | Yes (no standing free tier for new accounts) | Yes (billing account) |
| Long-lived single process with background work | Yes | Yes | Not by default: CPU is throttled outside requests, and instances are stateless and may multiply |
| Fits "in-memory cache, one worker" | Yes | Yes | Only with max-instances=1 and always-on CPU, which leaves the free tier |
| Cold start | Slow (tens of seconds after ~15 idle minutes) | Fast | Fast |
| Setup time | `render.yaml` + Dockerfile | `fly.toml` + CLI | gcloud + IAM + registry |

**Choice: Render.** It is the only one of the three that is free without a card and runs the design as written: one long-lived process holding the queue and cache. Its weakness is the cold start, handled three ways: a keep-warm ping every 10 minutes, a wake-up call from the landing page with a visible "waking the gravedigger" state, and share links that can re-run an analysis. The second weakness is CPU: limits in `config.py` are tuned on day 1 against the real instance.

**Fallback:** if the day-1 spike shows the sample analysis taking more than 10 s or a 500-file repo more than 120 s on Render, raise decision D10 with the owner (Cloud Run with a billing account is the alternative). Do not switch silently.

These tier facts are as understood when the spec was written; task 1 re-checks them against the providers' current pricing pages.

## Data Models (canonical)

Pydantic v2 models in `backend/graveyard/models.py`; mirrored by hand in `web/lib/types.ts`. JSON uses snake_case. Fields marked † are additions to the brief's model (assumption A1).

### DeadItem

| Field | Type | Notes |
|---|---|---|
| `id` | string | 12 hex chars, stable for a given repo and commit |
| `name` | string | Qualified name: `export_legacy_csv`, `Stock.recount`, `useMemo` |
| `kind` | `"function" \| "import" \| "test"` | `test` is P1 only |
| `language` | `"python" \| "typescript"` | JavaScript files report `typescript` |
| `file_path` | string | POSIX path relative to repo root |
| `start_line` | integer ≥ 1 | inclusive |
| `end_line` | integer ≥ `start_line` | inclusive |
| `last_commit` | object or null | `{ "hash": string(40), "date": ISO-8601 UTC, "author": string, "is_boundary"†: boolean }` |
| `age_days` | integer ≥ 0 or null | null when `last_commit` is null; a lower bound when `is_boundary` |
| `callers_found` | array | `[{ "file_path": string, "line": integer, "kind": "test_reference" \| "string_match" \| "dynamic_import" \| "reexport", "snippet": string }]`; empty if none; at most 20 |
| `test_coverage` | `"covered" \| "not_covered" \| "unknown"` | static: whether a test file mentions the name |
| `confidence` | `"high" \| "medium" \| "low"` | |
| `verdict` | `"bury" \| "revive" \| "unsure"` | |
| `verdict_reason` | string | one sentence, ≤ 240 chars |
| `code_snippet` | string | exact source lines, at most 200 lines |
| `snippet_truncated`† | boolean | true when the item is longer than 200 lines |
| `deletable_as_whole_lines`† | boolean | false for an import that shares its statement with live names; the UI offers no diff then |

### Analysis

| Field | Type | Notes |
|---|---|---|
| `id` | string | 12 URL-safe chars, or `"sample"` |
| `repo_url` | string | canonical URL, or `"sample://haunted-repo"` |
| `repo_name` | string | `"owner/repo"`, or `"graveyard/haunted-repo"` |
| `branch` | string | |
| `commit_analysed` | string | 40 hex chars |
| `status` | `"queued" \| "running" \| "done" \| "failed"` | |
| `created_at` | ISO-8601 UTC | |
| `total_files_scanned` | integer | live while running |
| `total_dead_items` | integer | 0 until done |
| `items_by_language` | `{ "python": int, "typescript": int }` | |
| `items_by_verdict` | `{ "bury": int, "revive": int, "unsure": int }` | |
| `error_message` | string or null | set only when `failed` |
| `error_code`† | string or null | machine-readable companion of `error_message` |
| `progress`† | `{ "phase": "queued" \| "cloning" \| "scanning" \| "python" \| "typescript" \| "history" \| "verdicts" \| "done", "files_discovered": int, "queue_position": int }` | drives the loading screen |
| `is_sample`† | boolean | |
| `expires_at`† | ISO-8601 UTC or null | null for the sample |
| `warnings`† | string[] | honest caveats shown above the grid |

## Endpoints

### POST /api/analyze

Request (one of):

```json
{ "repo_url": "https://github.com/example-org/example-repo" }
```
```json
{ "sample": true }
```

Response `202 Accepted` (new job):

```json
{
  "id": "k3Jx9aQ2mLp1",
  "repo_url": "https://github.com/example-org/example-repo",
  "repo_name": "example-org/example-repo",
  "branch": "main",
  "commit_analysed": "9f2c1e7a4b6d8035c1e2f3a4b5c6d7e8f9a0b1c2",
  "status": "queued",
  "created_at": "2026-12-01T10:15:30Z",
  "total_files_scanned": 0,
  "total_dead_items": 0,
  "items_by_language": { "python": 0, "typescript": 0 },
  "items_by_verdict": { "bury": 0, "revive": 0, "unsure": 0 },
  "error_message": null,
  "error_code": null,
  "progress": { "phase": "queued", "files_discovered": 0, "queue_position": 1 },
  "is_sample": false,
  "expires_at": "2026-12-02T10:15:30Z",
  "warnings": []
}
```

Response `200 OK`: same shape, for the sample or a de-duplicated existing analysis (status may already be `done`).

Errors:

| Status | `error.code` | When | Example message |
|---|---|---|---|
| 400 | `invalid_request` | bad JSON; both or neither field | "Send either a repo URL or sample: true." |
| 400 | `invalid_url` | spec 01 Requirement 1 | "That does not look like a GitHub repo URL. Try https://github.com/owner/repo." |
| 404 | `repo_not_found_or_private` | spec 01 Requirement 2 | "That repo is private or does not exist. Graveyard can only dig in public repos." |
| 413 | `repo_too_large` | spec 01 Requirement 3 | "This repo is 840 MB. Graveyard can dig up repos of up to 100 MB." |
| 413 | `invalid_request` | body over 2 KB | "Request too large." |
| 422 | `repo_empty` | repo has no commits | "This repo has no commits yet." |
| 429 | `rate_limited` | Requirement 2 | "Too many digs. Try again in 4 minutes." |
| 503 | `server_busy` | queue full | "The gravedigger is busy. Try again in half a minute." |
| 503 | `github_unavailable` | GitHub unreachable or throttling git | "GitHub is not answering right now. Try again shortly." |
| 503 | `warming_up` | sample not ready | "Still waking up. One moment." |

Error body:

```json
{ "error": { "code": "repo_too_large", "message": "This repo is 840 MB. Graveyard can dig up repos of up to 100 MB." } }
```

### GET /api/analysis/{id}

`200 OK` while running:

```json
{
  "id": "k3Jx9aQ2mLp1",
  "repo_url": "https://github.com/example-org/example-repo",
  "repo_name": "example-org/example-repo",
  "branch": "main",
  "commit_analysed": "9f2c1e7a4b6d8035c1e2f3a4b5c6d7e8f9a0b1c2",
  "status": "running",
  "created_at": "2026-12-01T10:15:30Z",
  "total_files_scanned": 212,
  "total_dead_items": 0,
  "items_by_language": { "python": 0, "typescript": 0 },
  "items_by_verdict": { "bury": 0, "revive": 0, "unsure": 0 },
  "error_message": null,
  "error_code": null,
  "progress": { "phase": "typescript", "files_discovered": 430, "queue_position": 0 },
  "is_sample": false,
  "expires_at": "2026-12-02T10:15:30Z",
  "warnings": []
}
```

`200 OK` when done: `status: "done"`, totals filled, for example `"total_files_scanned": 430, "total_dead_items": 37, "items_by_language": {"python": 21, "typescript": 16}, "items_by_verdict": {"bury": 24, "revive": 6, "unsure": 7}, "warnings": ["3 files skipped: too large or not parseable"]`.

`200 OK` when failed: `status: "failed", "error_code": "too_many_files", "error_message": "This repo has 4,210 source files. Graveyard can dig through up to 1,500."`

Failure codes that appear only on a failed Analysis: `clone_timeout`, `too_many_files`, `repo_too_large`, `github_unavailable`, `analysis_timeout`, `server_restarted`, `internal_error`.

Errors: `404 analysis_not_found` ("This graveyard has been filled in. Analyses are kept for 24 hours.").

### GET /api/analysis/{id}/items

`200 OK`:

```json
{
  "analysis_id": "sample",
  "total": 19,
  "returned": 19,
  "items": [
    {
      "id": "3f9a1c2e7b04",
      "name": "export_legacy_csv",
      "kind": "function",
      "language": "python",
      "file_path": "inventory/reports.py",
      "start_line": 42,
      "end_line": 58,
      "last_commit": {
        "hash": "1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4",
        "date": "2024-12-01T09:00:00Z",
        "author": "Morticia Graves",
        "is_boundary": false
      },
      "age_days": 730,
      "callers_found": [],
      "test_coverage": "not_covered",
      "confidence": "high",
      "verdict": "bury",
      "verdict_reason": "No references anywhere in this repo, no test mentions it, it has been untouched for 730 days, and its file has no dynamic lookups.",
      "code_snippet": "def export_legacy_csv(rows, path):\n    ...",
      "snippet_truncated": false,
      "deletable_as_whole_lines": true
    },
    {
      "id": "a81d44c09e2f",
      "name": "handle_refund",
      "kind": "function",
      "language": "python",
      "file_path": "inventory/plugins.py",
      "start_line": 12,
      "end_line": 20,
      "last_commit": { "hash": "7e6d5c4b3a2918070f6e5d4c3b2a19080f7e6d5c", "date": "2025-06-10T09:00:00Z", "author": "Edgar Poe", "is_boundary": false },
      "age_days": 539,
      "callers_found": [
        { "file_path": "inventory/plugins.py", "line": 31, "kind": "string_match", "snippet": "ACTIONS = [\"handle_refund\", \"handle_return\"]" }
      ],
      "test_coverage": "not_covered",
      "confidence": "low",
      "verdict": "revive",
      "verdict_reason": "Nothing calls it directly, but its name appears as a string at inventory/plugins.py:31, which suggests it is looked up by name at runtime.",
      "code_snippet": "def handle_refund(order):\n    ...",
      "snippet_truncated": false,
      "deletable_as_whole_lines": true
    }
  ]
}
```

(The values above illustrate the shape; real values come from the pipeline.)

Errors: `404 analysis_not_found`; `409 analysis_not_ready` ("Still digging. Check back in a moment."); `409 analysis_failed` (message = the Analysis's `error_message`).

### GET /api/analysis/{id}/export.md

Query: `revived=<id>,<id>` (optional), `download=1` (optional).

`200 OK`, `text/markdown; charset=utf-8`:

```markdown
# Graveyard cleanup plan: graveyard/haunted-repo

- Branch: `main` at `1b2c3d4`
- Analysed: 2026-12-01 10:15 UTC
- Files scanned: 24
- Dead items: 19 (bury: 14, unsure: 1, revive: 4)
- Lines that could be buried: 142

> Sample repo: commit history is scripted, so ages are illustrative
> "Tests" below means a test file mentions the name. Graveyard does not run tests.

## inventory/reports.py

- [ ] **BURY (high)** `export_legacy_csv` (function, lines 42–58), untouched 730 days, last touched by Morticia Graves
  - No references anywhere in this repo, no test mentions it, it has been untouched for 730 days, and its file has no dynamic lookups.
- [ ] **BURY (high)** `json` (import, line 1), untouched 730 days, last touched by Morticia Graves
  - It is never used in this file, it has been untouched for 730 days, and the file has no dynamic lookups.

## inventory/plugins.py

- **REVIVE (low)** `handle_refund` (function, lines 12–20), untouched 539 days, last touched by Edgar Poe
  - Nothing calls it directly, but its name appears as a string at inventory/plugins.py:31, which suggests it is looked up by name at runtime.

---
Generated by Graveyard. Static analysis only: check each item before deleting.
```

`bury` items get a task-list checkbox; `revive` and `unsure` items do not. Errors as for `/items`.

### GET /api/health

`200 OK`: `{ "status": "ok", "version": "9f2c1e7", "sample_ready": true, "queue_depth": 0 }`

## Components and Interfaces

| Module | Responsibility |
|---|---|
| `api/routes.py` | The five routes; no logic beyond mapping |
| `api/errors.py` | `ApiError(status, code, message)`; handlers that turn `ApiError`, `RequestValidationError`, `IngestError` and `Exception` into the Error envelope; the `IngestError` → status table |
| `api/ratelimit.py` | Sliding-window counter per IP in a dict; pruned on access |
| `store.py` | `Store.create/get/update/finish/fail/find_by_repo_commit/sweep`; a lock around the dict; JSON persistence |
| `jobs.py` (inside `api/`) | `JobQueue`: a `queue.Queue` and one daemon worker thread; `enqueue(analysis_id, preflight)`; `queue_position(id)` |
| `export.py` | `render_markdown(analysis, items, revived_ids) -> str`; pure |
| `main.py` | App factory; lifespan: clean clone dir, load Store, materialise samples, compute Sample analysis in the worker, start sweeper |

Limits are off by default (owner decision, 14 Nov 2026; spec 01 design, "Limits"). The `repo_too_large`, `too_many_files`, `clone_timeout`, `analysis_timeout` and `rate_limited` responses in this document show what is returned once the matching limit is set; their numbers are examples.

Constants: `MAX_CONCURRENT_JOBS = 1`, `MAX_QUEUE = 4`, `RATE_LIMIT_COUNT = None` (unset: no rate limit), `RATE_LIMIT_WINDOW_S = 600`, `TTL_S = 86,400`, `MAX_STORED = 200`, `MAX_BODY_BYTES = 2,048`.

## Deployment

### Backend (`backend/Dockerfile`, `render.yaml`)

- Base `python:3.12-slim`; `apt-get install -y --no-install-recommends git`; non-root user; `pip install .`; copy `samples/` into the image; `CMD uvicorn graveyard.main:app --host 0.0.0.0 --port $PORT --workers 1`.
- The Docker build context is the repo root (the image needs `backend/` and `samples/`); `.dockerignore` excludes `web/`, `.git`, `node_modules`.
- `render.yaml`: one `web` service, `runtime: docker`, `plan: free`, `healthCheckPath: /api/health`, `autoDeploy: true`, optional `GITHUB_TOKEN` declared with `sync: false`.
- Git identity for the sample materialiser is set per command (`-c user.name=... -c user.email=...`), not in global config.

### Frontend (Vercel)

- Project root directory `web/`. Environment variable `BACKEND_URL` = the Render service URL.
- `next.config.ts` rewrites `/api/:path*` → `${BACKEND_URL}/api/:path*`.
- All API calls from the browser are short (pre-flight ≤ ~15 s, everything else < 1 s), within the platform's proxy timeout. If pre-flight proves too slow through the proxy, move `ls-remote` into the job and report its failures through the failed-Analysis path (decision for the owner, not a silent change).

### Keep-warm (`.github/workflows/keep-warm.yml`)

`schedule: cron "*/10 * * * *"`, one `curl -fsS` to `/api/health` on the Render URL (called directly, not through Vercel). Enabled on 1 December; disabled after results are announced.

### CI (`.github/workflows/ci.yml`)

Backend job: install, `ruff check`, `ruff format --check`, unit tests, property tests, accuracy gate. Frontend job: `npm ci`, lint, typecheck, tests, `next build`.

## Error Handling

- Every exception path ends in the Error envelope (Requirement 11.1).
- A Job failure never takes down the worker thread: the worker loop catches everything, marks the Analysis failed and continues.
- Disk write failure when persisting an Analysis is logged; the in-memory copy still serves.
- On startup with a corrupt JSON file in the cache directory: the file is deleted and skipped.

## Correctness Properties

- **Property P11 (export is complete and exact).** For any generated list of DeadItems and any subset of revived ids: every item's name appears exactly once in the export, under the heading of its file; headings are in alphabetical order; the header's bury/unsure/revive counts equal the counts in the input after applying revived ids. **Validates: Requirements 5.2, 5.3, 5.4.**
- **Property P19 (export cannot be injected).** For any item whose name, author or path contains Markdown or HTML control characters, the rendered document contains no unescaped occurrence of them outside code spans. **Validates: Requirement 5.6.**
- **Property P20 (models round-trip).** For any generated Analysis and DeadItem, `model_validate_json(model_dump_json(x)) == x`. **Validates: Requirements 6.3, 7.3.**
- **Property P21 (rate limiter).** For any sequence of request timestamps from one IP, the number accepted within any 600-second window never exceeds 5. **Validates: Requirement 2.1.**

## Testing Strategy

- `backend/tests/api/` with FastAPI `TestClient` and ingestion faked at the `preflight`/`ingest_remote` boundary: every status code and error code in the tables above has a test.
- Store tests with an injected clock: expiry, sweep, reload after restart, `server_restarted` marking, eviction at 200.
- One end-to-end test: `POST sample` → `GET analysis` → `GET items` → `GET export.md`.
- Deployment smoke script `scripts/smoke.sh <base-url>` (curl only): health, sample loop, invalid URL, private repo. Run after every production deploy.
