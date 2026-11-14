# Requirements Document: 01 Repo Ingestion

## Introduction

Repo ingestion turns a user's input (a GitHub URL, or "use the sample repo") into a `RepoSnapshot`: a folder on disk with a known commit, a list of source files to analyse, and enough git history for archaeology. It enforces every size and time limit, and it owns the two sample repos that prove the analysers are accurate.

Priority: P0.

## Glossary

- **Ingestor**: the backend component specified here (`backend/graveyard/ingestion/`).
- **RepoSnapshot**: the Ingestor's output; defined in `design.md`.
- **Source file**: a file with extension `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs` or `.cjs` that is not excluded by the walker rules.
- **Text-reference file**: a non-source file that analysers scan for name mentions (config and template files).
- **Haunted repo**: the known-dead sample at `samples/haunted-repo/`.
- **Living repo**: the known-live sample at `samples/living-repo/`.
- **Canonical URL**: `https://github.com/{owner}/{repo}`, no trailing slash, no `.git`.

## Requirements

### Requirement 1: URL validation and normalisation

**User Story:** As a developer, I want to paste a GitHub link in whatever form I copied it, so that I do not have to clean it up first.

#### Acceptance Criteria

1. WHEN a repo URL is submitted, THE Ingestor SHALL accept these forms and normalise each to the Canonical URL: `https://github.com/o/r`, `http://github.com/o/r`, `github.com/o/r`, `www.github.com/o/r`, any of these with a trailing `/` or `.git`, any of these followed by further path segments, a query string or a fragment, and `git@github.com:o/r.git`.
2. WHEN the URL has further path segments (for example `/tree/dev/src`), THE Ingestor SHALL ignore them and analyse the default branch.
3. IF the host is not `github.com`, THEN THE Ingestor SHALL reject the URL with error code `invalid_url` and a message that names GitHub as the only supported host.
4. IF the owner does not match `^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$` or the repo does not match `^[A-Za-z0-9._-]{1,100}$`, or the repo is `.` or `..`, THEN THE Ingestor SHALL reject the URL with error code `invalid_url`.
5. THE Ingestor SHALL trim surrounding whitespace before validation and SHALL reject input longer than 300 characters with `invalid_url`.
6. THE Ingestor SHALL build the clone URL only from the validated owner and repo, never from the raw input string.

Judge check: paste `github.com/<owner>/<repo>/` (no scheme, trailing slash) and the analysis starts; paste `https://gitlab.com/a/b` and an inline error appears within 1 second.

### Requirement 2: Repo existence and visibility

**User Story:** As a developer, I want a clear message when a repo cannot be read, so that I know whether I mistyped it or it is private.

#### Acceptance Criteria

1. WHEN a valid URL is submitted, THE Ingestor SHALL resolve the default branch name and HEAD commit with `git ls-remote --symref <clone-url> HEAD`, with a 10 second timeout and `GIT_TERMINAL_PROMPT=0`.
2. IF `git ls-remote` fails with an authentication or not-found error, THEN THE Ingestor SHALL reject the request with error code `repo_not_found_or_private`.
3. IF the repo has no commits, THEN THE Ingestor SHALL reject the request with error code `repo_empty`.
4. IF `git ls-remote` times out or fails for any other reason, THEN THE Ingestor SHALL reject the request with error code `github_unavailable`.
5. THE Ingestor SHALL NOT claim to distinguish "does not exist" from "private", because GitHub does not expose the difference to anonymous clients.

Judge check: paste the URL of a private repo (or a made-up one); the landing page shows "That repo is private or does not exist" and the input keeps its value.

### Requirement 3: Size limits before cloning

**User Story:** As the operator of a free-tier server, I want huge repos refused before any bytes are cloned, so that one request cannot exhaust the instance.

#### Acceptance Criteria

1. WHEN a repo passes Requirement 2, THE Ingestor SHALL request `GET https://api.github.com/repos/{owner}/{repo}` with a 5 second timeout, sending `Authorization: Bearer $GITHUB_TOKEN` only when that variable is set.
2. WHERE `MAX_REPO_SIZE_KB` is set (default: unset, no limit), IF the API reports `size` greater than it, THEN THE Ingestor SHALL reject the request with error code `repo_too_large`, and the message SHALL state the repo size and the limit in MB.
3. IF the API responds with 403 or 429 (rate limited), times out, or errors, THEN THE Ingestor SHALL skip the size pre-check, record the warning "Size pre-check skipped: GitHub API unavailable", and continue to cloning under the limits of Requirement 4.
4. THE Ingestor SHALL make at most one GitHub API request per analysis.

Judge check: paste `https://github.com/torvalds/linux`; an error "too large to dig up" appears within 5 seconds and nothing is analysed.

### Requirement 4: Cloning under limits

**User Story:** As a developer, I want analysis to either finish or fail with a reason within a few minutes, so that I am never left watching a spinner.

#### Acceptance Criteria

1. THE Ingestor SHALL clone with `git clone --depth 500 --single-branch --no-tags --no-recurse-submodules <clone-url> <dir>`, using an argument list (no shell), `GIT_TERMINAL_PROMPT=0` and `GIT_LFS_SKIP_SMUDGE=1`.
2. WHERE `CLONE_TIMEOUT_S` is set (default: unset, no limit), IF the clone runs longer than it, THEN THE Ingestor SHALL kill it, delete the partial directory and fail the analysis with error code `clone_timeout`.
3. WHERE `MAX_CLONE_DISK_MB` is set (default: unset, no limit), WHEN the clone completes, IF the directory is larger than it, THEN THE Ingestor SHALL delete it and fail the analysis with error code `repo_too_large`.
4. WHEN the clone completes, THE Ingestor SHALL record the analysed commit as the output of `git rev-parse HEAD` and the branch from Requirement 2.
5. WHEN an analysis reaches status `done` or `failed`, THE Ingestor SHALL delete the clone directory. Only the JSON result is kept.
6. IF the server restarts, THEN THE Ingestor SHALL delete every leftover clone directory under `GRAVEYARD_DATA_DIR/clones` at startup.

### Requirement 5: File discovery

**User Story:** As a developer, I want generated and vendored code left out, so that the graveyard only shows code my team wrote.

#### Acceptance Criteria

1. THE Ingestor SHALL list Source files by walking the clone without following symlinks, and SHALL skip any path that resolves outside the clone root.
2. THE Ingestor SHALL skip these directories at any depth: `.git`, `node_modules`, `vendor`, `third_party`, `dist`, `build`, `out`, `.next`, `.nuxt`, `coverage`, `__pycache__`, `.venv`, `venv`, `env`, `.tox`, `.mypy_cache`, `site-packages`, `migrations`, `__generated__`, `generated`.
3. THE Ingestor SHALL skip these files: `*.min.js`, `*.d.ts`, `*.bundle.js`, `*_pb2.py`, `*_pb2_grpc.py`, `*.config.js`, `*.config.ts`, `*.config.mjs`, `*.config.cjs`, `*.stories.*`, and any file whose first 5 lines contain `@generated` or `DO NOT EDIT`.
4. WHERE `MAX_FILE_BYTES` is set (default: unset, no limit), THE Ingestor SHALL skip any Source file larger than it and count it in `files_skipped`.
5. THE Ingestor SHALL list Text-reference files: files up to 1 MB with extension `.yaml`, `.yml`, `.toml`, `.json`, `.cfg`, `.ini`, `.html`, `.jinja`, `.j2`, `.vue`, `.svelte`, `.astro`, `.mdx`, outside the directories of criterion 2, excluding `package-lock.json` and files ending `.lock`.
6. WHERE `MAX_SOURCE_FILES` is set (default: unset, no limit), IF more than that many Source files remain, THEN THE Ingestor SHALL fail the analysis with error code `too_many_files`, and the message SHALL state the count and the limit.
7. WHEN no Source files remain, THE Ingestor SHALL return a RepoSnapshot with an empty file list (the analysis completes with zero items; this is not an error).
8. THE Ingestor SHALL report the number of discovered Source files to the progress callback before analysis begins.
9. THE Ingestor SHALL classify each Source file as `python` (`.py`) or `typescript` (all other Source extensions), and SHALL mark it `is_test` using the rules in `design.md`.

### Requirement 6: Sample repos

**User Story:** As a judge, I want to try Graveyard with one click, so that I can evaluate it without finding a repo myself.

#### Acceptance Criteria

1. THE repo SHALL contain `samples/haunted-repo/` with Python and TypeScript code, a `history.json` and an `expected.json` that lists every item Graveyard must report, with its exact kind, verdict and confidence.
2. THE repo SHALL contain `samples/living-repo/` with Python and TypeScript code that exercises every entry-point exception and dynamic-usage pattern in specs 02 and 03, a `history.json`, and an `expected.json` that lists the only `unsure`/`revive` items permitted.
3. WHEN the backend starts, THE Ingestor SHALL materialise each sample into a real git repository under `GRAVEYARD_DATA_DIR/samples/` by replaying `history.json`: one commit per entry, with the listed author name, the listed files, and author and committer dates set to `now − days_ago`.
4. WHEN `sample=true` is requested, THE Ingestor SHALL return a RepoSnapshot for the materialised Haunted repo with `is_sample = true`, with no network access.
5. THE materialised sample SHALL go through the same walker, analysers, archaeology and verdict code as a cloned repo. No result for the sample is hard-coded.
6. THE Analysis for the sample SHALL carry the warning "Sample repo: commit history is scripted, so ages are illustrative".
7. THE Ingestor SHALL expose `ingest_local(path)` so the CLI and tests can analyse any local folder, with or without a `.git` directory.

Judge check: click "Try the sample repo"; a graveyard with at least 12 tombstones appears within 5 seconds, with a visible note that the sample's history is scripted.

### Requirement 7: Safety

**User Story:** As the operator, I want untrusted repos handled as inert data, so that analysing a malicious repo cannot harm the server.

#### Acceptance Criteria

1. THE Ingestor SHALL NOT execute, import or install anything from a cloned repo, and SHALL NOT run any git command that executes repo-defined hooks or filters.
2. THE Ingestor SHALL create each clone in a fresh directory named by a random token, never by user input.
3. THE Ingestor SHALL read files as bytes and decode as UTF-8 with replacement; a file that is not valid UTF-8 SHALL NOT fail the analysis.

## Assumptions (flagged; see docs/open-decisions.md)

- A1. "Shallow clone" is taken as depth 500, not depth 1. A depth-1 clone has exactly one commit, so every item would show the same date and author and git archaeology would be meaningless. Depth 500 is still a shallow clone. See decision D1.
- A2. Only the default branch is analysed in P0; `/tree/<branch>` in the URL is ignored. See D7.
- A3. `.js`/`.jsx`/`.mjs`/`.cjs` files are reported with `language = "typescript"` because the data model allows only `python` and `typescript`. See D8.
- A4. Sample history is scripted with backdated commits so that the sample can show `high` confidence items (which need more than 180 days of age). It is labelled in the UI. See D2.
- A5. `migrations` directories are skipped (Django/Alembic migrations are loaded by name and would be noise).
- A6. Owner decision (14 Nov 2026): no size, file-count, time or item limits for now. Every limit is a `config.py` value that defaults to unset; the checks, error codes and error screens are still built and tested (with explicit test values), so a limit can be switched on by setting one number once real measurements on the host exist. Clone depth (500 commits) is not a limit of this kind and stays. See D17.
