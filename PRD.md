# Product Requirements — CLIVERSE

## Objective

Build a local-first development environment that makes existing AI coding
CLIs persistent, context-aware, rule-governed, version-controlled and
inspectable. The user remains in control of questions, permissions, external
connections and destructive actions.

## Users and user story

**Primary user:** a developer working in a local project with one or more
existing AI coding CLIs.

**User story:** Given a development request, the environment gathers relevant
project context and applicable rules, asks for missing critical information,
produces a structured task, checks permission before execution, records the
session and file changes, and exposes a reviewable Git history.

## Goals

- Provide a dependable local CLI and core API.
- Keep memory, rules, sessions, decisions, events and Git changes inspectable.
- Keep CLI vendors replaceable through explicit adapter contracts.
- Fail closed when a required policy decision is missing or fails.
- Build and verify vertical slices rather than disconnected layers.
- Keep model inference local; no hosted model/API is selected for the current
  initial build.

## Non-goals

- Multi-agent orchestration in this version.
- A custom foundation model or model training.
- A Member 1 dashboard or unapproved UI/UX decisions.
- A claim of legal/regulatory compliance; policy checks are assistance only.
- Automatic execution when a required permission decision is absent.

## Agreed repository and Laya boundary

- Product code and task commits belong in `seshhasaipardhiv-cloud/CLIVERSE`.
- The separate `siva169/laya` source repository is not to be modified or copied.
- Laya is a local typed-decision engine, not a generative prompt planner.
  CLIVERSE may call its public API through an adapter for classification and
  structured decisions; deterministic prompt assembly remains CLIVERSE code.
- Laya model weights and any generative open-weight model are not selected or
  downloaded in this phase. The live model path must not be reported as
  verified until it runs locally.
- The repository already contains Member 4 security/governance/audit code.
  Preserve those files. Its test and inspection results are in
  [`docs/repository-baseline.md`](docs/repository-baseline.md); the passing
  tests do not independently verify every README claim.
- The team confirmed MIT as the intended project license. A `LICENSE` file is
  added separately; no existing Member 4 files are changed.
- Python 3.11 is available in the build environment and is within Laya's
  documented Python support range. Python 3.14 is also present but outside
  Laya's stated classifiers; target Python 3.10–3.13.

## Architecture and module ownership

The four module boundaries and build dependencies are defined in
[`CAPABILITY-MAP.md`](CAPABILITY-MAP.md). Member 1 owns `core-laya`; Member 2
owns `memory-rules`; Member 3 owns `dashboard-ux`; Member 4 owns
`trust-audit`. Member 1 must not implement the other owners' internals.

## Member 1 functional requirements

1. Initialize a project-local environment and persist its configuration.
2. Accept a user request, retrieve context/rules through provider interfaces,
   and stop for clarification when required information is missing.
3. Produce a stable structured task with `role`, `context`, `task`,
   `requirements`, `constraints` and `output`.
4. Dispatch only through a selected CLI adapter, using an argument vector and
   an explicit working directory; never build a shell command from user text.
5. Record a unique session, meaningful events, execution result and changed
   files.
6. Expose Git status/diff/history and recoverable changes. Destructive undo
   must be explicitly confirmed and must never overwrite unrelated work.
7. Surface errors and policy denials; never convert failures into
   success-shaped defaults.

## Cross-member interface contracts

Proposed method signatures and the current integration gate are also recorded
in [`docs/integration-contracts.md`](docs/integration-contracts.md).

### Member 2 — memory and rules

Proposed synchronous provider contract; request/response schemas must be
confirmed with Member 2 before integration:

- `retrieve_context(task) -> ContextBundle`
- `get_applicable_rules(task) -> list[Rule]`
- `store_memory(data) -> MemoryRef`
- `search_memory(query) -> list[MemoryHit]`

Each record carries a stable ID, source, project scope and timestamp. Retrieval
returns a bounded result set and its provenance. Missing providers are explicit
errors, not silent empty context.

### Member 4 — authorization and policy

Proposed execution boundary; confirm the schema with Member 4 before
integration:

- `authorize(identity, operation, project_root, paths, command) -> Decision`
- `Decision` is one of `ALLOW`, `WARN`, or `BLOCK`, with a reason and any
  required user confirmation.
- Missing or failed authorization blocks execution.
- The environment must not pass secrets or unrelated environment variables to
  an adapter by default.

### CLI adapter

- Input: a typed task, configured executable/argument list, project root and
  bounded timeout.
- Output: process status, stdout/stderr, duration and changed-path summary.
- Errors: unavailable executable, timeout, non-zero exit and invalid result
  are explicit failures.

## Proposed repository layout

```text
src/cliverse/       CLI, core use cases, adapters and persistence
tests/              Standard-library unit and integration tests
docs/               Architecture, references and review checklists
tasks/              Approved build plan and task status
public/             Reserved for Member 3 after UI/UX approval
```

## Technology constraints

- Python 3.10–3.13 for compatibility with the selected Laya package.
- Python standard library first: `argparse`, `sqlite3`, `subprocess`,
  `pathlib`, and `unittest`.
- Git CLI for repository operations.
- SQLite for initial local persistence.
- Laya is integrated through its public API only; its source stays unchanged.
- No paid service, hosted inference API, new account or package installation
  is assumed. Any installation or model download needs separate approval.

## CLI contract

- Commands return machine-readable JSON by default; `--human` is opt-in.
- Standard output contains result data; diagnostics go to standard error.
- Errors use a stable object with `error`, `code`, `message` and `suggestion`,
  and exit non-zero.
- Missing required input does not start an interactive prompt in agent mode.
- Destructive operations require explicit confirmation.

## Commands and verification

The initial test runner uses only the standard library:

```bash
python3.11 -m unittest discover -s tests -v
python3.11 -m cliverse --help
```

Each implemented slice must add focused tests and run the repository's test
suite. Tests must not call hosted services or download model weights.

## Success criteria

- Every completed Member 1 task has an acceptance check and test evidence.
- A fresh local checkout can initialize the environment and inspect a
  structured plan without a hosted service.
- Clarification-needed requests cannot proceed into execution.
- Adapter execution is behind a policy boundary and does not invoke a shell.
- Session/event data and Git changes can be reviewed.
- No model-backed inference, full project completion, or hackathon eligibility
  is claimed until the local model and required end-to-end path are verified.
- Teammate identities and experience are confirmed by the team rather than
  invented.

## Project checklists

- The 16-item polish checklist and 17-item fix checklist are tracked in
  [`docs/checklists.md`](docs/checklists.md); dashboard items are assigned to
  Member 3 and remain unverified.
- Model selection/availability and teammate names/experience remain open
  items.
