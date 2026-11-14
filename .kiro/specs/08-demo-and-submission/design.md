# Design Document: 08 Demo and Submission

## Overview

Four artefacts, produced in this order because each feeds the next: `docs/accuracy.md` (numbers) → demo video (shows the numbers) → Devpost description (quotes them) → Kiro write-up (explains how it was built). `docs/kiro-log.md` is kept throughout the build so the write-up is assembled from notes, not memory.

## Accuracy sweep method

1. Pick 5+ repos before running anything: public, under the size limits, actively used, a mix of Python and TypeScript. Record the list first.
2. Run each on production. Save the export Markdown under `docs/sweep/<owner>-<repo>.md`.
3. For each repo, take the first 10 `bury / high` items in export order (no cherry-picking). For each, search the repo on GitHub for the name. Record: truly dead / false positive (and why the analyser missed the use) / cannot tell.
4. `docs/accuracy.md` table:

| Repo @ commit | Files | Bury | Unsure | Revive | High checked | Truly dead | False positive | Cannot tell |
|---|---|---|---|---|---|---|---|---|

5. Precision for `bury / high` = truly dead ÷ (truly dead + false positive). State the sample size next to the percentage every time it is quoted.

## Demo video script (target 2:40, hard limit 2:59)

Record at 1080p, browser zoom 125%, dark OS theme, notifications off. Backend warmed up beforehand. Narration is read from this script; `[N]` marks numbers taken from `docs/accuracy.md` or the screen, never invented.

| Time | Screen | Narration |
|---|---|---|
| 0:00–0:12 | Landing page, fog drifting | "Every codebase has a graveyard: functions nobody calls, imports nobody uses. Nobody deletes them, because nobody is sure they are dead. Graveyard finds out." |
| 0:12–0:25 | Paste the demo repo URL, click Analyse; loading state with rising file count | "Paste any public GitHub repo. Graveyard clones it, parses the Python with the ast module and the TypeScript with tree-sitter, and reads the git history. No login, no key, nothing from the repo is executed." |
| 0:25–0:45 | Grid appears; pan across stats bar; click the Bury filter | "Each dead item is a tombstone. Here: [N] files scanned, [N] dead items, [N] lines that could be buried, and the oldest ghost has been lying here for [N] days." |
| 0:45–1:10 | Open a `bury / high` tombstone; point at reason, last commit, callers, code | "Exhume one. No references anywhere in the repo, no test mentions it, untouched for [N] days. Verdict: bury it. And here is the deletion diff." Click Copy deletion diff; paste into a terminal with `git apply --unidiff-zero`. |
| 1:10–1:30 | Open a `revive` tombstone; point at the string-match caller | "This one looks dead too. But its name appears as a string in a dispatch table, so it is probably called at runtime. Verdict: revive it. Graveyard would rather say 'unsure' than tell you to delete live code." |
| 1:30–1:45 | Export screen; download; then paste share link in a second window | "Export the cleanup plan as Markdown for your next pull request, and share the graveyard with your team by link." |
| 1:45–2:25 | Kiro: spec folder tree → `02-python-analyzer/requirements.md` (an EARS line) → `design.md` property → the property test file → run the accuracy gate red then green → a hook firing on save | "I built this solo in two weeks with Kiro. Eight specs, each with requirements, design and tasks. The design lists correctness properties, like 'adding a caller must flip the verdict', and Kiro turned them into property-based tests. A hook reruns the accuracy gate on every save of an analyser file: two sample repos, one full of known dead code, one full of code that only looks dead. The UI was not allowed to start until that gate was green. Custom agents own one pipeline stage each." |
| 2:25–2:40 | `docs/accuracy.md` table, then back to the landing page with the URL visible | "On [N] real repos, [N] of [N] hand-checked high-confidence items were truly dead. Graveyard: paste a repo, bury the dead. Link below." |

Shot list to capture separately (so the Kiro segment can be cut tightly): spec tree; EARS criterion; property in design; property test; gate failing; gate passing; hook run; agent list.

If the demo repo analysis takes longer than 15 s, cut the loading state with a visible "×4" speed label rather than hiding it.

## Devpost description outline

- **Title:** Graveyard: find the dead code haunting your repo
- **Tagline:** Paste a public GitHub repo URL, get a graveyard of its dead code.
- **Inspiration** (3–4 sentences): the function nobody dares delete; onboarding into a repo and reading code that turned out to be dead.
- **What it does:** the six-step core loop; bury / revive / unsure with one-sentence reasons; the honesty rules (static coverage, lower-bound ages, never `high` when dynamic calls are possible).
- **How we built it (Frankenstein):** the stitched parts and the seams between them: Python `ast` + tree-sitter producing one shared `Candidate` type; git blame for age; a pure decision table for verdicts; FastAPI job queue with no database; Next.js on Vercel proxying to Render. One diagram.
- **How Kiro was used:** five bullets summarising the write-up, linking to it.
- **Challenges:** false positives (entry points, exports, dynamic lookups) and how the two sample repos and the gate handled them; shallow-clone history and honest lower bounds; free-tier limits.
- **Accomplishments:** numbers from `docs/accuracy.md`; number of properties and what they caught; full loop with no key or login.
- **What we learned:** what specs changed about the work; one thing that did not work.
- **What's next:** P1 items; type-aware resolution of method calls; more languages; a GitHub Action that comments on pull requests (stated as future, not built).
- **Built with:** python, fastapi, tree-sitter, typescript, next.js, react, vercel, render, kiro, hypothesis.
- **Links:** app, repo, video.

## Kiro write-up outline (`docs/kiro-writeup.md`, 600–900 words)

1. **Approach in one paragraph.** Specs first, accuracy gate before UI, agents per pipeline stage.
2. **Spec-driven development.** How `requirements.md` → `design.md` → `tasks.md` structured the build; an example EARS criterion and the task and test it produced (paths + commit). Where a spec was wrong and was changed.
3. **Steering.** What `product.md`, `tech.md`, `structure.md`, `testing.md` made Kiro do consistently (for example: never `bury` when in doubt; reasons only from templates; no new dependencies without asking).
4. **Hooks.** Each hook, its trigger, and one time it caught something (from `docs/kiro-log.md`).
5. **Property-based testing.** The properties in the design documents, the generators, and at least one real bug a property found, with the shrunk counterexample.
6. **Custom agents (and Crew, if used).** One agent per stage, the shared `Candidate` contract as the handoff, what running them separately bought.
7. **MCP.** What the GitHub and filesystem servers were used for during development (finding sweep repos, checking blame results against GitHub, reading the sweep corpus outside the workspace).
8. **Powers.** Which were installed and what each added; omit the section if none were used.
9. **Vibe coding versus specs.** Where free-form chat was faster (UI polish, copy) and where specs were necessary (analysis rules).
10. **What I would do differently.**

## Submission checklist (`docs/submission-checklist.md`)

Repository
- [ ] Repo is public on GitHub (not GitLab)
- [ ] `LICENSE` (OSI-approved) at the repo root
- [ ] `/.kiro` exists at the repo root with steering, specs, hooks, agents and settings; not in `.gitignore` or `.git/info/exclude`
- [ ] First commit is dated on or after 30 Oct 2026
- [ ] README: what it is, live URL, local run steps with no secrets, limits, known blind spots
- [ ] A fresh clone runs with README steps only (tested in a new folder)
- [ ] No secrets in the repo or its history

App
- [ ] App URL is live and passes `scripts/smoke.sh` within one hour before submitting
- [ ] Works in a private window: no login, no key, no payment
- [ ] "Try the sample repo" works; a real public repo works
- [ ] Error states verified on production: private repo, huge repo, invalid URL, rate limit (mocked or real)
- [ ] Keep-warm workflow enabled
- [ ] Works on a phone; keyboard-only pass done

Evidence
- [ ] Accuracy gate green on `main`
- [ ] `docs/accuracy.md` complete; every quoted number traces to it
- [ ] `docs/judge-checklist.md` complete

Devpost
- [ ] Category: Frankenstein
- [ ] Text description
- [ ] Demo video: public on YouTube, under 3:00, shows the full loop and Kiro
- [ ] Kiro write-up pasted or linked
- [ ] App URL and repo URL
- [ ] Student details for Best Student Project: TU Delft, BSc Computer Science, graduating July 2027, plus whatever proof the form asks for
- [ ] Submitted before Fri 4 Dec 2026 14:00 PT (23:00 CET); target 20:00 CET
- [ ] Confirmation email received

Admin
- [ ] Kiro credits requested before Tue 1 Dec 2026 12:00 PT

## Error Handling (things that go wrong on submission day)

| Risk | Mitigation |
|---|---|
| Render instance asleep or redeploying when judges visit | Keep-warm workflow; landing wake-up notice; sample analysis recomputed at startup |
| GitHub rate-limits the server's IP | Size pre-check is optional by design; set `GITHUB_TOKEN` on Render if seen during the sweep |
| Video upload or processing delay | Upload on 3 Dec; never on deadline day |
| A late fix breaks accuracy | Gate runs in CI; no deploys after 18:00 CET on 4 Dec |
| Demo repo changes between sweep and recording | Record against whatever the repo is that day; numbers in narration are read from the screen |

## Testing Strategy

- Time the script by reading it aloud once before recording; trim narration, not steps, if over 2:50.
- Have one other person follow the README from a fresh clone and run the judge checklist cold.
