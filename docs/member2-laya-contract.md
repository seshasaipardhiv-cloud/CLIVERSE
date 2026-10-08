# Member 2 → Member 1 (Laya) Integration Contract

**Subsystem:** CLIVERSE — Member 2 (Memory / RAG & Rules Intelligence)  
**Contract Version:** 1.1 (Stage 5.1 Hardened)  
**Target Consumer:** Member 1 (Core Execution Engine & Laya Intent Processor)  
**Status:** Implemented, Hardened & Verified (All Stages 1–6 & Final — 167 Tests Green; Repo: 235 passed, 0 failed, 2 skipped due to documented environment-specific requirements across 237 collected items)

---

## 1. Executive Summary

Member 2 provides the cognitive context and engineering constraint intelligence consumed by Member 1 (Laya) during prompt planning and structured task creation.

```
                         TASK INVOCATION
                               │
                               ▼
        ┌──────────────────────────────────────────────┐
        │       LayaIntelligenceService (Member 2)     │
        │                                              │
        │   ┌────────────────────┐ ┌────────────────┐  │
        │   │  RetrievalService  │ │  RulesEngine   │  │
        │   │  (Semantic RAG)    │ │  (Constraints) │  │
        │   └─────────┬──────────┘ └───────┬────────┘  │
        └─────────────┼────────────────────┼───────────┘
                      ▼                    ▼
             [Relevant Memories]   [Winning Rules]
                      │                    │
                      └──────────┬─────────┘
                                 ▼
                     LayaIntelligenceContext
                                 │
                                 ▼
                    MEMBER 1 / LAYA PLANNER
                                 │
                                 ▼
                        MEMBER 4 (TrustGate)
                    Security & Execution Authorization
```

Member 2 keeps memory retrieval and rules evaluation logically separated internally, while providing a single, unified, serializable result object: [`LayaIntelligenceContext`](file:///A:/CLIVERSE/memory/intelligence.py).

> **Member 2 rule_decision is not execution authorization. Member 4 TrustGate is the final execution authorization authority.**  
> `rule_decision` represents developer/project rule resolution only. Member 4 governs final execution authorization and sandboxing.

---

## 2. Quickstart for Member 1

```python
from rag_rules_service import (
    LayaIntelligenceService,
    LayaIntelligenceContext,
    SubsystemStatus,
    RuleDecision,
)

# 1. Initialize the intelligence service (uses default persistent stores)
service = LayaIntelligenceService()

# 2. Build complete intelligence context for a task
intelligence: LayaIntelligenceContext = service.build_intelligence_context(
    task="Add JWT authentication to the login service",
    project_id="my-service",
    cli_name="claude-cli",
    top_k=5,
    min_score=0.35,
    context_budget_tokens=2000,
)

# 3. Check subsystem health BEFORE acting on decisions
if intelligence.memory_status == SubsystemStatus.ERROR:
    # Memory subsystem failed — do NOT treat this as "no relevant memory"
    log.warning("Memory unavailable: %s", intelligence.metadata.get("memory_error"))

if intelligence.rules_status == SubsystemStatus.ERROR:
    # Rules engine failed — rule_decision is UNKNOWN, not ALLOW
    log.warning("Rules engine unavailable: %s", intelligence.metadata.get("rules_error"))

# 4. Inspect rule decision (developer/project rules only, NOT security authorization)
if intelligence.rule_decision == RuleDecision.DENY:
    print("Blocked by engineering guardrail:", intelligence.rule_explanations)
elif intelligence.rule_decision == RuleDecision.ASK:
    print("Human confirmation required:", intelligence.rule_explanations)
elif intelligence.rule_decision == RuleDecision.REQUIRE:
    print("Prerequisite constraint active:", intelligence.rule_explanations)
elif intelligence.rule_decision == RuleDecision.UNKNOWN:
    print("Rule resolution unavailable — rules engine error")

# 5. Inject formatted context directly into Laya prompt
prompt_block = intelligence.combined_laya_context
```

Also accepts Member 1's `StructuredTask` (or any `TaskLike`-compatible object):

```python
intelligence = service.build_intelligence_context(
    task=structured_task,   # str OR StructuredTask OR any object with .task and .as_dict()
    project_id="my-service",
    cli_name="claude-cli",
)
```

---

## 3. Data Contract: `LayaIntelligenceContext`

The result object exposes typed fields for unified text generation and granular programmatic inspection:

| Field | Type | Description |
|---|---|---|
| `task` | `str` | Normalized user task prompt (extracted from str or TaskLike object). |
| `project_id` | `Optional[str]` | Active project identifier (strictly isolated). |
| `cli_name` | `Optional[str]` | Active CLI adapter identifier (e.g. `claude-cli`, `aider`). |
| `memory_context` | `ContextPacket` | Complete Stage 3 memory packet with ranked items, snippets, token estimates, and provenance. |
| `applicable_rules` | `List[Rule]` | All rules that passed scope, project, CLI, and condition filters. |
| `rule_resolution` | `RuleResolution` | Stage 4 deterministic resolution output (winning rules, suppressed rules, conflicts, trace). |
| `context_sources` | `List[str]` | File paths and line ranges cited in retrieved memory. |
| `rule_explanations` | `List[str]` | Human-readable conflict override and tie-break explanations. |
| `combined_laya_context` | `str` | Clean, multi-section Markdown block ready for prompt injection. |
| `memory_status` | `SubsystemStatus` | Explicit memory subsystem status (`OK_WITH_RESULTS`, `OK_EMPTY`, `ERROR`). |
| `rules_status` | `SubsystemStatus` | Explicit rules subsystem status (`OK_WITH_RESULTS`, `OK_EMPTY`, `ERROR`). |
| `rule_decision` | `RuleDecision` | Developer/project rule resolution decision (see Section 4). |
| `decision` | `str` | String alias of `rule_decision` for backward compatibility and serialization. |
| `metadata` | `Dict[str, Any]` | Audit metadata including `memory_status`, `rules_status`, `memory_error`, `rules_error`, and task fields from `as_dict()`. |

---

## 4. `SubsystemStatus` — Explicit Health States

```python
class SubsystemStatus(str, Enum):
    OK_WITH_RESULTS = "OK_WITH_RESULTS"  # Subsystem ran; found data
    OK_EMPTY        = "OK_EMPTY"         # Subsystem ran; found nothing (valid)
    ERROR           = "ERROR"            # Subsystem raised an exception
```

### Critical Semantics

| State | Description | `combined_laya_context` |
|---|---|---|
| `OK_WITH_RESULTS` | Subsystem ran successfully and returned data | Memory items or rule sections shown |
| `OK_EMPTY` | Subsystem ran successfully but found nothing | `*(No relevant project memory found)*` or `*(No applicable engineering rules)*` |
| `ERROR` | Subsystem raised an unrecoverable exception | `*(Memory subsystem error: <msg>)*` or `*(Rules subsystem error: <msg>)*` |

> **Rule:** `OK_EMPTY` and `ERROR` are **never interchangeable**.  
> An error must never be presented as "no relevant memory found."  
> An empty result must never be presented as a subsystem error.

---

## 5. `RuleDecision` — Rule Resolution Outcomes

```python
class RuleDecision(str, Enum):
    ALLOW   = "ALLOW"    # No applicable rules, or all rules permit
    WARN    = "WARN"     # Advisory warning; action may continue
    REQUIRE = "REQUIRE"  # Positive prerequisite constraint (e.g. "tests must pass")
    ASK     = "ASK"      # Human confirmation required before continuing
    DENY    = "DENY"     # Hard prohibition; action is blocked by guardrail
    UNKNOWN = "UNKNOWN"  # Rules engine failed; resolution unavailable
```

### Severity Priority (highest wins on conflict)

```
DENY (6) > ASK (5) > REQUIRE / ENFORCE (4) > WARN (2) > ALLOW (1)
```

### Decision Mapping

| `winning_rules` effects | `rule_decision` |
|---|---|
| Any `DENY` | `DENY` |
| Any `ASK` (no DENY) | `ASK` |
| Any `REQUIRE` or `ENFORCE` (no DENY/ASK) | `REQUIRE` |
| Any `WARN` (no above) | `WARN` |
| Only `ALLOW` or no rules | `ALLOW` |
| Rules engine exception | `UNKNOWN` |

### REQUIRE vs DENY

These are **not equivalent**:

- **`DENY`** — Hard prohibition. The action described by the rule is forbidden.
- **`REQUIRE`** — Positive prerequisite. The action is permitted **only if** a condition is first satisfied (e.g., "Tests must pass before merging").

`ENFORCE` is a historical synonym for `REQUIRE` and maps identically.

### Rule Decision is NOT Security Authorization

```
rule_decision  ≠  security_decision
rule_decision  ≠  execution_authorized
```

The full authorization flow is:

```
LAYA → MEMBER 2 (rule_decision) → MEMBER 4 TrustGate (security + governance) → EXECUTION
```

Member 2 never makes the final execution decision. Do not treat `rule_decision=ALLOW` as permission to execute.

---

## 6. Error & Empty-State Semantics (Stage 5.1 Hardened)

### Memory States

| Scenario | `memory_status` | `combined_laya_context` prompt text |
|---|---|---|
| Memory found | `OK_WITH_RESULTS` | `[MEMORY N]` sections with snippets |
| No matching memory | `OK_EMPTY` | `*(No relevant project memory found)*` |
| Retrieval exception | `ERROR` | `*(Memory subsystem error: <exception message>)*` |

### Rules States

| Scenario | `rules_status` | `rule_decision` | `combined_laya_context` prompt text |
|---|---|---|---|
| Rules found and resolved | `OK_WITH_RESULTS` | Based on winning effects | Rule sections shown |
| No applicable rules | `OK_EMPTY` | `ALLOW` | `*(No applicable engineering rules)*` |
| Rules engine exception | `ERROR` | `UNKNOWN` | `*(Rules subsystem error: <exception message>)*` |

### Failure Combinations

| Memory | Rules | `memory_status` | `rules_status` | `rule_decision` |
|---|---|---|---|---|
| OK | OK with rules | `OK_WITH_RESULTS` | `OK_WITH_RESULTS` | Based on effects |
| OK | OK no rules | `OK_WITH_RESULTS` or `OK_EMPTY` | `OK_EMPTY` | `ALLOW` |
| OK | Failed | Any OK state | `ERROR` | `UNKNOWN` |
| Failed | OK | `ERROR` | Any OK state | Based on effects |
| Failed | Failed | `ERROR` | `ERROR` | `UNKNOWN` |

---

## 7. TaskLike Protocol (FIX 7)

Member 2 accepts tasks as `str`, Member 1's `StructuredTask`, or any object satisfying:

```python
@runtime_checkable
class TaskLike(Protocol):
    task: str

    def as_dict(self) -> Dict[str, Any]:
        ...
```

- **`str`** — task text used directly.
- **`StructuredTask`** — `.task` extracted; `.as_dict()` merged into `metadata`.
- **Any `TaskLike`** — same behavior as StructuredTask.

Member 1 does **not** need to change its `StructuredTask` implementation.

---

## 8. Prompt Context Layout (`combined_laya_context`)

```markdown
### PROJECT CONTEXT

[MEMORY 1]
Source: docs/architecture.md:12-40
Type: doc
Relevance: 0.91

FastAPI backend architecture with PostgreSQL for persistent relational data.

### APPLICABLE RULES

[PROJECT]
* Use PostgreSQL for all database operations.

[CLI]
* Ask confirmation before installing new packages.

### RULE RESOLUTION

Decision: ASK
Confirmation Required: Ask confirmation before installing new packages.

No blocking conflict detected.
```

**Error state example (memory failed):**

```markdown
### PROJECT CONTEXT

*(Memory subsystem error: Storage failure)*

### APPLICABLE RULES

[PROJECT]
* Use PostgreSQL for all database operations.

### RULE RESOLUTION

Decision: REQUIRE
Prerequisite Constraint: Use PostgreSQL for all database operations.

No blocking conflict detected.
```

---

## 9. Ephemeral Task-Level Rules

Laya can define dynamic, task-specific rules without mutating persistent project or global configurations:

```python
from rules.models import Rule, RuleScope, RuleEffect

task_rule = Rule(
    rule_id="temp-use-mongo",
    name="Temporary MongoDB Usage",
    scope=RuleScope.TASK,
    target="database",
    effect=RuleEffect.ENFORCE,
    description="Use MongoDB for this analytics task only.",
)

intelligence = service.build_intelligence_context(
    task="Run analytics aggregation",
    project_id="my-service",
    task_rules=[task_rule],  # Ephemeral; not persisted to disk
)
```

By scope precedence, this `TASK` rule overrides any non-mandatory `PROJECT` or `GLOBAL` rule on the same target.

---

## 10. Determinism & Isolation Guarantees

1. **Deterministic Resolution:** Identical memory/rules state → identical rankings, decisions, and text traces across all calls.
2. **Project Isolation:** Project Alpha never retrieves Project Beta memory, and never applies Project Beta rules.
3. **CLI Isolation:** Rules with a `cli_filter` only apply when the matching CLI is active.
4. **Mandatory Guardrails:** A `GLOBAL` or `PROJECT` rule marked `is_mandatory=True` with `effect=DENY` **cannot be overridden** by any task instruction or higher-scope ALLOW.
5. **Status Stability:** `memory_status`, `rules_status`, `rule_decision`, and `decision` are deterministic across repeated calls with the same state.

---

## 11. Public API Surface

The canonical entry point for all Member 1 and Member 3 consumption is:

```python
from rag_rules_service import (
    LayaIntelligenceService,    # Main facade
    LayaIntelligenceContext,    # Result type
    SubsystemStatus,            # Health enum
    RuleDecision,               # Decision enum
    TaskLike,                   # Task protocol
)
```

`memory/intelligence.py` is the internal implementation module. Import from `rag_rules_service` for external consumption.
