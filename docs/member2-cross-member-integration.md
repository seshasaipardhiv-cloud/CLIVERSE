# Member 2 Cross-Member Integration Specification

**Subsystem:** CLIVERSE — Member 2 (Memory / RAG & Rules Intelligence)  
**Target Consumers:** Member 1 (Laya Engine & Core Planning), Member 3 (Dashboard), Member 4 (Security & Trust)  
**Status:** Frozen & Verified (Milestones: Stage 1 — Foundation, Stage 2 — Ingestion + Embedding Foundation, Stage 3 — Retrieval + Context Assembly, Stage 3.5 — RAG Validation + Hardening, Stage 4 — Rules Intelligence, Stage 5 — Unified Laya Intelligence Contract, Stage 5.1 — Integration Safety Hardening, Stage 6 — Real Cross-Member Integration, Final — Hardening + Handoff — 150 Tests Green)

---

## 1. Overview & Architectural Position

Member 2 serves as the cognitive and constraint intelligence provider for CLIVERSE.

```
                    USER TASK
                       │
                       ▼
                 MEMBER 1 LAYA
               (RequestPlanner)
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
   Adapter Protocol            Direct Facade
(MemoryProvider Protocol) (build_intelligence_context)
         │                           │
         └─────────────┬─────────────┘
                       ▼
          MEMBER 2 INTELLIGENCE
          ├── RetrievalService (Semantic RAG)
          └── RulesEngine (Constraint Resolution)
                       │
                       ▼
            LayaIntelligenceContext
                       │
                       ▼
            MEMBER 1 STRUCTURED TASK
                       │
                       ▼
              MEMBER 4 TRUSTGATE
         (Security, Sandbox & Audit)
                       │
                       ▼
               CLI EXECUTION
```

---

## 2. Canonical Public Imports

All external consumers must import strictly from the top-level public facade:

```python
from rag_rules_service import (
    # Core unified intelligence service & context
    LayaIntelligenceService,
    LayaIntelligenceContext,
    
    # Member 1 RequestPlanner adapter
    CliverseMemoryProviderAdapter,
    
    # Enums & protocols
    SubsystemStatus,
    RuleDecision,
    TaskLike,
    format_combined_laya_context,
)
```

**Rule:** Consumers must **never** import internal implementation modules directly (such as `memory.storage.sqlite_store`, `rules.resolver`, or `memory.embeddings.local_engine`).

---

## 3. Real Member 1 Integration Contracts

Member 2 supports **two native integration pathways** with Member 1:

### Pathway A: Native `RequestPlanner` Adapter (Member 1 Protocol)

Member 1's `RequestPlanner` requires an object implementing `cliverse.contracts.MemoryProvider`:

```python
from cliverse.planning import RequestPlanner, PlanningRequest
from rag_rules_service import CliverseMemoryProviderAdapter

# 1. Initialize Member 2 adapter with project & CLI scope
adapter = CliverseMemoryProviderAdapter(
    project_id="my-project",
    cli_name="claude-cli",
)

# 2. Connect directly to Member 1 RequestPlanner
planner = RequestPlanner(memory_provider=adapter)

# 3. Plan user request
plan_result = planner.plan(PlanningRequest(
    task="Add JWT authentication to the API",
    role="Backend Engineer",
    requirements=("Use RS256 algorithm",),
))

# plan_result.task is a StructuredTask with Member 2 context and rule constraints injected
print(plan_result.task.context)
print(plan_result.task.constraints)
```

### Pathway B: Direct Unified Facade (`build_intelligence_context`)

When Member 1 (or Member 3 Dashboard) requires the full `LayaIntelligenceContext` packet:

```python
from rag_rules_service import LayaIntelligenceService, LayaIntelligenceContext

service = LayaIntelligenceService()

# Accepts Member 1 StructuredTask, TaskLike objects, or plain strings:
intelligence: LayaIntelligenceContext = service.build_intelligence_context(
    task=structured_task,  # or "Add JWT authentication"
    project_id="my-project",
    cli_name="claude-cli",
    top_k=5,
    min_score=0.35,
    context_budget_tokens=2000,
)
```

---

## 4. Input & Output Contract Specifications

### Input Contract: `TaskLike`

```python
@runtime_checkable
class TaskLike(Protocol):
    task: str
    def as_dict(self) -> Dict[str, Any]: ...
```

Supported inputs for `task`:
- `str`: Plain string query (e.g. `"Add JWT authentication"`).
- `StructuredTask`: Member 1 frozen dataclass with `.task` and `.as_dict()`.
- Any object implementing `TaskLike`.

### Output Contract: `LayaIntelligenceContext`

| Field | Type | Description |
|---|---|---|
| `task` | `str` | Normalized task string. |
| `project_id` | `Optional[str]` | Active project identifier (strictly isolated). |
| `cli_name` | `Optional[str]` | Active CLI adapter identifier (e.g. `claude-cli`, `aider`). |
| `memory_context` | `ContextPacket` | Complete retrieved memory packet with items, token estimate, and provenance. |
| `applicable_rules` | `List[Rule]` | All rules matched to the task and active scope. |
| `rule_resolution` | `RuleResolution` | Deterministic resolution with winning rules, suppressed rules, and explanation trace. |
| `context_sources` | `List[str]` | File paths and line ranges cited in retrieved memory. |
| `rule_explanations` | `List[str]` | Human-readable explanation traces of conflict resolutions. |
| `combined_laya_context` | `str` | Clean, multi-section Markdown block formatted for Laya prompt injection. |
| `memory_status` | `SubsystemStatus` | `OK_WITH_RESULTS` \| `OK_EMPTY` \| `ERROR`. |
| `rules_status` | `SubsystemStatus` | `OK_WITH_RESULTS` \| `OK_EMPTY` \| `ERROR`. |
| `rule_decision` | `RuleDecision` | Developer/project rule resolution decision (see Section 6). |
| `decision` | `str` | Backward-compatible string alias of `rule_decision`. |
| `metadata` | `Dict[str, Any]` | Audit metadata including task dictionary fields, statuses, and error messages. |

---

## 5. Subsystem Status Semantics

Member 2 enforces strict tri-state operational statuses:

```python
class SubsystemStatus(str, Enum):
    OK_WITH_RESULTS = "OK_WITH_RESULTS"  # Ran successfully; matched items/rules
    OK_EMPTY        = "OK_EMPTY"         # Ran successfully; no items/rules matched
    ERROR           = "ERROR"            # Unhandled exception occurred
```

### Invariants:
1. `OK_EMPTY` and `ERROR` are **never conflated**.
2. A memory retrieval error is **never** presented as `"No relevant project memory found"`.
3. A rules engine failure produces `rules_status=ERROR` and `rule_decision=UNKNOWN` — it is **never** silently converted to `ALLOW`.

---

## 6. Rule Decision Semantics & Security Boundary

```python
class RuleDecision(str, Enum):
    ALLOW   = "ALLOW"    # Permitted; no conflicting restrictions
    WARN    = "WARN"     # Permitted with advisory warning
    REQUIRE = "REQUIRE"  # Positive prerequisite constraint (e.g. tests must pass)
    ASK     = "ASK"      # Human confirmation required before continuing
    DENY    = "DENY"     # Hard prohibition by engineering guardrail
    UNKNOWN = "UNKNOWN"  # Rules evaluation failed; unresolved
```

### Precedence Ordering:
$$\text{DENY (6)} \succ \text{ASK (5)} \succ \text{REQUIRE / ENFORCE (4)} \succ \text{WARN (2)} \succ \text{ALLOW (1)}$$

### Absolute Security Boundary:
> **`rule_decision` represents developer/project constraint resolution only.**  
> **It is NOT the final security or execution authorization.**  
> Member 4's `TrustGate` governs final execution authorization, sandboxing, identity verification, and audit logging. Member 2 never authorizes CLI commands or filesystem access.

---

## 7. Multi-Project & CLI Isolation Guarantees

1. **Project Boundary:** Memory chunks and rules for `project_id="alpha"` will never be retrieved or evaluated when querying `project_id="beta"`.
2. **CLI Boundary:** Rules with `cli_filter="claude-cli"` will never apply when `cli_name="aider"`.
3. **Mandatory Guardrails:** A `GLOBAL` or `PROJECT` rule with `is_mandatory=True` and `effect=DENY` cannot be overridden by higher-scope `TASK` rules.

---

## 8. Compatibility Matrix

| Member 1 Field / Concept | Member 2 Field / Concept | Compatibility | Adapter Mapping |
|---|---|---|---|
| `StructuredTask.task` | `task_str` | Native | Extracted via `_extract_task_text()` |
| `StructuredTask.role` | `metadata["role"]` | Native | Preserved via `as_dict()` |
| `StructuredTask.context` | `ContextPacket.assembled_prompt_text` | Native | Mapped in `CliverseMemoryProviderAdapter` |
| `StructuredTask.requirements` | `metadata["requirements"]` | Native | Preserved via `as_dict()` |
| `StructuredTask.constraints` | `RuleResolution.winning_rules` | Native | Converted to `cliverse.contracts.Rule` |
| `ContextBundle` | `ContextPacket` | Adapted | Converted by `CliverseMemoryProviderAdapter` |
| `cliverse.contracts.Rule` | `rules.models.Rule` | Adapted | Mapped by `CliverseMemoryProviderAdapter` |
| `MemoryProvider` Protocol | `CliverseMemoryProviderAdapter` | Native | 100% protocol compliance |
| Plain string query | `task: str` | Native | Supported directly |
