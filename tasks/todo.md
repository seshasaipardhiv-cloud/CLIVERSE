# CLIVERSE Task List

Task IDs are stable. "Member 1" tasks are the active implementation scope;
other rows are owned by the named teammate role and are not permission to edit
their internals.

## Member 1 — Core + Laya

- [ ] **M1-01 — Create the Python CLI foundation and `env init`**
  - Acceptance: package starts; `--help` works; JSON is the default; init
    creates project-local metadata without overwriting existing files.
  - Verify: standard-library tests plus initialization in a temporary folder.
  - Files: `src/cliverse/`, `tests/`, `pyproject.toml`, `README.md`.
  - Dependencies: project contract (`PRD.md`).

- [ ] **M1-02 — Persist sessions and core events**
  - Acceptance: sessions have unique IDs and timestamped metadata; events are
    append-only; invalid input fails explicitly.
  - Verify: create/read/list tests using temporary SQLite databases.
  - Files: `src/cliverse/sessions.py`, `src/cliverse/events.py`, tests.
  - Dependencies: M1-01.

- [ ] **M1-03 — Define Member 2 and Member 4 provider contracts**
  - Acceptance: context/rules and authorization have typed inputs/outputs;
    missing providers or exceptions do not silently allow execution.
  - Verify: contract tests for `ALLOW`, `WARN`, `BLOCK`, missing-provider and
    provider-failure outcomes.
  - Files: `src/cliverse/contracts.py`, `docs/integration-contracts.md`, tests.
  - Dependencies: none; confirm shapes with Members 2 and 4 before integration.

- [ ] **M1-04 — Add the unchanged Laya decision adapter**
  - Acceptance: CLIVERSE calls only Laya's public typed-decision API; prompt
    construction remains separate; no source copy or model download occurs.
  - Verify: fake-router tests; live inference is separately marked pending.
  - Files: `src/cliverse/laya_adapter.py`, `pyproject.toml`, tests, README.
  - Dependencies: M1-03; local Laya dependency availability.

- [ ] **M1-05 — Plan tasks and ask clarification when inputs are missing**
  - Acceptance: clear requests yield `role/context/task/requirements/
    constraints/output`; unresolved critical gaps block execution.
  - Verify: complete, ambiguous and malformed request tests.
  - Files: `src/cliverse/planning.py`, tests, docs.
  - Dependencies: M1-03, M1-04; Member 2 provider contract.

- [ ] **M1-06 — Dispatch through a guarded CLI adapter**
  - Acceptance: adapter uses an argument vector, explicit cwd and timeout;
    policy `BLOCK` prevents launch; failure results remain failures.
  - Verify: temporary fake executable for success, non-zero exit and timeout.
  - Files: `src/cliverse/cli_adapters/`, `src/cliverse/execution.py`, tests.
  - Dependencies: M1-02, M1-03, M1-05; Member 4 authorization contract.

- [ ] **M1-07 — Track filesystem changes and Git history**
  - Acceptance: changed paths and diffs are reviewable and scoped to the
    selected project; history identifies the originating session.
  - Verify: disposable Git repository with known changed and unrelated files.
  - Files: `src/cliverse/git/`, `src/cliverse/filesystem.py`, tests.
  - Dependencies: M1-02, M1-06.

- [ ] **M1-08 — Add explicit recovery and undo**
  - Acceptance: undo requires confirmation, rejects out-of-project paths and
    refuses to overwrite unrelated/uncommitted work.
  - Verify: restore tests in disposable repositories, including refusal cases.
  - Files: `src/cliverse/recovery.py`, `src/cliverse/git/`, tests, docs.
  - Dependencies: M1-07; Member 4 approval.

- [ ] **M1-09 — Verify the Member 1 end-to-end path**
  - Acceptance: init → plan/clarify → guarded fake CLI → session/events → Git
    evidence works without network or model weights.
  - Verify: one deterministic end-to-end test and documented demo commands.
  - Files: integration tests and README.
  - Dependencies: M1-01 through M1-08.

## Member 2 — RAG + Rules (teammate-owned)

- [ ] **M2-01 — Confirm retrieval and rules API schemas with Member 1**
- [ ] **M2-02 — Implement local ingestion, retrieval and persistent memory**
- [ ] **M2-03 — Implement rule parsing, priority and conflict resolution**
- [ ] **M2-04 — Add retrieval/rule evaluation tests and handoff documentation**

## Member 3 — Dashboard + UX (teammate-owned; UI choices require approval)

- [ ] **M3-01 — Collect and record boss-approved UI/UX decisions**
- [ ] **M3-02 — Build the dashboard against stable public interfaces**
- [ ] **M3-03 — Complete the 16-item polish checklist where applicable**
- [ ] **M3-04 — Complete the 17-item fix checklist where applicable**
- [ ] **M3-05 — Verify mobile layouts at 390, 425, 768 and 1024 px**

## Member 4 — Security + Governance + Audit (teammate-owned)

- [ ] **M4-01 — Confirm identity, permission and decision API with Member 1**
- [ ] **M4-02 — Implement scoped filesystem/command permissions and secrets**
- [ ] **M4-03 — Implement security and regulatory `ALLOW/WARN/BLOCK` policies**
- [ ] **M4-04 — Implement audit events and security-focused tests**

## Team / submission gates

- [ ] Confirm all four developer names and truthful experience descriptions.
- [x] Team confirmed MIT as the project license; add the license file.
- [ ] Record the four developer names and truthful experience descriptions.
- [ ] Verify a local open-weight model and its license before claiming AI-track
  eligibility; no model is currently selected or running.
- [ ] Keep meaningful incremental commits; event brief says every teammate
  should make at least one commit per hour.
- [ ] Complete a working demo and verify setup before final submission.
