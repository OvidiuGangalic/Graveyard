---
inclusion: always
---

# How Kiro is used on this project

Kiro is the development tool. Nothing here runs in production; the deployed app makes no LLM calls.

Kiro's file formats change between releases. The hook, agent and MCP files in this repo follow the documentation as read on 14 Nov 2026. If Kiro reports a schema error when loading one, fix the file to match the current docs and keep its intent.

## Specs

Eight spec folders under `.kiro/specs/`, each with `requirements.md` (EARS), `design.md` (with Correctness Properties) and `tasks.md`. Work one task at a time, in the order of `steering/roadmap.md`. Tasks marked `*` are P1 and need the owner's approval before they start.

## Hooks (`.kiro/hooks/`)

| File | Hook | Trigger | Action | Purpose |
|---|---|---|---|---|
| `format-on-save.json` | `format-python` | file save, `backend/**/*.py` | `python -m ruff format backend` | Auto-format so reviews are about logic |
| | `autofix-python` | file save, `backend/**/*.py` | `python -m ruff check backend --fix --quiet` | Remove unused imports and trivial lint (fitting, for this product) |
| | `format-web` | file save, `web/**/*.{ts,tsx,css}` | `npm --prefix web run format` | Same for the frontend |
| `test-on-save.json` | `unit-tests-python` | file save, `backend/**/*.py` | `python -m pytest backend/tests/unit -q -x` | Fast feedback on the rule just edited |
| | `lint-web` | file save, `web/**/*.{ts,tsx}` | `npm --prefix web run lint` | |
| | `tests-web` | file save, `web/**/*.{ts,tsx}` | `npm --prefix web test -- --run` | |
| `accuracy-gate-on-save.json` | `accuracy-gate` | file save under `backend/graveyard/{analyzers,verdict,git}/` or `samples/` | `python -m pytest backend/tests/acceptance -q` | A rule change that causes a false positive is seen within seconds |
| `guard-commit.json` | `block-commit-on-failing-properties` | before the agent uses the shell tool | `python .kiro/hooks/scripts/guard_commit.py` | If the command is a `git commit`, run the property tests and the accuracy gate; a non-zero exit blocks the commit |
| `spec-drift.json` | `spec-drift-check` | file save, `.kiro/specs/**/requirements.md` | agent prompt | Ask the agent to list where `design.md` and `tasks.md` no longer match the edited requirements, without editing them |
| | `type-mirror-check` | file save, `backend/graveyard/models.py` | agent prompt | Ask the agent to compare the API models with `web/lib/types.ts` and report differences |

The commit guard only gates commits made by the agent. Commits made by hand are gated by CI, which runs the same tests.

## MCP servers (`.kiro/settings/mcp.json`)

| Server | What it enables that would otherwise be hard |
|---|---|
| **GitHub** (remote, read-only) | (1) Finding candidate repos for the accuracy sweep by language and size without leaving the editor. (2) Checking git archaeology against an independent source: for a sample of items, compare our blame result with GitHub's commit data for the same lines. (3) Reading how real repos register entry points (decorators, `package.json` fields) when a false positive needs a new rule, without cloning them. (4) Collecting real examples of the error states: a private repo's response, an empty repo, a very large repo's `size`. Uses a personal token from the developer's environment at development time only. |
| **Filesystem** (local, scoped to `../graveyard-corpus`) | Kiro's built-in file tools stop at the workspace. The sweep corpus (clones of real repos) must live outside the workspace so it is never committed and never indexed as project code. This server lets the agent read those clones to investigate a false positive: open the file Graveyard flagged, search the corpus for the name, and write the regression case. Scoped to that one directory. |

Neither server is used by the running app, which talks to GitHub through `git` and one anonymous REST call.

## Custom agents (`.kiro/agents/`)

One agent per pipeline stage. Each owns one package, may write only there and in its tests, and hands off through a type in `backend/graveyard/models.py`.

| Agent | Owns | Reads | Outputs | Hands off to |
|---|---|---|---|---|
| `python-analyzer` | `backend/graveyard/analyzers/python/`, its unit tests and cases | spec 02, `RepoSnapshot` | `list[Candidate]` for Python | `verdict-judge` |
| `typescript-analyzer` | `backend/graveyard/analyzers/typescript/`, its unit tests and cases | spec 03, `RepoSnapshot` | `list[Candidate]` for TypeScript | `verdict-judge` |
| `git-archaeologist` | `backend/graveyard/git/`, its tests | spec 04, `Candidate` line ranges | `CommitInfo` per Candidate | `verdict-judge` |
| `verdict-judge` | `backend/graveyard/verdict/`, `pipeline.py`, `backend/tests/acceptance/` | spec 05, all of the above | `DeadItem`s; the accuracy gate result | API (spec 07) |
| `gravedigger` (orchestrator) | nothing; delegates | roadmap, all specs | A plan of which agent takes which task; a summary of results | – |

Handoff rules
- The contract is frozen first: spec 02 task 1 defines `Candidate`, `Flag` and `Caller`. No analyser agent starts before it is merged.
- No stage agent may write `backend/graveyard/models.py`. Contract tasks (spec 02 task 1, spec 05 task 1, spec 07 task 4.1) are done in the main Kiro session with the owner present.
- An agent that needs a contract change stops and reports to the owner. It does not edit `models.py` on its own.
- Only `verdict-judge` may edit `samples/*/expected.json`, and only with a stated reason.
- When the gate fails, `verdict-judge` reports which stage produced the wrong evidence (a missing reference → analyser agent; a wrong age → archaeologist; a wrong row → itself) and the fix goes to that agent.

Parallel work: on days 2–5 the two analyser agents are independent once the contract exists, so they can run as parallel subagents from `gravedigger`, or as two Kiro Crew sessions on separate branches. Use Crew only if setting it up takes under an hour on day 2; otherwise run the agents one after the other. Record what was done in `docs/kiro-log.md`, because the write-up may only claim what happened.

## Powers

Check the catalogue at kiro.dev/powers on day 1 and install only what is used.

| Power | What it adds | Status |
|---|---|---|
| Postman | Builds a collection for the five endpoints from spec 07 and runs it against local and production; a second, independent check of every status code in the error tables | Planned; confirm it is still in the catalogue |
| A power for the hosting provider (Vercel or Render), if one exists | Deploy status and logs from inside Kiro on deploy day | Use only if it exists; do not substitute another provider's power |
| `graveyard-rules` (custom, local) | Packages the tree-sitter node-type notes from the spec 03 spike and the rule tables of specs 02/03 so they load only when an analyser file is open, keeping other sessions' context small | Optional; build only if the spike notes grow beyond what steering should carry |

If a power is not installed and used, it is not mentioned in the submission.

## Vibe coding

Allowed for UI polish, copy and CSS in spec 06 after the tokens exist. Not allowed for anything under `backend/graveyard/analyzers/`, `verdict/` or `git/`: those change only through a spec task with a rule ID and a test.
