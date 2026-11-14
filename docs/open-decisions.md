# Open decisions

One page. Each row has my recommendation and what the specs currently assume. Reply with the IDs you want changed; everything else stands as written.

## Needs your answer before 21 Nov

| ID | Decision | Specs assume | Why it matters |
|---|---|---|---|
| **D1** | **Clone depth (touches a FIXED item).** The brief says "git log on a shallow clone". A depth-1 clone has one commit, so every item would show the same date and author. | `--depth 500`: still a shallow clone, with ages older than the window shown as "at least N days". | This is the only place I read a FIXED item loosely. Alternatives: depth 1 with no real ages (breaks the 180-day rule), or a full/blobless clone (not shallow). |
| **D3** | **Exported TypeScript function that nothing in the repo imports, in an app (not a library).** The brief says both "exported = low/unsure" and "check for imports of that export". | `bury / medium`, reason "safe to delete unless code outside this repo uses it". Library exports are `revive / low`. | Strict reading (`unsure / low` for every export) makes the TypeScript side nearly empty of `bury` items, since most dead TS code is an unused export. |
| **D15** | **Dependencies.** You asked to approve each. | Backend: fastapi, uvicorn, pydantic, httpx, tree-sitter, tree-sitter-typescript, tree-sitter-javascript; dev: pytest, hypothesis, ruff. Frontend: next, react, react-dom; dev: typescript, eslint, eslint-config-next, prettier, vitest, @testing-library/react, jsdom, fast-check. | Nothing else is used: no Tailwind, UI kit, syntax highlighter, Markdown renderer or rate-limit library. |
| **D10** | **Backend host.** | Render free Docker web service. | Free without a card and runs one long-lived process, which the in-memory cache needs. Cost: cold start after ~15 idle minutes and a slow CPU, covered by a keep-warm ping, a wake-up notice and re-runnable share links. Cloud Run is faster but needs a billing account and fights the in-memory design. I could not verify today's free-tier terms; the day-1 spike does. |
| **D2** | **Sample repo history.** The sample lives inside this repo, so it has no history of its own, and nothing committed this month can be older than 180 days. | A script replays `history.json` into a real git repo with backdated commits at startup. The UI labels the sample "commit history is scripted". | Without it the sample can never show a `high` item. With it, the pipeline is real but the dates are staged, hence the label. Alternative: publish the sample as a separate public repo as well. |

## Assumptions I made; change any you disagree with

| ID | Decision | Specs assume |
|---|---|---|
| D4 | Reference matching (**decided by you, 14 Nov: scope-aware**) | A reference is tied to one definition when imports, module-level names or `self`/`this` show which one it means, so same-named functions in different files or classes are judged separately. Calls on arbitrary objects (`obj.x()`) cannot be tied to a class without type inference; they match by name, minus definitions whose parameter list cannot take the call's arguments. Items found only through that argument check are capped at `medium`. Any doubt falls back to name matching. |
| D5 | Mentions in docs (`.md`, `.rst`, `.txt`) | Ignored. Mentions in config and templates (`.yaml`, `.toml`, `.json`, `.html`, `.vue`, ...) count as evidence of use → `revive`. |
| D6 | Data-model additions beyond the brief | `DeadItem`: `last_commit.is_boundary`, `snippet_truncated`, `deletable_as_whole_lines`. `Analysis`: `error_code`, `progress`, `is_sample`, `expires_at`, `warnings`. Every field you listed is unchanged. `last_commit` and `age_days` may be null when git history is unavailable. |
| D7 | Branch | Default branch only. `/tree/<branch>` in a pasted URL is ignored. |
| D8 | JavaScript files | Analysed, reported with `language: "typescript"` (the model has two values). |
| D9 | Reflection cap | A non-literal `getattr` anywhere in a repo caps **methods** at `medium`. Module-level functions are capped only when the dynamic lookup is in their own file. Widening it to all functions is safer but may leave few `high` items; decide with data from the 2 Dec sweep. |
| D11 | Licence | MIT. |
| D12 | P0/P1 split where the brief lists a feature in both | P0: language and verdict filters; "Copy deletion diff" in the detail dialog. P1: age filter, sorting, rendered diff preview, copy button on each card. |
| D13 | Fonts | Cormorant Garamond (headings) and JetBrains Mono (code) via `next/font`; system font for body text. |
| D14 | Demo repo for the video | Chosen during the 2 Dec sweep, not now: I do not know yet what Graveyard finds on real repos. |
| D16 | "Test coverage" | Static: a test file mentions the name. Graveyard never runs tests; the UI says so. |
| D17 | Limits (**decided by you, 14 Nov: none for now**) | No repo-size, file-count, file-size, clone-time, analysis-time, item-count or per-IP limit. Each is a config value that defaults to off; the checks and error screens are still built and tested, so one can be switched on with an environment variable. Risk to revisit on deploy day (1 Dec): the server runs one analysis at a time, so with no time limit one very large repo blocks everyone behind it, and a free instance may run out of memory. |
| D18 | Partially dead import statements | `from x import a, b` with only `a` unused is reported, but no diff is offered ("remove it by hand"). |
| D19 | Confidence gaps the brief left open | Unknown age → `medium`. Only tests reference it → `bury / medium`, "delete with its tests". Unknown decorator or external base class → `unsure / low`. |

## Kiro-specific

| ID | Decision | Specs assume |
|---|---|---|
| D20 | Hook and agent file formats | Written against Kiro's docs as read on 14 Nov 2026 (`.kiro/hooks/*.json` with `trigger`/`matcher`/`action`; `.kiro/agents/*.md` with frontmatter). I could not run Kiro to validate them. If Kiro rejects a file on load, the fix is syntax only. Unverified details: the `X-MCP-Readonly` header in `mcp.json`, and whether `npx` needs `cmd /c` on Windows. |
| D21 | Commit guard | "Block commits with failing property tests" is a pre-tool-use hook plus a 40-line script, `.kiro/hooks/scripts/guard_commit.py`. Kiro has no commit trigger. It gates the agent's commits; yours are gated by CI. This is the only code file in the tree. |
| D22 | Kiro Crew | Optional. Use for the two analyser agents in parallel only if setup takes under an hour on 22 Nov; otherwise plain subagents. |
| D23 | Powers | Postman is the only one I could confirm exists and fits. A hosting-provider power and a custom `graveyard-rules` power are listed as "use only if available / needed". |
| D25 | `python` on your machine | Bare `python` is the Microsoft Store alias here; only `py` works. Every hook and command calls `python`, so they need an activated `.venv` (steps in `.kiro/steering/tech.md`), and Kiro must be launched from that shell. `.venv/` goes in `.gitignore`. |
| D24 | Sweep corpus location | `../graveyard-corpus` (sibling of the repo), read through the filesystem MCP server. |

## Risks to the schedule

- **Analyser accuracy** takes days 2–7 of 13. If the gate is not green by Fri 27 Nov, apply the cut order in `.kiro/steering/roadmap.md` before touching the UI.
- **Mon 30 Nov** (ETH deadline) has nothing planned. **Fri 4 Dec** is buffer only; the complete draft goes in on Thu 3 Dec.
- **Kiro credits**: request them now, not on 1 Dec.
