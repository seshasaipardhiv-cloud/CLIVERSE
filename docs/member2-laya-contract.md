# Member 2 $\rightarrow$ Member 1 (Laya) Integration Contract

**Subsystem:** CLIVERSE — Member 2 (Memory / RAG & Rules Intelligence)  
**Contract Version:** 1.0 (Stage 5 Complete)  
**Target Consumer:** Member 1 (Core Execution Engine & Laya Intent Processor)  
**Status:** Implemented & Verified (123 Tests Green)  

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
```

Member 2 keeps memory retrieval and rules evaluation logically separated internally, while providing a single, unified, serializable result object: [`LayaIntelligenceContext`](file:///A:/CLIVERSE/memory/intelligence.py).

---

## 2. Quickstart for Member 1

```python
from rag_rules_service import LayaIntelligenceService, LayaIntelligenceContext

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

# 3. Check overall rule decision
if intelligence.decision == "DENY":
    print("Action blocked by engineering guardrails:", intelligence.rule_explanations)
elif intelligence.decision == "ASK":
    print("Action requires human confirmation:", intelligence.rule_explanations)

# 4. Inject formatted context directly into Laya prompt
prompt_block = intelligence.combined_laya_context
```

---

## 3. Data Contract: `LayaIntelligenceContext`

The result object exposes typed fields for both unified text generation and granular programmatic inspection:

| Field | Type | Description |
|---|---|---|
| `task` | `str` | Normalized user task prompt. |
| `project_id` | `Optional[str]` | Active project identifier (strictly isolated). |
| `cli_name` | `Optional[str]` | Active CLI adapter identifier (e.g. `claude-cli`, `aider`). |
| `memory_context` | `ContextPacket` | Complete Stage 3 memory packet with ranked items, snippets, token estimates, and provenance. |
| `applicable_rules` | `List[Rule]` | All rules that passed scope, project, CLI, and condition filters. |
| `rule_resolution` | `RuleResolution` | Stage 4 deterministic resolution output containing winning rules, suppressed rules, conflicts, and trace. |
| `context_sources` | `List[str]` | List of file paths and line ranges cited in retrieved memory. |
| `rule_explanations` | `List[str]` | List of human-readable conflict override and tie-break explanations. |
| `combined_laya_context` | `str` | Clean, multi-section Markdown block ready for prompt injection. |
| `decision` | `str` | Overall status: `"ALLOW"`, `"WARN"`, `"ASK"`, or `"DENY"`. |
| `metadata` | `Dict[str, Any]` | Audit metadata including execution statuses (`"memory_status"`, `"rules_status"`). |

---

## 4. Prompt Context Layout (`combined_laya_context`)

The `combined_laya_context` string is structured into three clear sections:

```markdown
### PROJECT CONTEXT

[MEMORY 1]
Source: docs/architecture.md:12-40
Type: doc
Relevance: 0.91

FastAPI backend architecture with PostgreSQL for persistent relational data.

[MEMORY 2]
Source: decisions/auth.md:1-8
Type: decision
Relevance: 0.87

Authentication uses JWT tokens signed with RS256 algorithm.

### APPLICABLE RULES

[PROJECT]
* Use PostgreSQL for all database operations.

[CLI]
* Ask confirmation before installing new packages.

### RULE RESOLUTION

Decision: ALLOW

No blocking conflict detected.
```

If Member 1 prefers to place Memory and Rules in separate prompt sections, it can access them independently:
- **Memory only:** `intelligence.memory_context.assembled_prompt_text`
- **Rules only:** `intelligence.rule_resolution.constraints_prompt_text`

---

## 5. Ephemeral Task-Level Rules

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

By scope precedence, this `TASK` rule will override any non-mandatory `PROJECT` or `GLOBAL` rule targeting `database`.

---

## 6. Error & Empty-State Semantics

| Scenario | Memory Context | Applicable Rules | Decision | Notes |
|---|---|---|---|---|
| **Normal (Hits & Rules)** | Populated with ranked items | Populated with winning rules | `ALLOW` / `WARN` / `ASK` / `DENY` | Standard happy path. |
| **No Memory Found** | `items = []`, placeholder text | Rules as normal | Based on rules | Valid empty packet; no crash. |
| **No Rules Applicable** | Items as normal | `applicable_rules = []` | `ALLOW` | Valid empty rules set; no crash. |
| **Memory Error** | `items = []`, `metadata["memory_status"]="error"` | Rules as normal | Based on rules | Fail-safe: rules continue to evaluate. |
| **Rules Error** | Items as normal | `applicable_rules = []`, `metadata["rules_status"]="error"` | `ALLOW` | Fail-safe: memory continues to evaluate. |

---

## 7. Determinism & Isolation Guarantees

1. **Deterministic Resolution:** Given identical memory and rules states, repeated calls produce identical results, identical rankings, and identical text traces.
2. **Project Isolation:** Project Alpha never retrieves Project Beta memory, and Project Alpha never applies Project Beta rules.
3. **CLI Isolation:** Rules with a `cli_filter` only apply when the matching CLI is active.
4. **Mandatory Guardrails:** A lower-scope `GLOBAL` or `PROJECT` rule marked `is_mandatory=True` with `effect=DENY` **cannot be overridden** by any task instruction.
