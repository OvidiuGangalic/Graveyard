# Implementation Plan: 06 Graveyard UI

**Do not start until the accuracy gate (spec 05 task 7) is green.** Depends on spec 07 tasks 3 (Next.js skeleton deployed) and 7–8 (API routes and export) running locally.

Order: the sample repo is visible as tombstones by the end of task 9; the full loop works by the end of task 16.

- [ ] 1. Tooling
  - Vitest + Testing Library + jsdom + fast-check config; `lint`, `typecheck`, `test`, `format` scripts; exclude `samples/` everywhere
  - _Requirements: 10.1_

- [ ] 2. Types and API client
  - `lib/types.ts` mirroring spec 07; `lib/api.ts` with `ApiError`; non-JSON responses treated as network failures
  - Backend CLI command `schema` + the type mirror test
  - _Requirements: 1.3, 1.6, 1.7_

- [ ] 3. Design tokens and layout shell
  - `globals.css` with every token from `design.md`; fonts through `next/font`; `layout.tsx` with `<main>`, fog layers, reduced-motion rule
  - Check each listed colour pair with a contrast checker; adjust tokens and the design table if any is below 4.5:1
  - _Requirements: 10.1–10.4, 11.6_

- [ ] 4. Pure helpers with property tests
  - [ ] 4.1 `lib/format.ts` (age wording incl. "at least" and "age unknown", hashes, dates, GitHub URLs, aria label) with unit tests
    - _Requirements: 3.3, 6.3, 6.6, 11.2_
  - [ ] 4.2 `lib/filters.ts` + property test P22
    - _Requirements: 4.1, 4.2_
  - [ ] 4.3 `lib/stats.ts` + property test P23
    - _Requirements: 3.2_
  - [ ] 4.4 `lib/diff.ts` + property test P12
    - _Requirements: 7.1_

- [ ] 5. Landing
  - [ ] 5.1 `RepoForm`: input, Analyse, sample button, in-flight state, navigation to the Share link
    - _Requirements: 1.1, 1.3, 1.4, 1.5_
  - [ ] 5.2 Inline errors: API message, network failure, empty input; focus returns to the input
    - _Requirements: 1.6, 1.7, 1.8_
  - [ ] 5.3 Health wake-up notice
    - _Requirements: 1.9_
  - [ ] 5.4 `PreviewTombstones` + the test against `expected.json`
    - _Requirements: 1.2_
  - [ ] 5.5 Component tests for 5.1–5.3
    - _Requirements: 1.3–1.9_

- [ ] 6. Polling hook and loading state
  - [ ] 6.1 `useAnalysis`: cadence, visibility pause, 10-minute give-up, items fetch on `done`, `analysis_not_ready` race
    - _Requirements: 2.1, 2.4, 2.5_
  - [ ] 6.2 `DiggingState` with phase copy and `aria-live`
    - _Requirements: 2.2, 2.3_

- [ ] 7. Tombstone and grid
  - [ ] 7.1 `Badge` and `Tombstone` (button, headstone shape, text for verdict and confidence, accessible name, focus ring)
    - _Requirements: 3.3, 3.4, 11.2, 11.4_
  - [ ] 7.2 `TombstoneGrid` with the breakpoints
    - _Requirements: 3.3, 11.1_

- [ ] 8. Graveyard screen
  - [ ] 8.1 `GraveyardView` state machine; header with repo, branch, commit, actions
    - _Requirements: 3.1_
  - [ ] 8.2 `StatsBar`
    - _Requirements: 3.2_
  - [ ] 8.3 `Notice`s: warnings, sample note, tests note, "showing first N"
    - _Requirements: 3.6–3.9_
  - [ ] 8.4 Render the grid in batches of 200 with "Show 200 more"; component test with 450 items
    - _Requirements: 3.10_

- [ ] 9. Empty, failed, expired and network-error states
  - `StateMessage`; "Dig again" for retryable failures and for expired links with `repo`; error from a re-dig shown in place
  - One component test per state
  - _Requirements: 5.1–5.6_

- [ ] 10. Filters
  - `Filters` with counts and `aria-pressed`; URL sync; no-match state with "Clear filters"
  - _Requirements: 4.1–4.4_

- [ ] 11. Detail dialog: content
  - [ ] 11.1 `TombstoneDetail` with native `<dialog>`: open from grid and from `?item=`, close paths, focus return, URL sync
    - _Requirements: 6.1, 6.8, 11.3_
  - [ ] 11.2 Verdict banner, facts list, GitHub links (not for the sample), callers, test status, null and boundary wording
    - _Requirements: 6.2–6.6_
  - [ ] 11.3 `CodeSnippet` with line numbers, inner horizontal scroll, truncation note
    - _Requirements: 6.7, 6.9_

- [ ] 12. Detail dialog: actions
  - [ ] 12.1 `CopyButton` with clipboard fallback
    - _Requirements: 7.7_
  - [ ] 12.2 "Copy deletion diff": enabled, disabled-with-reason, and "anyway" variants
    - _Requirements: 7.1–7.3_
  - [ ] 12.3 `lib/revived.ts` and the "Mark as revived" toggle; tombstone shows "revived by you"; stats update
    - _Requirements: 7.4, 7.5, 7.8, 3.5_
  - [ ] 12.4 "Copy link" with `item`
    - _Requirements: 7.6_

- [ ] 13. Component tests for the dialog
  - Fields render; disabled diff cases; Escape returns focus; revive persists across remount
  - _Requirements: 6.1–6.8, 7.1–7.5_

- [ ] 14. Export screen
  - `ExportView`: fetch with `revived`, `<pre>`, Copy Markdown, Download .md, Back; error states
  - _Requirements: 8.1–8.3_

- [ ] 15. Share link
  - "Copy link" on the Graveyard header including filters; check in a private window against the local backend
  - _Requirements: 9.1, 9.2_

- [ ] 16. Full-loop check on the sample repo (local)
  - Landing → sample → grid → detail → copy diff → mark revived → export → download. Fix what breaks
  - _Requirements: all P0_

- [ ] 17. Mobile pass
  - 360 px and 390 px in device emulation and one real phone: no horizontal scroll, two-column grid, full-screen dialog, 44 px targets
  - _Requirements: 11.1, 11.4_

- [ ] 18. Keyboard and screen-reader pass
  - Landing to Export with the keyboard only; headings, landmarks, titles; one pass with a screen reader on the grid and dialog
  - _Requirements: 11.2, 11.3, 11.5, 11.6_

- [ ] 19. Judge checklist on production
  - Run every "Judge check" in `requirements.md` on the live URL; record pass/fail in `docs/judge-checklist.md`; each must fit its stated time and all together under 2 minutes per feature
  - _Requirements: all P0_

- [ ]* 20. (P1, needs owner approval) Age filter and sorting
  - _Requirements: 12.1_

- [ ]* 21. (P1, needs owner approval) Diff preview in the dialog
  - _Requirements: 12.2_

- [ ]* 22. (P1, needs owner approval) Copy button per tombstone; zombie-test label
  - _Requirements: 12.3, 12.4_
