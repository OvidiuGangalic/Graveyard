# Design Document: 06 Graveyard UI

## Overview

```
/                                   Landing            (server component shell + client RepoForm)
/graveyard/[id]                     Graveyard          (client: polling, filters, dialog)
/graveyard/[id]?item=<itemId>       Tombstone detail   (dialog state held in the URL)
/graveyard/[id]/export              Export             (client: fetch Markdown text)
```

All data comes from `/api/*` on the same origin (rewritten to the backend by `next.config.ts`). No server-side data fetching: the graveyard pages are client components because they poll and read `localStorage`. No global state library; state lives in the URL, in component state, and in one `localStorage` key per analysis.

## Screens

### Landing

```
┌──────────────────────────────────────────────┐
│                 GRAVEYARD                    │  h1, serif display
│  Paste a public GitHub repo. See its dead    │
│  code laid to rest.                          │
│  ┌──────────────────────────────┐ ┌────────┐ │
│  │ https://github.com/owner/repo│ │Analyse │ │
│  └──────────────────────────────┘ └────────┘ │
│  [inline error, role=alert]                  │
│            [ Try the sample repo ]           │
│   ▟▙      ▟▙      ▟▙    From the sample repo │  3 preview tombstones
│  No login. Public repos only. Python and     │
│  TypeScript. Nothing from your repo is run.  │
└──────────────────────────────────────────────┘
```

Mobile: input and button stack; preview tombstones in one row, scaled down.

### Graveyard

```
┌──────────────────────────────────────────────────────────────┐
│ owner/repo · main @ 9f2c1e7     [Copy link] [Export] [New dig]│
│ ┌───────────┬───────────┬──────────────────┬───────────────┐ │
│ │ 430 files │ 37 dead   │ 612 lines could  │ oldest ghost  │ │
│ │ scanned   │ items     │ be buried        │ 1,204 days    │ │
│ └───────────┴───────────┴──────────────────┴───────────────┘ │
│ ⚠ warnings (if any)        ℹ "Tests" means a test file ...   │
│ Language: (All 37)(Python 21)(TypeScript 16)                 │
│ Verdict:  (All 37)(Bury 24)(Revive 6)(Unsure 7)              │
│  ▟▙   ▟▙   ▟▙   ▟▙   ▟▙                                      │
│  name file age [high] bury   ...                             │
└──────────────────────────────────────────────────────────────┘
```

States of this screen (exactly one renders): `loading`, `grid`, `empty-clean`, `empty-no-files`, `failed`, `expired`, `network-error`.

### Tombstone detail (dialog)

```
┌────────────────────────────────────────────── ✕ ┐
│ export_legacy_csv        function · python       │
│ ┌──────────────────────────────────────────────┐ │
│ │ BURY IT · high confidence                    │ │
│ │ No references anywhere in this repo, ...     │ │
│ └──────────────────────────────────────────────┘ │
│ File      inventory/reports.py, lines 42–58  ↗   │
│ Last touched  1 Dec 2024 by Morticia Graves (1b2c3d4 ↗) │
│ Age       730 days                               │
│ Callers   None found                             │
│ Tests     No test file mentions it               │
│ ┌ code ────────────────────────────────────────┐ │
│ │ 42  def export_legacy_csv(rows, path):       │ │
│ └──────────────────────────────────────────────┘ │
│ [Copy deletion diff] [Mark as revived] [Copy link]│
└──────────────────────────────────────────────────┘
```

Implemented with the native `<dialog>` element and `showModal()`, which provides the focus trap, Escape handling and inert background without a dependency.

### Export

Header with repo name; a `<pre>` block with the Markdown source; three actions (Copy Markdown, Download .md, Back to the graveyard).

## Components and Interfaces

| Component | Props (main) | Notes |
|---|---|---|
| `RepoForm` | – | Input, two buttons, inline error, health wake-up notice |
| `PreviewTombstones` | – | Static, `aria-hidden` decorative shapes + a visible caption |
| `GraveyardView` | `id` | Owns the screen state machine; uses `useAnalysis` |
| `DiggingState` | `analysis` | Loading copy by phase, `aria-live` |
| `StatsBar` | `analysis, items, revivedIds` | Uses `lib/stats.ts` |
| `Filters` | `counts, value, onChange` | Buttons with `aria-pressed` |
| `TombstoneGrid` | `items, revivedIds, onOpen` | CSS grid |
| `Tombstone` | `item, revived, onOpen` | A `<button>`; CSS-shaped headstone |
| `TombstoneDetail` | `item, analysis, revived, onToggleRevived, onClose` | `<dialog>` |
| `CodeSnippet` | `code, startLine` | `<pre>` with a line-number gutter |
| `Badge` | `kind: "confidence" \| "verdict", value` | Text + token colour |
| `Notice` | `tone: "warning" \| "info"` | Warnings and the tests note |
| `StateMessage` | `title, body, actions` | Empty, failed, expired, network-error |
| `CopyButton` | `getText, label, doneLabel` | Clipboard with fallback box |
| `ExportView` | `id` | |

`web/lib/`:

| Module | Exports | Pure |
|---|---|---|
| `types.ts` | `Analysis`, `DeadItem`, `Caller`, `LastCommit`, `Progress`, `ApiErrorBody` (mirror of spec 07) | – |
| `api.ts` | `startAnalysis`, `startSample`, `getAnalysis`, `getItems`, `getExportMarkdown`, `getHealth`; all throw `ApiError {status, code, message}` | no |
| `useAnalysis.ts` | hook: polling with the cadence of Requirement 2.1, visibility pause, returns `{state, analysis, items, error}` | no |
| `diff.ts` | `buildDeletionDiff(item): string` | yes |
| `filters.ts` | `applyFilters(items, f)`, `countBy(items)`, `parseFilters(searchParams)`, `toQuery(f)` | yes |
| `stats.ts` | `computeStats(analysis, items, revivedIds)` | yes |
| `revived.ts` | `loadRevived(id)`, `saveRevived(id, set)` with in-memory fallback | no |
| `format.ts` | `formatAge(item)`, `shortHash`, `formatDate`, `githubBlobUrl`, `githubCommitUrl`, `ariaLabel(item)` | yes |

### Deletion diff format (`diff.ts`)

For an item with `file_path = P`, `start_line = s`, `end_line = e`, `n = e − s + 1`, and snippet lines `L1..Ln`:

```
--- a/P
+++ b/P
@@ -s,n +s',0 @@
-L1
...
-Ln
```

where `s' = s − 1`. Lines are joined with `\n` and the text ends with a newline. This is a zero-context unified diff against the analysed commit; it applies with `git apply --unidiff-zero`. The confirmation message says so. A snippet line is emitted verbatim after the `-`; nothing is trimmed.

## Design tokens (`globals.css`)

| Token | Value | Use |
|---|---|---|
| `--color-bg` | `#0a0d0b` | page background |
| `--color-bg-raised` | `#121713` | cards, dialog, stats bar |
| `--color-stone` | `#2a312c` | tombstone face |
| `--color-stone-edge` | `#3d463f` | borders |
| `--color-bone` | `#ece7d9` | primary text |
| `--color-bone-dim` | `#a9a595` | secondary text |
| `--color-green` | `#7ddc8b` | accent: links, focus ring, primary button, `high` badge |
| `--color-green-deep` | `#1f3d27` | primary button background, selected filter |
| `--color-fog` | `rgba(125, 220, 139, 0.07)` | fog layers |
| `--color-amber` | `#e0b354` | `medium` badge, warnings |
| `--color-ash` | `#aab0b5` | `low` badge |
| `--color-blood` | `#e8806f` | errors |
| `--font-display` | Cormorant Garamond, Georgia, serif | h1–h3, verdict banner |
| `--font-body` | system-ui, -apple-system, "Segoe UI", sans-serif | body, buttons |
| `--font-mono` | JetBrains Mono, ui-monospace, Consolas, monospace | names, paths, code |
| `--text-xs … --text-3xl` | 0.75, 0.875, 1, 1.25, 1.75, 2.5, 3.5 rem | type scale |
| `--space-1 … --space-8` | 4, 8, 12, 16, 24, 32, 48, 64 px | spacing |
| `--radius-sm`, `--radius-md`, `--radius-tomb` | 4 px, 8 px, `48% 48% 6px 6px / 28% 28% 6px 6px` | corners; headstone top |
| `--focus-ring` | `2px solid var(--color-green)` with 2 px offset | every focusable element |
| `--shadow-raise` | `0 8px 24px rgba(0, 0, 0, 0.5)` | dialog |

Contrast targets (checked in task 3): bone on bg, bone-dim on bg, green on bg, amber on bg-raised, ash on stone, blood on bg; all ≥ 4.5:1. If a pair fails, adjust the foreground token and update this table.

Breakpoints: `< 360` one grid column; `360–599` two columns, dialog full-screen; `600–899` three to four columns; `≥ 900` auto-fill at min 190 px.

Fog: two fixed, blurred radial-gradient layers drifting with a 60 s CSS animation; `@media (prefers-reduced-motion: reduce)` sets `animation: none`.

## Error Handling

| Situation | Screen state | Copy source |
|---|---|---|
| `POST /api/analyze` 4xx/5xx | inline under input | `error.message` from the API |
| Network failure on any call | inline (Landing) or `network-error` state with Retry | fixed copy |
| Analysis `failed` | `failed` | `error_message` |
| `GET analysis` 404 | `expired` | fixed copy + optional "Dig again" |
| `GET items` 409 `analysis_not_ready` (race) | stay in `loading`, poll again | – |
| Response is not JSON (proxy error page) | treated as network failure | fixed copy |
| `item` query names an unknown item | grid opens, dialog does not; `item` removed from URL | – |
| Clipboard denied | fallback selectable box | fixed copy |

Polling gives up after 10 minutes with the `network-error` state ("This dig is taking too long. Retry").

## Correctness Properties (fast-check)

- **Property P12 (the diff deletes exactly the item).** For any generated file of 1–300 lines and any range `[s, e]` within it, applying the diff built from that range (with a small in-test zero-context patch applier) yields the file without lines `s..e`, and every body line of the diff starts with `-`. **Validates: Requirement 7.1.**
- **Property P22 (filters partition).** For any generated item list: `applyFilters` returns a sub-list preserving order; with both filters "All" it returns every item; the per-verdict counts sum to the total, as do the per-language counts; `parseFilters(toQuery(f))` equals `f`. **Validates: Requirements 4.1, 4.2.**
- **Property P23 (stats are consistent).** For any generated item list and revived set: "lines that could be buried" equals the sum of line counts of non-revived `bury` items and never increases when an item is added to the revived set; "oldest ghost" is ≥ every non-null `age_days`. **Validates: Requirement 3.2.**

## Testing Strategy

- Vitest + Testing Library: `RepoForm` (each error path with a mocked `fetch`), `GraveyardView` state machine (one test per state), `TombstoneDetail` (fields, disabled diff cases, focus return), `Filters` (URL sync).
- A test that the Landing preview items equal three entries of `samples/haunted-repo/expected.json` (read at test time).
- Type mirror check: a script test that the keys of `DeadItem` and `Analysis` in `types.ts` equal the keys in a JSON schema dumped by the backend (`python -m graveyard.cli schema`), so the two sides cannot drift.
- Manual checklist (task 19): the judge checks of every requirement, run on production, on a laptop and on a phone, keyboard only once.
