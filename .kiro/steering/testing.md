---
inclusion: fileMatch
fileMatchPattern: "{backend/**/*.py,web/**/*.ts,web/**/*.tsx,.kiro/specs/**/*.md}"
---

# Testing and property-based testing plan

## Layers

| Layer | Where | Runs | Purpose |
|---|---|---|---|
| Unit, one per rule ID | `backend/tests/unit/` | on save (hook), CI | Each analysis rule (PY-E3, TS-R7, ...) has a test named after it |
| Property | `backend/tests/property/`, `web/**/*.property.test.ts` | before agent commits (hook), CI | Invariants over generated input |
| Accuracy gate | `backend/tests/acceptance/` | on save of analyser/verdict/git/sample files (hook), CI | Both sample repos match their `expected.json` |
| API | `backend/tests/api/` | CI | Every status and error code in spec 07 |
| Component | `web/**/*.test.tsx` | on save (hook), CI | Screen states, dialog, forms |
| Manual judge checklist | `docs/judge-checklist.md` | before submission | Every P0 "Judge check" on production |

The accuracy gate outranks everything: when it is red, no other work proceeds.

## Property catalogue

Backend properties use Hypothesis; frontend properties use fast-check. Generators are built from plain strategies (templates of small modules with unique identifiers and a random call graph); no extra generator library.

| ID | Property | Spec and requirement validated |
|---|---|---|
| P1 | The Python analyser never raises, for any text or bytes in a `.py` file | 02 R7.1 |
| P1-ts | The TypeScript analyser never raises, for any bytes in a `.ts`/`.tsx`/`.js` file | 03 R8.1 |
| P2 / P2-ts | Dead function count ≤ functions defined; every item's line range lies inside its file; the snippet equals those lines | 02 R1.1, R8.1; 03 R1.2, R9.1 |
| P3 / P3-ts | An uncalled function is reported; importing and calling it un-reports it; removing that again reports it (and for TS: importing an export un-reports it) | 02 R2.2, R2.4; 03 R2.1, R3.1 |
| P4, P4a | The pipeline is deterministic: same result twice, and with the file order shuffled, including ids | 02 R7.2; 03 R8.2; 05 R4.2, R4.4 |
| P5 / P5-ts | Adding a file to a repo never makes a previously live function dead | 02 R2.1; 03 R3.1 |
| P6 | A function with an exempt name or decorator (PY-E tables) is never reported | 02 R3.2 |
| P7 | `high` confidence implies: no revive/blind/caution flag, not test-covered, a commit present, age > 180 days | 05 R1.3, R1.4 |
| P7b | `bury` ⇔ confidence medium or high; `revive`/`unsure` ⇔ low | 05 R2.4 |
| P7-ts | Every Candidate for an exported function carries `EXPORTED` (so it can never be `high`) | 03 R3.7 |
| P8 | Adding evidence (a flag, test coverage, a younger age) never raises confidence | 05 R1.1, R1.2 |
| P9 | `age_days` ≥ 0, equals whole days between the dates, and never decreases as "now" advances | 04 R4.1, R4.2 |
| P10, P10b | URL normalisation is idempotent and recovers the generated owner/repo; non-GitHub hosts are rejected | 01 R1.1, R1.3, R1.4 |
| P11 | The Markdown export lists every item exactly once under its file, files in order, header counts equal to the item counts | 07 R5.2–R5.4 |
| P12 | Applying the copied deletion diff removes exactly lines `start..end` | 06 R7.1 |
| P13 / P13-ts | An unused import is reported; adding a use un-reports it | 02 R6.1; 03 R7.1 |
| P14 | The walker never returns a path outside the repo root or inside an excluded directory | 01 R5.1, R5.2 |
| P15, P16 | The blame parser picks the newest commit (ties by hash) and never raises on any text | 04 R1.1, R1.4, R3.5 |
| P17 | Every verdict reason is one sentence, ≤ 240 chars, no unfilled placeholder, and says "at least" for boundary ages | 05 R3.2, R3.6 |
| P18 | Item ids are unique within an analysis | 05 R4.3 |
| P19 | Repo content cannot inject Markdown into the export | 07 R5.6 |
| P20 | API models survive a JSON round trip | 07 R6.3 |
| P21 | For any configured count N, the rate limiter never accepts more than N requests per IP in any 10-minute window; with no count set it accepts everything | 07 R2.1 |
| P24 / P24-ts | Two same-named functions in different modules: importing and calling one leaves exactly the other reported; switching the import switches the result | 02 R2.4; 03 R3.1 |
| P25 / P25-ts | Scope resolution only adds findings: everything pure name matching reports is still reported | 02 R2.9, R2.10; 03 R3.1a, R3.1b |
| P26 | The arity rule never excludes a call that Python would accept for that signature | 02 R2.8 |
| P22, P23 | Filters partition the items and round-trip through the URL; stats are consistent with the items | 06 R3.2, R4.1, R4.2 |

## Rules for property tests

- Each test's docstring starts with the property ID and the "Validates" line, copied from the design document.
- Hypothesis settings: `max_examples=100` locally, `deadline=None` for analyser properties; a `ci` profile with `max_examples=300`; `derandomize=True` in CI so failures reproduce.
- When a property fails, keep the shrunk counterexample as a unit test before fixing the bug. Note it in `docs/kiro-log.md` (it is write-up material).
- A property test is never weakened to make it pass. If the property is wrong, change the design document first, then the test.
- Property tests must not touch the network. Git-dependent properties build repos in `tmp_path`.

## Definition of done (project)

- Every P0 requirement has a "Judge check" that a non-technical person can run in under 2 minutes, and each passes on production.
- Accuracy gate green: every known-dead item in the haunted repo is found with the expected verdict; nothing in the living repo is `bury` or `high`.
- A fresh clone runs with README steps only and no secrets.
- The demo video is under 3 minutes and shows the full loop.
- `docs/submission-checklist.md` is fully ticked.
