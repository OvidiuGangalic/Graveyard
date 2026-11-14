# Requirements Document: 08 Demo and Submission

## Introduction

This spec covers everything a judge sees that is not the app itself: the accuracy evidence, the demo video, the Devpost description, the write-up on how Kiro was used, and the submission checklist. Presentation is 20% of the score and depth of Kiro use is another 20%, so these are deliverables with acceptance criteria, not afterthoughts.

Deadline: Fri 4 Dec 2026, 14:00 PT (23:00 CET). Target: complete draft submitted Thu 3 Dec; final submit by 20:00 CET on 4 Dec.

Priority: P0.

## Glossary

- **Sweep**: running Graveyard on real public repos and hand-checking a sample of its `bury / high` items.
- **Write-up**: the "how Kiro was used" text required by the hackathon.

## Requirements

### Requirement 1: Accuracy evidence

**User Story:** As a judge, I want to know whether the results can be trusted, so that I can score impact honestly.

#### Acceptance Criteria

1. THE owner SHALL run Graveyard on at least 5 public repos (at least 2 mostly Python, at least 2 mostly TypeScript), chosen before looking at their results.
2. FOR each repo, THE owner SHALL hand-check up to 10 `bury / high` items by searching the repo for the name, and record each as truly dead, false positive or cannot tell.
3. `docs/accuracy.md` SHALL list the repos, commits, item counts by verdict, the hand-check results and the resulting precision for `bury / high`, including the false positives found.
4. EVERY false positive found SHALL be added to the regression corpus (spec 02 task 10 / spec 03) and either fixed or listed under "Known blind spots" in the README.
5. THE README, the Devpost text and the video SHALL quote only numbers that appear in `docs/accuracy.md`.
6. IF precision for `bury / high` is below 90% after fixes, THEN THE owner SHALL say so in the README and SHALL NOT describe `high` as "safe to delete" anywhere.

### Requirement 2: Demo video

**User Story:** As a judge, I want to see the whole loop in under three minutes.

#### Acceptance Criteria

1. THE video SHALL be shorter than 3 minutes (target 2:40), public on YouTube, with the app URL and repo URL in the description.
2. THE video SHALL show, on the production URL: pasting a real public repo URL; the loading state; the grid and stats bar; one `bury` tombstone exhumed; one `revive` tombstone exhumed with its reason; copying a deletion diff; the export; and the share link opened in a second window.
3. THE video SHALL show Kiro for at least 30 seconds: a spec (requirements → design → tasks), a hook firing, and the accuracy gate or a property test failing then passing.
4. THE video SHALL follow the script in `design.md`; any change to the script SHALL keep criteria 2 and 3 satisfied.
5. THE video SHALL have readable text at 1080p and narration or captions for every step.
6. THE video SHALL contain no copyrighted music and no third-party trademarks beyond GitHub repo pages shown in normal use.

### Requirement 3: Devpost description

#### Acceptance Criteria

1. THE description SHALL follow the outline in `design.md`: inspiration, what it does, how it was built, how Kiro was used, challenges, accomplishments, what was learned, what is next.
2. THE description SHALL state the category (Frankenstein), name the stitched-together parts (Python `ast`, tree-sitter, git history, GitHub API, FastAPI, Next.js), and explain why they form one product.
3. THE description SHALL state the limits honestly: public repos, Python and TypeScript, static analysis, size limits, 24-hour retention.
4. THE description SHALL include the app URL, the repo URL and the video URL.

### Requirement 4: Kiro write-up

**User Story:** As a judge scoring Technological Implementation, I want concrete evidence of how deeply Kiro was used.

#### Acceptance Criteria

1. THE Write-up SHALL cover, each with at least one concrete example taken from this repo's history: spec-driven development; steering; agent hooks; MCP; custom agents (and Kiro Crew if used); property-based testing from specs; powers; and vibe coding versus specs (where each was used and why).
2. EVERY example SHALL point to a file path in `/.kiro` or a commit hash.
3. THE Write-up SHALL include one example where Kiro was wrong or a spec had to change, and what was done.
4. THE owner SHALL keep a running log `docs/kiro-log.md` during the build (date, what Kiro did, what was notable), one line per session, as raw material.
5. THE Write-up SHALL NOT claim use of a Kiro feature that was not used.

### Requirement 5: Submission checklist

#### Acceptance Criteria

1. THE checklist in `design.md` SHALL be completed and committed as `docs/submission-checklist.md` with every box ticked before final submission.
2. THE repo SHALL be public on GitHub, with an OSI-approved licence file at the root and the `/.kiro` directory present and not ignored.
3. THE app URL SHALL pass `scripts/smoke.sh` within one hour before submission.
4. THE Devpost entry SHALL include the student details needed for Best Student Project.
5. THE repo history SHALL show that the project was built inside the submission period (first commit on or after 30 Oct 2026).
6. THE Kiro credit request SHALL be filed before Tue 1 Dec 2026 12:00 PT.

## Assumptions (flagged; see docs/open-decisions.md)

- A1. The demo repo for the video is chosen during the Sweep (a repo with at least one clear `bury / high` and one clear `revive`). It is not chosen now, because results on real repos are not known yet. See D14.
- A2. Exact Devpost form fields and the student-verification requirement are read from the hackathon page at submission time; the checklist lists what the brief states.
