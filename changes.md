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
