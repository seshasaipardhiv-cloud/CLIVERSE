# Member 2 Final Handoff Specification

**Subsystem:** CLIVERSE — Member 2 (Memory / RAG + Rules Intelligence)  
**Status:** COMPLETE & FROZEN (Milestones: Stage 1 — Foundation, Stage 2 — Ingestion + Embedding Foundation, Stage 3 — Retrieval + Context Assembly, Stage 3.5 — RAG Validation + Hardening, Stage 4 — Rules Intelligence, Stage 5 — Unified Laya Intelligence Contract, Stage 5.1 — Integration Safety Hardening, Stage 6 — Real Cross-Member Integration, Final — Hardening + Handoff)  
**Test Suite:** 145 Tests Passing (Zero Regressions, Authoritative Verified Total)  
**Authors:** Member 2 Engineering Lead

---

## 1. Member 2 Ownership & Scope

Member 2 is the **Cognitive Backbone** of CLIVERSE. It owns:
- **`memory/`**: Persistent storage (SQLite), ingestion pipeline, deterministic text chunker, SHA-256 deduplication, embedding abstraction, local hash-bucket embedding baseline, hybrid retrieval engine (cosine + keyword overlap), score-threshold filtering, line-overlap deduplication, and source provenance context assembly.
- **`rules/`**: Hierarchical rule models (`GLOBAL`, `PROJECT`, `CLI`, `TASK`), YAML/JSON parsing, syntax/condition validation, applicability matching, priority weighting, conflict detection, deterministic resolution with explainable traces, and persistent file-based rule storage.
- **`rag_rules_service.py`**: The canonical public integration facade and adapter layer connecting Member 2 to Member 1 (Laya), Member 3 (Dashboard), and Member 4 (Security).
- **`tests/`**: All Member 2 unit, integration, validation, and contract test suites.
- **`docs/`**: Member 2 technical specifications and contracts.

---

## 2. Canonical Public Import & API Surface

All external consumers (Member 1, Member 3, and Member 4) must interface strictly via:

```python
from rag_rules_service import (
    # Facades & Context
    LayaIntelligenceService,
    LayaIntelligenceContext,
    
    # Member 1 Protocol Adapter
    CliverseMemoryProviderAdapter,
    
    # Enums & Protocols
    SubsystemStatus,
    RuleDecision,
    TaskLike,
    format_combined_laya_context,
)
```

### Frozen Public Methods:

#### Unified Intelligence
```python
service.build_intelligence_context(
    task: Union[str, TaskLike, Any],
    project_id: Optional[str] = None,
    cli_name: Optional[str] = None,
    task_rules: Optional[List[Rule]] = None,
    top_k: int = 5,
    min_score: float = 0.35,
    context_budget_tokens: int = 2000,
    task_metadata: Optional[Dict[str, Any]] = None,
) -> LayaIntelligenceContext
```

#### Memory Operations
```python
service.store_memory(content: str, project_id: str, source_type: str = "doc", source_path: str = "unknown", title: Optional[str] = None, session_id: Optional[str] = None, tags: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None) -> IngestionResult
service.search_memory(query: str, project_id: Optional[str] = None, top_k: int = 5, min_score: float = 0.35, source_types: Optional[List[str]] = None, session_id: Optional[str] = None, source_path: Optional[str] = None) -> List[MemorySearchResult]
service.retrieve_context(task: str, project_id: Optional[str] = None, top_k: int = 5, min_score: float = 0.35, context_budget_tokens: int = 2000) -> ContextPacket
service.delete_memory(record_id: str) -> bool
```

#### Rules Operations
```python
service.create_rule(rule: Rule) -> Rule
service.get_rule(rule_id: str) -> Optional[Rule]
service.update_rule(rule: Rule) -> Rule
service.delete_rule(rule_id: str) -> bool
service.list_rules(scope: Optional[RuleScope] = None, project_id: Optional[str] = None) -> List[Rule]
service.get_applicable_rules(task: Union[str, TaskLike, Any], project_id: Optional[str] = None, cli_name: Optional[str] = None, task_metadata: Optional[Dict[str, Any]] = None, task_rules: Optional[List[Rule]] = None) -> List[Rule]
service.resolve_rules(task: Union[str, TaskLike, Any], project_id: Optional[str] = None, cli_name: Optional[str] = None, task_metadata: Optional[Dict[str, Any]] = None, task_rules: Optional[List[Rule]] = None) -> RuleResolution
```

---

## 3. Subsystem Operational Statuses & Error Semantics

Member 2 strictly enforces explicit operational statuses:

```python
class SubsystemStatus(str, Enum):
    OK_WITH_RESULTS = "OK_WITH_RESULTS"
    OK_EMPTY        = "OK_EMPTY"
    ERROR           = "ERROR"
```

### Safety Invariants:
1. **Never mask ERROR as OK_EMPTY:** If SQLite retrieval fails, `memory_status = ERROR` and the prompt displays `*(Memory subsystem error: <error details>)*`. It is **never** formatted as `"No relevant project memory found"`.
2. **Never mask ERROR as ALLOW:** If the rules engine fails, `rules_status = ERROR` and `rule_decision = UNKNOWN`. It is **never** silently permitted as `ALLOW`.
3. **Empty states are explicit:** If zero memories match, `memory_status = OK_EMPTY` and prompt displays `*(No relevant project memory found)*`. If zero rules match, `rules_status = OK_EMPTY` and `rule_decision = ALLOW`.

---

## 4. Rule Decision Semantics & Hierarchy

### Canonical Rule Effects:
- **`ALLOW`**: Explicit permission or allowance.
- **`WARN`**: Permitted with an advisory warning in planning prompt.
- **`REQUIRE`**: Positive engineering constraint directive (e.g. "Tests must pass before commit"). Rendered with explicit `[REQUIRE]` tag in context.
- **`ASK`**: Requires interactive user confirmation prior to execution.
- **`DENY`**: Hard negative constraint prohibition.
- *(Note: `ENFORCE` is maintained as a backward-compatible alias of `REQUIRE`. `UNKNOWN` is a result state representing evaluation failure).*

```python
class RuleDecision(str, Enum):
    ALLOW   = "ALLOW"
    WARN    = "WARN"
    REQUIRE = "REQUIRE"
    ASK     = "ASK"
    DENY    = "DENY"
    UNKNOWN = "UNKNOWN"
```

### Scope Weighting:
$$\text{TASK (400)} \succ \text{CLI (300)} \succ \text{PROJECT (200)} \succ \text{GLOBAL (100)}$$
Effective priority: $\text{Score} = \text{Scope Weight} + \text{Rule Priority (0–99)}$.

### Severity Tie-Breaking:
$$\text{DENY (6)} \succ \text{ASK (5)} \succ \text{REQUIRE / ENFORCE (4)} \succ \text{WARN (2)} \succ \text{ALLOW (1)}$$

### Mandatory Guardrails:
Any rule marked `is_mandatory=True` with `effect=DENY` in `GLOBAL` or `PROJECT` scope **cannot be overridden** by higher-scope rules.

### Member 1 Adapter Semantic Preservation:
When converting Member 2 rules to Member 1 `cliverse.contracts.Rule`:
- Mandatory rules: `content = "[{effect} MANDATORY] {description}"`, `priority = 9999 + effective_priority`.
- Non-mandatory rules: `content = "[{effect}] {description}"`, `priority = effective_priority`.
- Rich provenance: `source = "rules:{target};effect={effect};mandatory={is_mandatory};version={version}"`.
- Full model access: `cliverse_rule._member2_rule` references original `Rule`, and `adapter.get_member2_rule(rule_id)` retrieves it.
- Zero duplicate evaluation: `build_intelligence_context` evaluates applicable rules once and passes them directly to `resolve_rules(applicable_rules=...)`.

---

## 5. Security & Governance Boundary (Member 4)

> **`rule_decision` represents developer/project constraints only.**  
> **It is NOT the final security or execution authorization.**

The conceptual pipeline is:
$$\text{USER} \rightarrow \text{MEMBER 1 (Laya)} \rightarrow \text{MEMBER 2 (Memory + Rules)} \rightarrow \text{MEMBER 4 (TrustGate)} \rightarrow \text{EXECUTION}$$

Member 2 does **not** evaluate identity tokens, sandbox policies, secrets protection, or regulatory audit compliance. That responsibility belongs to Member 4 (`trust_gate.py`).

---

## 6. Integration with Other Members

### Member 1 (Core & Laya Planning)
- **Adapter Consumption:** Connect via `CliverseMemoryProviderAdapter(project_id=..., cli_name=...)` and pass directly to `RequestPlanner(memory_provider=adapter)`.
- **Direct Consumption:** Pass `StructuredTask` into `LayaIntelligenceService.build_intelligence_context()`.

### Member 3 (Dashboard UI)
- Call `service.search_memory()` or `service.list_rules()` to inspect state.
- Call `service.build_intelligence_context().model_dump()` to render the full context, decision trace, and conflict explanations in JSON.

---

## 7. Setup & Execution Commands

### Environment Setup:
```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
pip install -e .
```

### Running Member 2 Tests:
```bash
python -m pytest tests/test_memory_storage_models.py \
                 tests/test_ingestion_embeddings.py \
                 tests/test_retrieval_context.py \
                 tests/test_rag_validation.py \
                 tests/test_rules_engine.py \
                 tests/test_laya_intelligence_integration.py \
                 tests/test_stage51_hardening.py \
                 tests/test_final_cross_member_integration.py -v
```

### Machine-Verified Test Suite Breakdown:

| Test File | Passed | Failed | Total | Primary Coverage |
|---|---|---|---|---|
| `tests/test_memory_storage_models.py` | 5 | 0 | 5 | Memory models, schemas, SQLite persistence |
| `tests/test_ingestion_embeddings.py` | 12 | 0 | 12 | Normalization, chunking, deduplication, local embeddings |
| `tests/test_retrieval_context.py` | 12 | 0 | 12 | Hybrid search, ranking, thresholding, context assembly |
| `tests/test_rag_validation.py` | 43 | 0 | 43 | RAG validation suite, edge cases, deterministic behavior |
| `tests/test_rules_engine.py` | 29 | 0 | 29 | Rule parsing, validation, scopes, resolver, conflict traces |
| `tests/test_laya_intelligence_integration.py` | 11 | 0 | 11 | LayaIntelligenceService facade and integration |
| `tests/test_stage51_hardening.py` | 19 | 0 | 19 | Safety hardening, tri-state statuses, error vs empty |
| `tests/test_final_cross_member_integration.py` | 14 | 0 | 14 | Cross-member adapter, zero-duplicate eval, input validation |
| **Total Member 2 Suite** | **145** | **0** | **145** | **Authoritative verified count** |

### Running RAG Evaluation:
```bash
python scripts/evaluate_retrieval.py
```

### Running Member 4 Test Runner:
```bash
python run_tests.py
```

---

## 8. RAG Evaluation Metrics (Actual Baseline)

Evaluated against 10 documents, 58 chunks, and 25 queries (`tests/fixtures/retrieval_eval.json`):

| Metric | K=1 | K=3 | K=5 |
|---|---|---|---|
| **Recall@K** | 66.0% | 84.0% | 88.0% |
| **Precision@K** | 76.0% | 46.7% | 36.0% |

- **Mean Reciprocal Rank (MRR):** 0.817
- **Succeeded (@5):** 23 / 25 queries
- **Failed (@5):** 2 / 25 queries (due to lexical mismatch in the hash-bucket embedding baseline)

---

## 9. Performance Baseline (Local Measurements)

Measured on local SSD storage:
- **Ingestion (10 docs):** ~58.2 ms (~5.8 ms / document)
- **Rule Creation (10 rules):** ~11.4 ms (~1.1 ms / rule)
- **Retrieval:** ~1.5 ms
- **Rule Resolution:** ~63.0 ms
- **Unified Context Construction:** ~19.8 ms

---

## 10. Technical Debt & Known Limitations

| Item | Classification | Description |
|---|---|---|
| **Baseline Embedding** | `MVP-READY` | Local hash-bucket engine (64-dim). Fast, deterministic, zero-dependency. Paraphrase queries with no lexical overlap fail. Plug in neural provider for production. |
| **Token Counting** | `MVP-READY` | Estimated via `max(1, ceil(len / 4))`. Deterministic approximation without external tokenizer dependency. |
| **Compound Rule Logic** | `FUTURE` | Multi-condition rules currently operate with implicit `AND`. Boolean `OR` trees deferred. |
| **File Concurrency** | `MVP-READY` | YAML rules stored in `.cliverse/rules/`. Single-user workstation safe; multi-process write locks deferred. |
| **Storage Scaling** | `MVP-READY` | SQLite persistent database at `.envcore/memory/cliverse_memory.db`. Migration to PostgreSQL + pgvector supported via `MemoryStorage` interface. |

---

## 11. Do-Not-Modify Boundaries

1. **Do NOT modify:** `src/cliverse/` (Member 1 core engine, execution, git, sessions, recovery).
2. **Do NOT modify:** `security/`, `governance/`, `audit/`, `trust_gate.py` (Member 4).
3. **Do NOT modify:** Member 3 UI/Dashboard components.
4. **Do NOT merge:** Memory internal tables into rules or vice-versa.
5. **Do NOT make:** Member 2 authorize execution or run external processes.
