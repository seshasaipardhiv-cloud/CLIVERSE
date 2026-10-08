# CLIVERSE Capability Map

## Product boundary

CLIVERSE is a local-first environment around existing AI coding CLIs. It adds
planning, persistent project context, user rules, controlled execution,
versioned changes, recoverable sessions, audit records, and a dashboard.
Multi-agent orchestration is out of scope for this version.

## Stable module IDs and ownership

| Module ID | Owner | Responsibility | Depends on |
|---|---|---|---|
| `core-laya` | Member 1 | Environment and CLI, Laya planning/clarification, CLI adapters, filesystem tracking, Git, sessions, recovery, core events | `memory-rules`, `trust-audit` |
| `memory-rules` | Member 2 | Persistent project/conversation memory, retrieval, global/project/CLI rules, priority and conflict resolution | None |
| `dashboard-ux` | Member 3 | User-facing dashboard, project/session/rules/memory/Git views, settings and live activity | `core-laya`, `memory-rules`, `trust-audit` |
| `trust-audit` | Member 4 | Identity, permissions, command/filesystem restrictions, secrets, sandboxing, policies, governance and audit infrastructure | None |

## Dependency direction and build order

1. Agree on the Member 1/2/4 interface contracts before consumers depend on them.
2. Build a small `core-laya` vertical path with replaceable memory and policy
   interfaces.
3. Implement `memory-rules` and `trust-audit` behind those interfaces.
4. Connect the dashboard only to stable public interfaces; its UI decisions
   remain with the user and Member 3.
5. Add regulatory monitoring after the execution, memory, security and audit
   path is stable.

Dependencies point from consumers to providers; no module may directly edit
another member's internal implementation. Multi-agent orchestration is not a
module in this map.

## Existing repository baseline

The repository already contains Member 4 security, governance, audit and API
modules. They are preserved as-is. The existing standard-library runner passed
six tests on Python 3.11; that is a baseline check, not a complete security
review or proof of the README's broader claims. See
[`docs/repository-baseline.md`](docs/repository-baseline.md).

## Review roster

The supplied brief identifies member numbers and responsibilities but does not
identify people or provide experience histories. Do not infer either.

| Member | Name | Review domain | Experience |
|---|---|---|---|
| Member 1 | Not provided | Core + Laya, CLI adapters, sessions, Git and recovery | Not provided |
| Member 2 | Not provided | RAG, persistent memory, rule parsing/resolution | Not provided |
| Member 3 | Not provided | Dashboard, frontend UX and user-facing integration | Not provided |
| Member 4 | Not provided | Security, permissions, governance and audit | Not provided |
