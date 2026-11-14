# Requirements Document: 06 Graveyard UI

## Introduction

The UI is a Next.js app with four screens: Landing, Graveyard (grid), Tombstone detail (a dialog over the grid) and Export. It shows only what the API returns. The theme is a haunted graveyard; the data is presented plainly and every caveat the backend reports is visible.

This spec must not be started until the accuracy gate (spec 05 Requirement 6) is green.

Priority: P0 (Requirements 1–11), P1 (Requirement 12).

## Glossary

- **App**: the Next.js application in `web/`.
- **Tombstone**: one DeadItem rendered as a card in the grid.
- **Exhume**: open a Tombstone's detail.
- **Locally revived**: an item the user has marked "revived" in this browser; stored in `localStorage`, never sent to the server except as the `revived` export parameter.
- **Share link**: `/graveyard/{id}?repo={owner}/{repo}`.

## Requirements

### Requirement 1: Landing

**User Story:** As a visitor, I want to understand the product and start in one action, so that I get value in seconds.

#### Acceptance Criteria

1. THE Landing screen SHALL show: the name "Graveyard"; the line "Paste a public GitHub repo. See its dead code laid to rest."; one text input labelled "GitHub repo URL"; an "Analyse" button; a "Try the sample repo" button; three preview Tombstones; and the note "No login. Public repos only. Python and TypeScript. Nothing from your repo is ever run."
2. THE three preview Tombstones SHALL show three real items from the sample repo's ground truth, captioned "From the sample repo", and SHALL NOT be interactive.
3. WHEN the user submits the form (button or Enter), THE App SHALL call `POST /api/analyze` with the trimmed input and, on `200` or `202`, navigate to the Share link for the returned id.
4. WHEN the user clicks "Try the sample repo", THE App SHALL call `POST /api/analyze` with `sample: true` and navigate to `/graveyard/sample`.
5. WHILE a submit request is in flight, THE App SHALL disable both buttons and show "Opening the gates…".
6. IF the API returns an error, THEN THE App SHALL show the API's `error.message` directly under the input in an element with `role="alert"`, keep the input's value, and return focus to the input.
7. IF the request fails without a response (network error), THEN THE App SHALL show "Could not reach the graveyard. Check your connection and try again."
8. IF the input is empty on submit, THEN THE App SHALL show "Paste a GitHub repo URL first." without calling the API.
9. WHEN the Landing screen loads, THE App SHALL call `GET /api/health`; IF no answer arrives within 2 seconds, THEN THE App SHALL show "Waking the gravedigger… the first dig may take a minute." until an answer arrives.
10. THE Landing screen SHALL have no login, sign-up, cookie banner or tracking.

Judge check (30 s): open the app URL. One input, two buttons, three tombstones and no login are visible without scrolling on a laptop.

### Requirement 2: Loading state

**User Story:** As a user, I want to see that the dig is progressing, so that I do not leave.

#### Acceptance Criteria

1. WHILE the Analysis status is `queued` or `running`, THE Graveyard screen SHALL poll `GET /api/analysis/{id}` every 1.5 seconds for the first 60 seconds and every 3 seconds after that.
2. THE loading state SHALL show the repo name, the heading "Digging up…", and a line chosen by `progress.phase`: `queued` → "Waiting for a shovel (position N in the queue)"; `cloning` → "Opening the gates…"; `scanning` → "Counting headstones…"; `python`/`typescript` → "{total_files_scanned} of {files_discovered} files exhumed"; `history` → "Reading the epitaphs…"; `verdicts` → "Passing judgement…".
3. THE loading state SHALL announce phase changes through an `aria-live="polite"` region.
4. WHEN the status becomes `done`, THE App SHALL fetch the items and show the grid without a page reload.
5. THE App SHALL stop polling when the screen is left or the browser tab is hidden, and resume when it is visible again.

Judge check (60 s): paste a small public repo URL and click Analyse. A "Digging up…" screen appears with a file count that increases, then the grid.

### Requirement 3: Graveyard grid

**User Story:** As a developer, I want to scan all dead items at once, so that I can see the size of the problem and pick where to start.

#### Acceptance Criteria

1. THE Graveyard screen SHALL show a header with the repo name, branch and 7-character commit, a "Copy link" button, an "Export cleanup plan" link and a "New dig" link to Landing.
2. THE stats bar SHALL show four figures computed from the items: files scanned (`total_files_scanned`); dead items (`total_dead_items`); lines that could be buried (sum of `end_line − start_line + 1` over items with verdict `bury` that are not Locally revived); oldest ghost (the largest `age_days`, with the item's name, prefixed "at least" when that item's commit is a boundary commit, or "unknown" when no item has an age).
3. THE grid SHALL render every item passing the active filters as a Tombstone showing: name; file path; age ("730 days", "at least 730 days", or "age unknown"); a confidence badge with the word `high`, `medium` or `low`; and the verdict word.
4. EACH Tombstone SHALL convey verdict and confidence in text, never by colour alone.
5. WHEN an item is Locally revived, ITS Tombstone SHALL show "revived by you" in place of the verdict word.
6. WHEN the Analysis has warnings, THE Graveyard screen SHALL show each warning above the grid.
7. WHEN the Analysis `is_sample`, THE screen SHALL show the sample warning (scripted history) above the grid.
8. THE Graveyard screen SHALL show, once, the note "'Tests' means a test file mentions the name. Graveyard does not run your tests."
9. WHEN `total_dead_items` exceeds the number of items returned, THE screen SHALL say "Showing the first {returned} of {total}".
10. WHEN more than 200 items pass the filters, THE grid SHALL render the first 200 and a "Show 200 more" button that appends the next 200, so that a repo with thousands of items stays responsive (the backend has no item limit by default). The stats bar and filter counts SHALL always cover all items.

Judge check (20 s): on the sample graveyard, count four figures in the stats bar and at least 12 tombstones, each with a name, a file, an age and a badge.

### Requirement 4: Filters

#### Acceptance Criteria

1. THE Graveyard screen SHALL offer a language filter (All, Python, TypeScript) and a verdict filter (All, Bury, Revive, Unsure), each showing the count of matching items.
2. WHEN a filter changes, THE grid SHALL update without a network request, and the filter state SHALL be written to the URL query (`lang`, `verdict`) so that a copied link reproduces the view.
3. WHEN no item matches the active filters, THE grid SHALL show "Nothing buried here. Try clearing the filters." and a "Clear filters" button.
4. THE filters SHALL be native form controls or buttons with `aria-pressed`, operable by keyboard.

Judge check (15 s): click "Python" then "Bury"; the tombstone count drops and every remaining tombstone says `bury`.

### Requirement 5: Empty, failed and expired states

#### Acceptance Criteria

1. WHEN the Analysis is `done` with zero items and `total_files_scanned > 0`, THE screen SHALL show "No ghosts found. Suspiciously clean repo." with the number of files scanned.
2. WHEN the Analysis is `done` with `total_files_scanned == 0`, THE screen SHALL show "No Python or TypeScript files found in this repo."
3. WHEN the Analysis is `failed`, THE screen SHALL show the heading "The dig failed", the `error_message`, and a "Try another repo" link; for `error_code` `server_restarted`, `analysis_timeout` or `github_unavailable` it SHALL also show a "Dig again" button that resubmits the same repo URL.
4. WHEN `GET /api/analysis/{id}` returns `404`, THE screen SHALL show "This graveyard has been filled in. Analyses are kept for 24 hours."; IF the URL has a `repo` parameter, THEN it SHALL also show a "Dig again" button that submits `https://github.com/{repo}`.
5. WHEN a "Dig again" request returns an API error, THE screen SHALL show that error's message in place.
6. EVERY error state SHALL have a way back to Landing.

Judge check (45 s): paste a private or made-up repo URL → inline "private or does not exist". Paste `https://github.com/torvalds/linux` → "too large". Paste `hello` → "does not look like a GitHub repo URL".

### Requirement 6: Tombstone detail

**User Story:** As a developer, I want all the evidence for one item in one place, so that I can decide whether to delete it.

#### Acceptance Criteria

1. WHEN a Tombstone is activated, THE App SHALL open a modal dialog and add `item={id}` to the URL; WHEN a Graveyard URL with `item` is loaded, THE dialog for that item SHALL open once items have loaded.
2. THE dialog SHALL show: name, kind and language; a verdict banner reading "BURY IT", "REVIVE IT" or "UNSURE" with the confidence and the `verdict_reason`; file path and line range; last commit date, author and 7-character hash; age; callers found; test status; and the code snippet with line numbers starting at `start_line`.
3. WHEN the Analysis is not the sample, THE file path SHALL link to `{repo_url}/blob/{commit_analysed}/{file_path}#L{start}-L{end}` and the hash to `{repo_url}/commit/{hash}`, both opening in a new tab.
4. THE callers section SHALL list each caller as "{kind label} at {file}:{line}" with its snippet, or "None found" when empty; kind labels: `test_reference` → "Test", `string_match` → "Name in a string", `dynamic_import` → "Dynamic import", `reexport` → "Re-export".
5. THE test status SHALL read "A test file mentions it", "No test file mentions it" or "No tests found for this language", by `test_coverage`.
6. WHEN `last_commit` is null, THE dialog SHALL show "Git history unavailable" for commit and age; WHEN `is_boundary` is true, THE age SHALL read "at least N days".
7. WHEN `snippet_truncated` is true, THE dialog SHALL say "Showing the first 200 lines of {total}".
8. THE dialog SHALL close on Escape, on its close button and on a click outside it; on close, focus SHALL return to the Tombstone that opened it and `item` SHALL be removed from the URL.
9. THE code snippet SHALL scroll horizontally inside its own box and SHALL NOT cause the page to scroll horizontally.

Judge check (20 s): click `export_legacy_csv`; a panel shows BURY IT, a one-sentence reason, a file and lines, an author and date, and the code.

### Requirement 7: Detail actions

#### Acceptance Criteria

1. THE dialog SHALL have a "Copy deletion diff" button that copies a unified diff removing lines `start_line` to `end_line` of `file_path`, built from `code_snippet` in the format given in `design.md`, and then shows "Copied. Apply with: git apply --unidiff-zero".
2. WHEN `deletable_as_whole_lines` is false or `snippet_truncated` is true, THE button SHALL be disabled with the visible explanation "This import shares its line with names still in use; remove it by hand." or "Too long to copy as a diff; delete lines {start}–{end} by hand."
3. WHEN the verdict is `revive` or `unsure`, THE button SHALL be labelled "Copy deletion diff anyway" and styled as secondary.
4. THE dialog SHALL have a "Mark as revived" toggle that adds or removes the item id in `localStorage` under `graveyard:revived:{analysis_id}`; the label SHALL read "Unmark revived" when set.
5. THE App SHALL make no network request when an item is marked or unmarked, and the mark SHALL survive a page reload in the same browser.
6. THE dialog SHALL have a "Copy link" button that copies the Share link with `item={id}`.
7. IF the Clipboard API is unavailable or refuses, THEN THE App SHALL show the text in a selectable box with the message "Select and copy".
8. IF `localStorage` is unavailable, THEN the mark SHALL be kept in memory for the session and the App SHALL NOT throw.

Judge check (20 s): click "Copy deletion diff", paste into any text field: lines beginning with `-`. Click "Mark as revived", reload: the tombstone still says "revived by you".

### Requirement 8: Export screen

#### Acceptance Criteria

1. THE Export screen at `/graveyard/{id}/export` SHALL fetch `/api/analysis/{id}/export.md` with the Locally revived ids in `revived` and show the Markdown source in a scrollable monospace block.
2. THE screen SHALL have "Copy Markdown", "Download .md" (a link to the same URL with `download=1`) and "Back to the graveyard".
3. THE error cases of Requirement 5.3 and 5.4 SHALL apply.

Judge check (15 s): click "Export cleanup plan"; a Markdown document grouped by file appears; "Download .md" saves a file.

### Requirement 9: Shareable URL

#### Acceptance Criteria

1. "Copy link" on the Graveyard screen SHALL copy the Share link including the active filters.
2. WHEN a Share link is opened in another browser within 24 hours, THE same graveyard SHALL load with no login.

Judge check (15 s): click "Copy link", open it in a private window; the same graveyard appears.

### Requirement 10: Design tokens and theme

#### Acceptance Criteria

1. THE App SHALL define every colour, font family, font size, spacing step, radius and shadow as CSS custom properties in `web/app/globals.css`, with the values in `design.md`, and components SHALL use only those properties.
2. THE App SHALL use a dark background, bone-white text and a graveyard-green accent; a serif display font for headings; a monospace font for code, names and paths.
3. EVERY text/background pair SHALL have a contrast ratio of at least 4.5:1 (3:1 for text of 24 px and larger).
4. THE fog effect SHALL be CSS only and SHALL NOT animate when `prefers-reduced-motion: reduce` is set.
5. Theme copy ("exhume", "bury", "revive", "ghost") SHALL appear in headings, buttons and states; facts (paths, dates, counts, reasons) SHALL be stated plainly.

### Requirement 11: Mobile and accessibility

#### Acceptance Criteria

1. AT a viewport width of 360 px, EVERY screen SHALL be usable with no horizontal page scroll; the grid SHALL show two columns from 360 px and one column below; the detail dialog SHALL be full-screen below 600 px.
2. EVERY Tombstone SHALL be a `<button>` reachable by Tab in reading order, activated by Enter or Space, with a visible focus ring and an accessible name of the form "{name}, {kind} in {file_path}, {age}, {verdict}, {confidence} confidence".
3. THE detail dialog SHALL trap focus while open and SHALL be labelled by the item name.
4. EVERY interactive element SHALL have a touch target of at least 44 × 44 px.
5. THE App SHALL be operable from Landing to Export using the keyboard alone.
6. EVERY page SHALL have one `<h1>`, a `<main>` landmark and a descriptive `<title>`.

Judge check (30 s): on the sample graveyard press Tab until a tombstone is outlined, press Enter (detail opens), press Escape (focus returns to the same tombstone). Open the app on a phone: everything fits.

### Requirement 12 (P1, do not start without owner approval)

#### Acceptance Criteria

1. THE Graveyard screen SHALL offer an age filter (All, older than 180 days, older than 1 year, older than 2 years) and a sort control (default, oldest first, largest first).
2. THE dialog SHALL render the deletion diff as a preview with removed lines marked.
3. EACH Tombstone SHALL have a copy button that copies `{file_path}:{start_line}-{end_line}`.
4. THE grid SHALL show Tombstones of kind `test` with the label "zombie test".

## Assumptions (flagged; see docs/open-decisions.md)

- A1. The brief lists "filter by language / verdict / age" under the Graveyard screen but "dead-code age filter and sorting" under P1. Language and verdict filters are P0; the age filter and sorting are P1. See D12.
- A2. The brief lists "Copy deletion diff" on the detail screen but "deletion diff preview" and "copy-to-clipboard per tombstone" under P1. Copying the diff from the detail dialog is P0; the rendered preview and the per-card copy button are P1. See D12.
- A3. Detail is a dialog over the grid with a deep link (`?item=`), not a separate page, so the grid keeps its scroll position and filters.
- A4. Body text uses the system UI font stack; only headings (serif) and code (monospace) load web fonts. Proposed fonts: Cormorant Garamond and JetBrains Mono via `next/font/google`. See D13.
- A5. The preview Tombstones on Landing are hard-coded copies of three sample ground-truth items. A test asserts they match `samples/haunted-repo/expected.json`, so they cannot drift into fiction.
- A6. No syntax highlighting in P0 (it would need a dependency).
