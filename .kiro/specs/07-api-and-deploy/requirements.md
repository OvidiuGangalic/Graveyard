# Requirements Document: 07 API and Deploy

## Introduction

This spec covers the HTTP API between the Next.js frontend and the FastAPI backend, the job queue and 24-hour cache behind it, the Markdown export, and deployment to Vercel (frontend) and Render (backend). `design.md` holds the canonical data model and every endpoint with examples; the frontend's types mirror it field for field.

Priority: P0.

## Glossary

- **API**: the FastAPI application in `backend/graveyard/`.
- **Store**: the in-memory and on-disk cache of analyses (`store.py`).
- **Job**: one run of the pipeline for one Analysis.
- **Sample analysis**: the Analysis of the Haunted repo, with the fixed id `sample`.
- **Error envelope**: `{"error": {"code": "<snake_case>", "message": "<sentence for users>"}}`.

## Requirements

### Requirement 1: Start an analysis

**User Story:** As a developer, I want to submit a repo and get an id straight away, so that I can watch progress and share the link.

#### Acceptance Criteria

1. WHEN `POST /api/analyze` receives `{"repo_url": "<string>"}`, THE API SHALL run the ingestion pre-flight (spec 01) and, on success, create an Analysis with status `queued`, enqueue a Job and respond `202` with the Analysis.
2. WHEN `POST /api/analyze` receives `{"sample": true}`, THE API SHALL respond `200` with the Sample analysis.
3. IF the body has both `repo_url` and `sample: true`, neither, or is not valid JSON, THEN THE API SHALL respond `400` with code `invalid_request`.
4. WHEN an Analysis for the same Canonical URL and the same HEAD commit exists in the Store and is not `failed`, THE API SHALL respond `200` with that Analysis and SHALL NOT enqueue a Job.
5. IF pre-flight fails, THEN THE API SHALL respond with the status and code mapped in `design.md` and SHALL NOT create an Analysis.
6. IF the queue already holds `MAX_QUEUE` (4) waiting Jobs, THEN THE API SHALL respond `503` with code `server_busy` and a `Retry-After: 30` header.

### Requirement 2: Rate limiting

**User Story:** As the operator, I want one visitor unable to monopolise a free-tier server.

#### Acceptance Criteria

1. WHERE `RATE_LIMIT_COUNT` is set (default: unset, no rate limit), THE API SHALL allow each client IP at most `RATE_LIMIT_COUNT` accepted `POST /api/analyze` requests with a `repo_url` per rolling 10 minutes.
2. IF the limit is exceeded, THEN THE API SHALL respond `429` with code `rate_limited`, a `Retry-After` header in seconds, and a message stating how long to wait.
3. THE API SHALL NOT count sample requests, de-duplicated requests (Requirement 1.4), or requests rejected by pre-flight against the limit.
4. THE API SHALL take the client IP from the first address in `X-Forwarded-For` when present, otherwise from the socket.

Judge check: none; the limit is off by default. The limiter is tested with an explicit count, and the error screen is verified in the frontend with a mocked 429.

### Requirement 3: Read an analysis

**User Story:** As a developer, I want to poll one endpoint for status and progress, and open a shared link later.

#### Acceptance Criteria

1. WHEN `GET /api/analysis/{id}` is called for a stored Analysis, THE API SHALL respond `200` with the Analysis, including live `progress` while `queued` or `running`.
2. IF the id is unknown or expired, THEN THE API SHALL respond `404` with code `analysis_not_found`.
3. THE API SHALL respond to `GET /api/analysis/{id}` within 200 ms regardless of running Jobs (it reads the Store only).
4. WHEN a Job fails, THE Analysis SHALL have status `failed`, an `error_code`, and an `error_message` written for end users.

### Requirement 4: Read items

#### Acceptance Criteria

1. WHEN `GET /api/analysis/{id}/items` is called for an Analysis with status `done`, THE API SHALL respond `200` with all stored items in the order defined by spec 05 Requirement 4.4.
2. IF the Analysis is `queued` or `running`, THEN THE API SHALL respond `409` with code `analysis_not_ready`.
3. IF the Analysis is `failed`, THEN THE API SHALL respond `409` with code `analysis_failed` and the Analysis's `error_message`.
4. IF the id is unknown or expired, THEN THE API SHALL respond `404` with code `analysis_not_found`.

### Requirement 5: Export

**User Story:** As a developer, I want a Markdown cleanup plan I can paste into an issue or PR description.

#### Acceptance Criteria

1. WHEN `GET /api/analysis/{id}/export.md` is called for a `done` Analysis, THE API SHALL respond `200` with `Content-Type: text/markdown; charset=utf-8` and the document described in `design.md`.
2. THE document SHALL group items by file path (alphabetical), list items within a file by start line, and show for each: name, kind, line range, verdict, confidence, age, last author and the verdict reason.
3. THE document SHALL begin with the repo name, branch, analysed commit, analysis date, totals by verdict, and every Analysis warning.
4. WHEN the query parameter `revived` holds a comma-separated list of item ids, THE document SHALL show those items with verdict "REVIVE (marked by you)" and SHALL exclude them from the bury totals; unknown ids SHALL be ignored.
5. WHEN the query parameter `download=1` is present, THE API SHALL add `Content-Disposition: attachment; filename="graveyard-<repo>-<short commit>.md"`.
6. THE document SHALL escape Markdown control characters in names, authors and paths so that repo content cannot inject formatting or links.
7. THE error cases SHALL match Requirement 4.2 to 4.4.

Judge check: on the sample graveyard click "Export cleanup plan", then "Download .md"; the file opens in any editor and has a heading `inventory/reports.py` with a line "BURY (high) `export_legacy_csv`" under it.

### Requirement 6: Jobs

#### Acceptance Criteria

1. THE API SHALL run at most `MAX_CONCURRENT_JOBS` (1) Job at a time, in a worker thread, in submission order.
2. WHILE a Job runs, THE API SHALL update the Analysis `progress` and `total_files_scanned` from the pipeline's progress callback.
3. WHEN a Job finishes, THE API SHALL store the Analysis and items in memory and write them as one JSON file `GRAVEYARD_DATA_DIR/analyses/{id}.json`.
4. IF a Job raises `AnalysisTimeout`, THEN THE Analysis SHALL fail with code `analysis_timeout`; IF it raises any unexpected error, THEN with code `internal_error` and a generic message.
5. THE API SHALL keep responding to read requests while a Job runs.

### Requirement 7: Cache and expiry

#### Acceptance Criteria

1. THE Store SHALL expire each Analysis 24 hours after `created_at` and SHALL delete its memory entry and JSON file.
2. THE Store SHALL sweep for expired entries at startup and every 10 minutes.
3. WHEN the API starts, THE Store SHALL load unexpired JSON files from disk, and SHALL mark any Analysis found `queued` or `running` as `failed` with code `server_restarted`.
4. THE Sample analysis SHALL never expire; it SHALL be computed at startup and recomputed every 24 hours so that its ages stay correct.
5. THE Store SHALL hold at most 200 analyses, evicting the oldest first.

### Requirement 8: Shareable URL

**User Story:** As a developer, I want to send a colleague a link to my graveyard.

#### Acceptance Criteria

1. THE Analysis id SHALL be 12 URL-safe random characters, generated with a cryptographic random source.
2. THE API SHALL serve any stored Analysis to any client that has its id, with no authentication.
3. WHEN an id has expired, THE `404` response SHALL be distinguishable by code `analysis_not_found` so the frontend can offer to re-run (the repo URL travels in the share link; see spec 06 Requirement 7).

### Requirement 9: Health

#### Acceptance Criteria

1. `GET /api/health` SHALL respond `200` with `{"status": "ok", "version": "<git sha or 'dev'>", "sample_ready": <bool>, "queue_depth": <int>}` within 200 ms.
2. WHILE the Sample analysis is still being computed at startup, `sample_ready` SHALL be `false` and `POST /api/analyze` with `sample: true` SHALL respond `503` with code `warming_up` and `Retry-After: 3`.

### Requirement 10: Deployment

**User Story:** As a judge, I want a URL that works with no setup.

#### Acceptance Criteria

1. THE backend SHALL be deployed on Render as a free Docker web service defined by `render.yaml`, with `/api/health` as the health check path.
2. THE Docker image SHALL contain `git`, run as a non-root user, and start with a single uvicorn worker (the Store is in-process).
3. THE frontend SHALL be deployed on Vercel from `web/`, with a rewrite of `/api/:path*` to `${BACKEND_URL}/api/:path*`, so the browser only ever talks to the Vercel origin.
4. THE deployed app SHALL work with no environment variable set other than `BACKEND_URL` on Vercel.
5. A scheduled GitHub Actions workflow SHALL request `/api/health` every 10 minutes from 1 December 2026 until judging ends, to keep the Render instance awake.
6. THE README SHALL list the steps to run both apps locally from a fresh clone, needing only Python 3.12, Node 20+ and git, and no secrets.
7. THE repo SHALL contain an open-source `LICENSE` file at its root and SHALL NOT list `.kiro` in any ignore file.

Judge check: open the app URL in a private browser window; the landing page loads, and "Try the sample repo" shows a graveyard without any login or key.

### Requirement 11: API hygiene

#### Acceptance Criteria

1. THE API SHALL return the Error envelope for every non-2xx response, including validation errors and unhandled exceptions (which map to `500 internal_error`).
2. THE API SHALL NOT include stack traces, file system paths or git stderr in any response.
3. THE API SHALL reject request bodies larger than 2 KB with `413` and code `invalid_request`.
4. THE API SHALL log one line per request (method, path, status, duration) and SHALL NOT log `GITHUB_TOKEN`.

## Assumptions (flagged; see docs/open-decisions.md)

- A1. The brief's Analysis model is extended with `error_code`, `progress`, `is_sample`, `expires_at` and `warnings`. The listed fields are unchanged. See D6.
- A2. Render's free tier is assumed to give about 512 MB RAM, a fraction of a CPU, and to sleep after about 15 idle minutes, losing memory and disk. Verify the current terms on day 1. A slept instance loses all analyses, which is why share links carry the repo URL and the keep-warm workflow exists. See D10.
- A3. Licence: MIT. See D11.
- A4. Filtering and sorting happen in the browser; `/items` has no query parameters and no pagination. With `MAX_ITEMS` unset the response holds every item, so the grid must render in batches (spec 06) for repos with thousands of items.
