# Implementation Plan: 08 Demo and Submission

Task 0 runs throughout the build. Tasks 1–3 on Wed 2 Dec, 4–9 on Thu 3 Dec, 10 on Fri 4 Dec.

- [ ] 0. Keep the Kiro log (every build day, 2 minutes)
  - One line per session in `docs/kiro-log.md`: date, spec task, what Kiro did, anything notable (a bug a property caught, a hook that fired usefully, a spec that had to change), commit hash
  - Save screenshots of notable moments into `docs/media/`
  - _Requirements: 4.4_

- [ ] 0.1 Request Kiro credits (do this before 21 Nov; hard deadline Tue 1 Dec 12:00 PT)
  - _Requirements: 5.6_

- [ ] 1. Accuracy sweep
  - [ ] 1.1 Write the list of 5+ repos into `docs/accuracy.md` before running any of them
    - _Requirements: 1.1_
  - [ ] 1.2 Run each on production; save exports under `docs/sweep/`
    - _Requirements: 1.1_
  - [ ] 1.3 Hand-check the first 10 `bury / high` items per repo; fill the table; compute precision with its sample size
    - _Requirements: 1.2, 1.3_

- [ ] 2. Act on the sweep
  - Add each false positive to the regression corpus; fix the rule or document the blind spot in the README; re-run the gate
  - Timebox: 3 hours. Anything not fixed in that time is documented, not fixed
  - _Requirements: 1.4, 1.6_

- [ ] 3. Choose the demo repo
  - One with a clear `bury / high` and a clear `revive`, analysed in under 15 s; note the two tombstones to open
  - _Requirements: 2.2_

- [ ] 4. Capture Kiro footage
  - The eight shots in the shot list: spec tree, EARS criterion, property in design, property test, gate red, gate green, hook run, agent list
  - _Requirements: 2.3_

- [ ] 5. Record the app walkthrough
  - Warm the backend; follow the script rows 0:00–1:45 and 2:25–2:40 on production; read numbers from the screen
  - _Requirements: 2.2, 2.4, 2.5_

- [ ] 6. Edit and publish the video
  - Cut to under 2:59; captions or narration on every step; upload as public; app and repo URLs in the description; watch it once logged out
  - _Requirements: 2.1, 2.5, 2.6_

- [ ] 7. Write the Kiro write-up
  - `docs/kiro-writeup.md` from the outline and `docs/kiro-log.md`; every example has a path or commit hash; remove any section for a feature that was not used
  - _Requirements: 4.1–4.3, 4.5_

- [ ] 8. Write the Devpost description
  - From the outline; numbers only from `docs/accuracy.md`; limits stated; three links
  - _Requirements: 3.1–3.4, 1.5_

- [ ] 9. Submit a complete draft
  - Fill every Devpost field including student details; save as draft or submit if edits are allowed until the deadline
  - _Requirements: 5.4_

- [ ] 10. Final submission
  - [ ] 10.1 Walk `docs/submission-checklist.md` top to bottom, ticking each box only after checking it
    - _Requirements: 5.1, 5.2, 5.5_
  - [ ] 10.2 Run `scripts/smoke.sh` on production
    - _Requirements: 5.3_
  - [ ] 10.3 Submit by 20:00 CET; confirm the email arrived; no deploys afterwards
    - _Requirements: 5.1_
