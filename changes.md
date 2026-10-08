# Changes

## 2026-10-08 — Establish Member 1 plan and repository handoff

- Recorded the four-module ownership map, Member 1 PRD, ordered implementation
  plan, API boundary proposals and acceptance-based task list.
- Preserved the pre-existing Member 4 security/governance/audit implementation;
  documented its scope, baseline test result and integration observations
  without editing its files.
- Ran the existing Python 3.11 test runner: 6 tests passed.
- Added source notes and tracked the 16-item polish + 17-item fix checklist.
- Added the team-confirmed MIT license.
- Left teammate names/experience, live model selection and actual model
  inference explicitly pending.
- No application code, package installation, model download or hosted API use
  was performed in this documentation slice.

## 2026-10-08 — M1-01: create CLI foundation and environment initialization

- Added a Python 3.10–3.13 package, source-checkout launcher, stable JSON
  errors, and `init`/`status` commands.
- Project initialization creates `.envcore/config.json` with restrictive
  permissions and refuses to overwrite existing configuration.
- Added focused standard-library tests for initialization, malformed
  configuration, non-overwrite behavior, JSON output, help and version.
- Verified: 5 targeted tests passed; CLI help and version commands succeeded.
- No dependency installation, model download or hosted API use.

## 2026-10-08 — M1-02: persist sessions and core events

- Added SQLite-backed session creation, listing, detail retrieval, completion
  status and bounded append-only event records.
- Used bound SQL parameters, foreign keys, append-only event triggers and
  explicit invalid/missing-session errors.
- Added `cliverse session start|list|show|finish` JSON commands.
- Verified: 11 core CLI/environment/session tests passed, including persistence
  across store instances and refusal to mutate stored events.
- No dependency installation, model download or hosted API use.

## 2026-10-08 — M1-03: define cross-member provider contracts

- Added typed task/context/rule/memory records and the four Member 2 provider
  operations.
- Added a Member 4 authorization request/result protocol; `BLOCK`, invalid
  results and unconfirmed `WARN` fail closed.
- Verified: 15 core tests passed, including authorization decision boundaries.
- Member 2/4 owner confirmation is still pending; the proposed interfaces are
  not represented as an agreed integration yet.

## 2026-10-08 — M1-04: add the Laya decision adapter

- Added an adapter for the public `Router.predict(state, questions)` API.
- The adapter requires a caller-injected router, validates the typed answer
  envelope and never constructs a router or triggers checkpoint downloads.
- Verified: 18 core tests passed, including fake-router response and error
  cases. No live model inference was run.

## 2026-10-08 — M1-05: structure tasks and gate clarification

- Added deterministic ROLE/CONTEXT/TASK/REQUIREMENTS/CONSTRAINTS/OUTPUT
  planning with optional Member 2 context/rules providers.
- Missing tasks and explicit unresolved critical questions return
  `needs_clarification` without constructing a task.
- Missing memory providers fail explicitly. `--without-memory` is an explicit
  opt-in and reports that no RAG context/rules were retrieved.
- Provider exceptions and invalid provenance remain visible.
- Verified: 24 core tests passed; a CLI smoke test emitted the expected
  structured JSON task.
- Automatic semantic ambiguity detection and live Laya inference remain
  unverified; caller-supplied clarification is the current boundary.

## 2026-10-08 — M1-06: add guarded CLI process execution

- Added argument-vector subprocess execution with `shell=False`, canonical
  executable paths, explicit project cwd, bounded timeout and explicit child
  environment (no inherited secrets by default).
- Authorization is required before launch. Missing/invalid/BLOCK decisions
  stop execution; WARN requires a separate confirmation. Non-zero exits and
  timeouts remain explicit errors.
- Verified: 30 core tests passed, including denial-before-launch, warning
  confirmation, argument safety, environment scoping, timeout and non-zero
  exit handling.
- No public command can launch an AI CLI yet; integration awaits Member 4's
  authenticated authorization contract.

## 2026-10-08 — M1-07: inspect project Git state

- Added read-only Git status, staged/unstaged/untracked diff and bounded
  history inspection, restricted to the selected repository root.
- Disabled external diff/pagers, used argv execution and surfaced Git errors.
- History extracts session IDs only from explicit `CLIVERSE-Session:` commit
  trailers; it does not invent provenance.
- Added `cliverse git status|diff|history`.
- Verified: 35 core tests passed across committed/unborn repositories,
  untracked files, root containment and session trailer parsing.

## 2026-10-08 — M1-08: add session-linked commit and recovery APIs

- Added explicit-path commits with exact changed-path matching, no pre-staged
  user changes, session trailers, confirmation and authorization.
- Added undo preview and revert only for the clean current HEAD commit carrying
  the requested session trailer; refuses dirty trees, unrelated HEADs and
  merge commits. Git hooks are disabled for this controlled operation.
- CLI exposes `git undo-preview`; commit and revert mutation remain library
  only until Member 4 confirms a safe integration.
- Verified: 9 Git inspection/commit tests and 5 recovery tests passed in
  disposable repositories, including preservation of unrelated changes.

## 2026-10-08 — M1-09: verify Member 1 vertical path

- Added a deterministic end-to-end test covering init → structured plan →
  guarded local process → session/events → session-linked Git commit →
  confirmed undo.
- The test uses a temporary Git project, local Python process and injected
  allow-only test authorizers. It uses no hosted service or model weights.
- Hardened `.envcore` permissions and rejected symlinked session databases;
  isolated Git inspection from system/global configuration and rechecked the
  reviewed worktree before staging.
- Verified: all 48 Member 1 core tests and all 6 existing Member 4 baseline
  tests passed; `git diff --check` passed.
- Actual Laya model inference, Member 2 retrieval and Member 4 authorization
  remain unverified integration gates.
