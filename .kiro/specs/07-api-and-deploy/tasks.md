# Implementation Plan: 07 API and Deploy

Tasks 1–3 happen on day 1 (walking skeleton in production). Tasks 4–9 on day 7, after the accuracy gate. Tasks 10–14 on day 11.

- [ ] 1. Hosting spike (timebox: 90 minutes)
  - Re-read Render's and Vercel's current free-tier terms; note RAM, CPU, sleep behaviour and proxy timeout in `docs/open-decisions.md` under D10
  - If Render's free web service no longer exists or needs a card, stop and ask the owner
  - _Requirements: 10.1_

- [ ] 2. Backend skeleton in production
  - [ ] 2.1 `main.py` app factory with `GET /api/health` (static values for now)
    - _Requirements: 9.1_
  - [ ] 2.2 `backend/Dockerfile` (git, non-root, one worker), `.dockerignore`, `render.yaml`
    - _Requirements: 10.1, 10.2_
  - [ ] 2.3 Deploy to Render; confirm `/api/health` answers and `git --version` works in the container
    - _Requirements: 10.1_

- [ ] 3. Frontend skeleton in production
  - `create-next-app` in `web/` (TypeScript, App Router, no Tailwind); `/api/*` rewrite; a placeholder page that fetches `/api/health` and prints it
  - Deploy to Vercel with `BACKEND_URL`; confirm the page shows the Render health JSON
  - Add `LICENSE` and check that no ignore file lists `.kiro`
  - _Requirements: 10.3, 10.4, 10.7_

- [ ] 4. API models and errors
  - [ ] 4.1 Pydantic `Analysis`, `Progress`, `ItemsResponse`, `AnalyzeRequest` as in design "Data Models"
    - _Requirements: 3.1, 4.1_
  - [ ] 4.2 `ApiError`, the Error envelope handlers, the `IngestError` status table, body-size limit
    - _Requirements: 11.1–11.3_
  - [ ] 4.3 Property test P20 (models round-trip)
    - _Requirements: 6.3_

- [ ] 5. Store
  - [ ] 5.1 In-memory dict with lock; create/get/update/finish/fail; `find_by_repo_commit`
    - _Requirements: 1.4, 3.1_
  - [ ] 5.2 JSON persistence, reload at startup, `server_restarted` marking, corrupt-file handling
    - _Requirements: 6.3, 7.3_
  - [ ] 5.3 TTL sweep with an injectable clock; 200-entry eviction
    - _Requirements: 7.1, 7.2, 7.5_
  - [ ] 5.4 Unit tests for 5.1–5.3
    - _Requirements: 7.1–7.5_

- [ ] 6. Job queue
  - [ ] 6.1 One worker thread; `enqueue`; progress callback updates the Store; queue position
    - _Requirements: 6.1, 6.2, 6.5_
  - [ ] 6.2 Failure mapping: `IngestError` codes, `analysis_timeout`, `internal_error`; worker survives every exception
    - _Requirements: 3.4, 6.4_
  - [ ] 6.3 Sample analysis at startup with `sample_ready`; daily recompute
    - _Requirements: 7.4, 9.2_

- [ ] 7. Routes
  - [ ] 7.1 `POST /api/analyze`: body validation, sample path, pre-flight, de-duplication, queue-full check
    - _Requirements: 1.1–1.6_
  - [ ] 7.2 `GET /api/analysis/{id}` and `GET /api/analysis/{id}/items`
    - _Requirements: 3.1–3.3, 4.1–4.4_
  - [ ] 7.3 Rate limiter and its wiring; property test P21
    - _Requirements: 2.1–2.4_
  - [ ] 7.4 API tests: one per row of every error table in `design.md`
    - _Requirements: 1.3, 1.5, 1.6, 2.2, 3.2, 4.2–4.4_

- [ ] 8. Export
  - [ ] 8.1 `render_markdown`: header, warnings, grouping, ordering, checkboxes, escaping
    - _Requirements: 5.2, 5.3, 5.6_
  - [ ] 8.2 `revived` and `download` query parameters; route `GET /api/analysis/{id}/export.md`
    - _Requirements: 5.1, 5.4, 5.5, 5.7_
  - [ ] 8.3 Property tests P11 and P19
    - _Requirements: 5.2–5.4, 5.6_

- [ ] 9. End-to-end API test and local loop
  - Test: sample → analysis → items → export
  - Manual: run the backend locally and `curl` a small public repo through the full loop
  - _Requirements: 1.1, 3.1, 4.1, 5.1_

- [ ] 10. Production deploy of the real API
  - Deploy; run through the sample loop on the Render URL; measure sample analysis time and one ~300-file public repo; adjust limits in `config.py` if needed and record the numbers under D10
  - _Requirements: 10.1, 10.4_

- [ ] 11. Smoke script
  - `scripts/smoke.sh <base-url>`: health, sample loop, invalid URL (400), made-up repo (404)
  - _Requirements: 9.1, 10.4_

- [ ] 12. Keep-warm and CI workflows
  - `.github/workflows/keep-warm.yml` (cron every 10 minutes, direct to Render); extend `ci.yml` with the frontend job
  - _Requirements: 10.5_

- [ ] 13. Request logging and hygiene check
  - One log line per request; grep logs of a failing request to confirm no path, stack trace or token appears in the response
  - _Requirements: 11.2, 11.4_

- [ ] 14. README
  - What it is, live URL, local run steps for backend and frontend (fresh clone, no secrets), limits, known blind spots of the analysis, licence
  - Have a clean checkout in a new folder follow the README word for word
  - _Requirements: 10.6_
