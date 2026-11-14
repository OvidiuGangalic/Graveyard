---
inclusion: always
---

# Repo structure

```
/
├── .kiro/                       # NEVER gitignore. Required by the hackathon.
│   ├── steering/                # product.md, tech.md, structure.md, testing.md, kiro-workflow.md, roadmap.md
│   ├── specs/                   # 01..08, each with requirements.md, design.md, tasks.md
│   ├── hooks/                   # *.json hook files + scripts/
│   ├── agents/                  # custom agents (one per pipeline stage)
│   └── settings/mcp.json        # MCP servers used during development
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── graveyard/
│   │   ├── main.py              # FastAPI app factory, startup (sample warm-up), /api/health
│   │   ├── config.py            # every limit and threshold, in one place
│   │   ├── models.py            # API models (Analysis, DeadItem) + internal types (RepoSnapshot, Candidate, Evidence, CommitInfo)
│   │   ├── pipeline.py          # ingest -> analyse -> archaeology -> verdict, with progress callbacks
│   │   ├── store.py             # in-memory + on-disk cache, 24h TTL
│   │   ├── export.py            # Markdown cleanup plan
│   │   ├── cli.py               # `python -m graveyard.cli analyse <path>`
│   │   ├── api/                 # routes.py, errors.py, ratelimit.py, jobs.py
│   │   ├── ingestion/           # url.py, github.py, clone.py, walker.py, samples.py   (spec 01)
│   │   ├── analyzers/
│   │   │   ├── common.py        # shared helpers: test-file detection, text-reference scan, snippets
│   │   │   ├── python/          # definitions.py, references.py, resolve.py, entrypoints.py, imports.py   (spec 02)
│   │   │   └── typescript/      # parser.py, definitions.py, references.py, resolve.py, exports.py, imports.py   (spec 03)
│   │   ├── git/                 # archaeology.py   (spec 04)
│   │   └── verdict/             # engine.py, reasons.py   (spec 05)
│   └── tests/
│       ├── unit/                # mirrors graveyard/ layout
│       ├── property/            # Hypothesis properties + strategies.py
│       ├── acceptance/          # accuracy gate over samples/
│       └── api/                 # endpoint tests with FastAPI TestClient
├── web/
│   ├── package.json
│   ├── next.config.ts           # /api/* rewrite to BACKEND_URL
│   ├── app/
│   │   ├── layout.tsx           # fonts, fog background
│   │   ├── globals.css          # design tokens
│   │   ├── page.tsx             # Landing
│   │   └── graveyard/[id]/
│   │       ├── page.tsx         # Graveyard grid (+ detail dialog via ?item=)
│   │       └── export/page.tsx  # Export screen
│   ├── components/              # Tombstone, TombstoneDetail, StatsBar, Filters, RepoForm, DiggingState, ErrorState, ...
│   └── lib/                     # api.ts, types.ts, diff.ts, filters.ts, stats.ts, revived.ts, format.ts
├── samples/
│   ├── haunted-repo/            # known-dead sample: source files + history.json + expected.json
│   └── living-repo/             # known-live sample: source files + history.json + expected.json
├── docs/
│   ├── open-decisions.md        # decisions waiting for the owner
│   ├── accuracy.md              # results of the real-repo false-positive sweep (+ sweep/ exports)
│   ├── kiro-log.md              # one line per build session; raw material for the write-up
│   ├── kiro-writeup.md          # how Kiro was used (submission)
│   ├── judge-checklist.md       # every P0 "Judge check", run on production
│   └── submission-checklist.md
├── scripts/                     # smoke.sh
├── .github/workflows/           # ci.yml, keep-warm.yml
├── render.yaml
├── README.md
└── LICENSE
```

## Rules

- Pipeline stages only talk through the types in `backend/graveyard/models.py`. An analyser never imports from `git/` or `verdict/`, and vice versa. `pipeline.py` is the only module that knows all stages.
- `samples/` is test data and demo data. Files under `samples/` are never linted, formatted or "fixed": their dead code is deliberate. They are excluded in `ruff`, `eslint`, `prettier` and `tsconfig`.
- `expected.json` in each sample repo is the ground truth for the accuracy gate. Changing it requires a sentence in the commit message explaining why the ground truth changed.
- Nothing under `web/` imports from `backend/` or `samples/`. The only contract between them is the HTTP API in `specs/07-api-and-deploy/design.md`.
- New top-level directories need owner approval.
