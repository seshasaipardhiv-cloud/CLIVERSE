# Implementation Plan — CLIVERSE

## Scope

Implement Member 1's `core-laya` responsibilities in the public
`seshhasaipardhiv-cloud/CLIVERSE` repository. Track the other member-owned
work for coordination, but do not implement their internals. The existing
`siva169/laya` source stays unchanged and is used only through its public
package interface.

## Architecture decisions

- Use a small Python package with standard-library CLI, SQLite, process and
  test support; avoid a web server in the Member 1 slice.
- Keep the core behind provider and adapter interfaces so Member 2 and Member
  4 can integrate without sharing internal modules.
- Make request planning deterministic and testable first. Laya supplies
  typed decisions when a local checkpoint is available; it does not generate
  natural-language prompts. Model-backed generation is deferred and must be
  an explicit later task.
- Use subprocess argument lists with `shell=False`; do not accept free-form
  shell command strings.
- Record changes and expose diff/history before adding recovery. Undo is
  confirmation-gated and must preserve unrelated work.
- Use no hosted APIs, paid services, installations or model downloads in the
  initial implementation.

## Task order and checkpoints

1. **Project contract and backlog** — capability map, PRD, task list, sources
   and project instructions. Verify paths/content and review diff.
2. **CLI foundation** — package entry point, JSON output/errors, project
   initialization. Verify with standard-library tests and a clean temp repo.
3. **Session and event persistence** — SQLite schema and session operations.
   Verify create/read/event behavior and validation.
4. **Provider contracts and Laya adapter** — typed task/context/rule/policy
   contracts and Laya decision adapter. Verify with fakes; do not download
   weights.
5. **Planning and clarification** — structured output and fail-closed
   clarification state. Verify clear, incomplete and malformed requests.
6. **CLI adapter and execution guard** — process adapter, timeout and policy
   boundary. Verify using a temporary fake executable; no real AI CLI invocation.
7. **Git inspection and recovery** — status/diff/history, then confirmed,
   scoped undo. Verify in disposable repositories and preserve unrelated files.
8. **End-to-end Member 1 path** — environment → plan → guarded execution →
   session/events → Git evidence. Verify with deterministic fakes.
9. **Member handoffs** — confirm Member 2/4 contracts; Member 3 UI remains
   blocked on user-selected design. Add no hidden cross-owner implementation.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| The product brief spans four independently owned subsystems | A full system is not deliverable in two hours by one member | Implement Member 1 slices; record teammate-owned work separately |
| Laya is a typed classifier, not a prompt-generating LLM | Overstated AI capability or wrong adapter design | Use typed decisions only; keep prompt assembly separate; defer generation |
| No model checkpoint has been selected or verified | Live inference and open-weight-AI demo are not yet proven | Use offline fakes in tests; request approval before model install/download |
| Member 2/4 contracts are not finalized | Integration mismatch and unsafe execution | Publish proposed contracts; confirm with those owners before integration |
| Undo can overwrite user work | Data loss | Scope paths to project root, inspect state, require confirmation and test recovery |
| No teammate names or experience histories were supplied | Fabricated reviewer information | Leave explicit placeholders; ask the team |
| Existing Member 4 code has an unauthenticated API and permissive defaults | Unsafe execution if Member 1 assumes the gate is production-ready | Preserve Member 4 files; require confirmed, fail-closed authorization contract before wiring execution |
| Team license choice was initially unknown | Unintended IP terms | Team confirmed MIT; add a separate LICENSE file |
| The current default interpreter is Python 3.14 | Laya documents support through Python 3.13 | Use the available Python 3.11 runtime for verification |

## Research sources

See [`docs/references.md`](../docs/references.md) for the official event rules,
Python subprocess/SQLite guidance, Laya API/limits, Git documentation and
Gemma 4 status.

## Definition of done

- Task acceptance criteria and focused checks pass.
- CLI output/errors match the documented contract.
- No test requires network access or model weights.
- Diff is scoped, readable and reviewed.
- `changes.md` is updated.
- Each completed task receives one clear Git checkpoint; no claim of model
  inference or full system completion without direct evidence.
