---
inclusion: always
---

# Roadmap (solo, 21 Nov – 3 Dec 2026)

Hard dates: Amazon OA due Fri 20 Nov. ETH Zurich deadline Mon 30 Nov. Kiro credit request closes Tue 1 Dec 12:00 PT. Submission closes Fri 4 Dec 14:00 PT = 23:00 CET.

## Before 21 Nov (30 minutes total, no build work)

- Request the 4,000 Kiro credits now. Do not wait for 1 Dec.
- Push this `.kiro/` tree to the public GitHub repo and add the licence.
- Answer `docs/open-decisions.md`.

## Build order

The order gets a working end-to-end slice on day 1 (sample repo → CLI JSON → deployed health check), then deepens each stage. The UI does not start until the accuracy gate passes.

| Day | Date | Work | Spec tasks | Exit check |
|---|---|---|---|---|
| 1 | Sat 21 Nov | Skeleton, models, sample repos + scripted history, local-folder ingestion, CLI stub. Deploy empty backend to Render and empty Next app to Vercel | 01: 1–6, 07: 1–3 | `/api/health` live on Render; Vercel page loads |
| 2 | Sun 22 Nov | Python dead functions | 02: 1–6 | haunted-repo Python functions found by CLI |
| 3 | Mon 23 Nov | Python dead imports + properties | 02: 7–11 | Python half of both `expected.json` passes |
| 4 | Tue 24 Nov | TS parsing, definitions, references | 03: 1–5 | haunted-repo TS functions found |
| 5 | Wed 25 Nov | TS exports, imports, properties | 03: 6–11 | TS half of both `expected.json` passes |
| 6 | Thu 26 Nov | Git archaeology + verdict engine | 04: all, 05: 1–5 | CLI prints full DeadItems with ages and verdicts |
| 7 | Fri 27 Nov | **Accuracy gate**, GitHub URL ingestion, API endpoints | 05: 6–8, 01: 7–11, 07: 4–9 | Gate green. `curl` full loop against local backend |
| 8 | Sat 28 Nov | UI: tokens, landing, grid, loading/empty/error | 06: 1–9 | Sample repo visible as tombstones in browser |
| 9 | Sun 29 Nov | UI: detail, diff copy, export, share URL | 06: 10–16 | Full loop in browser on sample repo |
| 10 | Mon 30 Nov | ETH deadline. Graveyard: nothing planned | | |
| 11 | Tue 1 Dec | Production deploy, keep-warm, error states on real repos, mobile + keyboard pass | 07: 10–14, 06: 17–19 | Full loop on production URL from a phone |
| 12 | Wed 2 Dec | Real-repo false-positive sweep, fixes, README. P1 only if everything above is green and the owner says yes | 08: 1–3 | `docs/accuracy.md` written |
| 13 | Thu 3 Dec | Record video, Devpost text, Kiro write-up, submit a complete draft | 08: 4–9 | Devpost draft submitted |
| – | Fri 4 Dec | Buffer only. Final submit by 20:00 CET (3h before the deadline) | 08: 10 | Submitted |

## Cut order if behind

Cut in this order, top first. Never cut the accuracy gate.

1. All P1.
2. Export screen preview (keep the download link to `export.md`).
3. Line-level blame (fall back to file-level `git log -1`, spec 04 requirement 3).
4. Text-file reference scan for `.vue`/`.svelte`/`.astro` (keep code and config files).
5. The arity rules (PY-A1, TS-A1) and class-family resolution (PY-S4, PY-S5, TS-S4): those occurrences become unresolved, which is the safe direction. Remove sample item 18 from `expected.json` in the same commit. Keep import-based resolution (PY-S1 to S3, TS-S1 to S3).
6. Class-method analysis in TypeScript (keep top-level functions).

Scope-aware matching (owner decision, 14 Nov) adds roughly half a day to each analyser. Each analyser is built name-matching first (spec 02 task 3.6), so there is a working result before resolution is added.
