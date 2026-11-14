---
inclusion: always
---

# Tech

## Stack (FIXED: ask before changing)

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router) + React + TypeScript, deployed on Vercel free tier |
| Backend | FastAPI + Python 3.12, deployed on Render free web service (Docker) |
| Python analysis | stdlib `ast` (plus stdlib `tokenize`, `tomllib`) |
| TS/JS analysis | tree-sitter via Python bindings |
| Git history | `git` CLI on a shallow clone (`--depth 500`), plus the GitHub public REST API for repo metadata (optional `GITHUB_TOKEN` for higher rate limits) |
| Storage | No database. Analyses cached in memory and as JSON on local disk, keyed by analysis ID, expiring after 24h |
| Runtime AI | None. No LLM API key at runtime. Works for judges with no key, no login, no payment |

Why Render: see `specs/07-api-and-deploy/design.md` section "Hosting decision".

## Dependencies (proposed: every one of these needs owner approval; add nothing else without asking)

Backend runtime: `fastapi`, `uvicorn[standard]`, `pydantic` (v2, comes with FastAPI), `httpx` (GitHub API), `tree-sitter`, `tree-sitter-typescript`, `tree-sitter-javascript`.

Backend dev: `pytest`, `hypothesis`, `ruff`.

Frontend runtime: `next`, `react`, `react-dom`. Fonts through `next/font` (built in). Styling with CSS Modules + CSS custom properties. No UI kit, no Tailwind, no syntax highlighter, no Markdown renderer in P0.

Frontend dev: `typescript`, `eslint` + `eslint-config-next`, `prettier`, `vitest`, `@testing-library/react`, `jsdom`, `fast-check`.

System: `git` (in the backend Docker image), Node 20+, Python 3.12.

## Commands

All commands run from the repo root. They must work on Windows (PowerShell), macOS and Linux.

`python` must resolve to Python 3.12 with the backend installed. On the owner's Windows machine the bare `python` command is the Microsoft Store alias and only `py` works, so create and activate a virtual environment first; inside it `python` is correct. Kiro must be started from a shell where that environment is active, otherwise every hook that calls `python` fails.

| Purpose | Command |
|---|---|
| Create the virtual environment (once) | `py -3.12 -m venv .venv` (Windows) or `python3.12 -m venv .venv` |
| Activate it | `.venv\Scripts\Activate.ps1` (Windows) or `source .venv/bin/activate` |
| Backend install | `python -m pip install -e "backend[dev]"` |
| Backend dev server | `python -m uvicorn graveyard.main:app --reload --port 8000 --app-dir backend` |
| Backend lint | `python -m ruff check backend` |
| Backend format | `python -m ruff format backend` |
| Backend unit tests | `python -m pytest backend/tests -q -m "not property and not acceptance"` |
| Property tests | `python -m pytest backend/tests/property -q` |
| Accuracy gate (sample repos) | `python -m pytest backend/tests/acceptance -q` |
| Analyse a local folder (no server) | `python -m graveyard.cli analyse <path>` (run from `backend/`) |
| Frontend install | `npm --prefix web ci` |
| Frontend dev server | `npm --prefix web run dev` |
| Frontend lint / typecheck | `npm --prefix web run lint` and `npm --prefix web run typecheck` |
| Frontend tests | `npm --prefix web test` |
| Frontend format | `npm --prefix web run format` |

## Environment variables (none are required)

| Variable | Where | Default | Purpose |
|---|---|---|---|
| `GITHUB_TOKEN` | backend | unset | Optional. Raises GitHub API limit from 60 to 5,000 requests/hour |
| `GRAVEYARD_DATA_DIR` | backend | OS temp dir + `/graveyard` | Clone and cache directory |
| `GRAVEYARD_<LIMIT>` | backend | unset | Optional. Switches on one limit, for example `GRAVEYARD_MAX_SOURCE_FILES=5000`. All limits are off by default (spec 01 design, "Limits") |
| `BACKEND_URL` | web (build/run) | `http://localhost:8000` | Target of the Next.js `/api/*` rewrite |

The app must run from a fresh clone with README steps only and no secrets.

## Code style

Python
- `ruff` for lint and format, line length 100. Type hints on every public function. `from __future__ import annotations`.
- Pydantic v2 models for everything that crosses the API boundary; frozen dataclasses for internal pipeline types.
- Analysers are pure functions of `(RepoSnapshot) -> list[Candidate]`: no network, no git, no global state. This is what makes them property-testable.
- `subprocess.run` with an argument list, never `shell=True`. Every subprocess has a timeout.
- Never `import`, `exec`, `eval` or otherwise run anything from an analysed repo.
- Verdict reasons come from the fixed templates in `specs/05-verdict-engine/design.md`. No free-text reasons.

TypeScript
- `strict: true`. No `any`. Types in `web/lib/types.ts` mirror the backend models field for field (snake_case kept as-is; no mapping layer).
- Server components by default; `"use client"` only where state or effects are needed.
- All colours, fonts and spacing come from the tokens in `web/app/globals.css`. No hard-coded hex values in components.
- Every interactive element is a real `<button>`, `<a>` or form control. No clickable `<div>`.

Testing
- Every analysis rule has at least one unit test named after its rule ID (for example `test_PY_E3_route_decorator_is_live`).
- Property-based tests use Hypothesis (backend) and fast-check (frontend). Properties are listed in `steering/testing.md`; each one names the requirement it validates.
- The accuracy gate (both sample repos) must pass before any work starts on spec 06.

Commits
- Small commits, imperative subject, spec task number in the body (for example `Refs: 02-python-analyzer task 3.2`).
- `/.kiro` is never gitignored.

## Spelling

UI copy uses British spelling ("Analyse"). The API path is `/api/analyze` as specified; do not rename it.
