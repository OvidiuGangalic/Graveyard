---
inclusion: always
---

# Product: Graveyard

**One-liner:** paste a public GitHub repo URL, get a graveyard of its dead code.

## Problem

Every repo has dead functions, dead imports and zombie tests. Nobody deletes them because nobody is sure nothing still calls them. They slow onboarding, hide bugs and bloat the codebase.

## Audience

Developers and small teams, especially on Python + TypeScript repos. Secondary audience: hackathon judges, who must be able to use the app with no key, no login and no payment.

## Core loop

1. Paste a repo URL, or click "Try the sample repo".
2. Graveyard analyses the repo (static analysis only; nothing from the repo is ever executed).
3. Each dead item appears as a tombstone in a grid.
4. Click a tombstone to **exhume** it: file, lines, last commit, author, age, callers found, test coverage, confidence.
5. Verdict: **BURY IT** (safe to delete, with a deletion diff), **REVIVE IT** (looks dead but is probably used, and why), or **UNSURE** (the analysis cannot see enough to say).
6. Export a Markdown cleanup plan.

## Tone

Haunted graveyard: dark UI, green fog, tombstones, "exhume", "bury", "revive". The theme is in the chrome and the copy. The data is serious.

## Accuracy rules (non-negotiable)

- No fake results. Every number on screen comes from the analysis of the actual repo.
- False positives are the biggest product risk. When in doubt the analyser says `unsure` or `revive`, never `bury`.
- `high` confidence is never claimed when the analysis cannot see dynamic calls. The verdict reason always says what the analysis could not see.
- "Test coverage" means *static* coverage: a test file mentions the name. Graveyard never runs tests. The UI must say this.
- The sample repo's git history is scripted (backdated commits). The UI must label it as such.

## What Graveyard never does

- No login, accounts or private repos.
- No languages other than Python and TypeScript/JavaScript.
- No deleting code in the user's repo, no pull requests, no writes to GitHub of any kind.
- No runtime LLM calls and no paid API. Kiro agents are a development tool only.
- No executing, importing or installing code from an analysed repo.
- No storing analyses beyond 24 hours, and no database in v1.

## Priorities

- **P0 (must ship):** repo URL input + sample repo; Python dead functions; TypeScript dead functions; dead imports (both); git last-touched date/author per item; graveyard grid; tombstone detail; verdict with reason and confidence; Markdown export; shareable analysis URL; error states for private repos, huge repos, invalid URLs and rate limits.
- **P1 (only when all P0 is done, and only after asking the owner):** zombie-test detection; age filter and sorting; deletion diff preview; copy-to-clipboard per tombstone card.
- **Out of scope (do not spec or build):** login/accounts, private repos, other languages, auto-deleting code, auto-creating pull requests, any paid API.

## Hackathon context

Kiroween 2026 (AWS / Devpost), category Frankenstein, solo student entry (TU Delft BSc Computer Science, graduating July 2027), eligible for Best Student Project. Deadline Fri 4 Dec 2026 14:00 PT (23:00 CET). Judging is 20% each: Potential Impact, Technological Implementation (depth of Kiro use), Design, Innovation/Idea, Presentation.

## Working agreement for agents

- Ask the owner before changing any FIXED decision (stack, hosting model, no-database, no-runtime-LLM, hackathon constraints), before starting any P1 task, and before adding any dependency not listed in `tech.md`.
- If a requirement is ambiguous, write the assumption into the spec under "Assumptions" and flag it in `docs/open-decisions.md`. Do not decide silently.
