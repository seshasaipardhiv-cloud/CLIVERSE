# Member 2 Final Handoff Specification

**Subsystem:** CLIVERSE — Member 2 (Memory / RAG + Rules Intelligence)  
**Status:** Verified hackathon MVP subsystem (Milestones: Stage 1 — Foundation, Stage 2 — Ingestion + Embedding Foundation, Stage 3 — Retrieval + Context Assembly, Stage 3.5 — RAG Validation + Hardening, Stage 4 — Rules Intelligence, Stage 5 — Unified Laya Intelligence Contract, Stage 5.1 — Integration Safety Hardening, Stage 6 — Real Cross-Member Integration, Final — Hardening + Handoff)  
**Test Suite:** 167 Member 2 Tests Passing (Zero Regressions; Repo: 235 passed, 0 failed, 2 skipped due to documented environment-specific requirements across 237 collected items)  
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
Required Member 2 rule semantics are preserved across the Member 2 → Member 1 adapter contract (`cliverse.contracts.Rule`):
- Mandatory rules: `content = "[{effect} MANDATORY] {description}"`, `priority = 9999 + effective_priority`.
- Non-mandatory rules: `content = "[{effect}] {description}"`, `priority = effective_priority`.
- Rich provenance & target preservation: `source = "rules:{target};target={target};effect={effect};mandatory={is_mandatory};version={version}"`.
- Clean reconstruction: `parse_cliverse_rule_semantics(rule)` recovers `target`, `rule_id`, `description`, `scope`, `priority`, `effect`, `is_mandatory`, and `version` cleanly across deep copies and dataclass serialization without relying on `object.__setattr__` or hidden private attributes.
- Single evaluation: `build_intelligence_context` evaluates applicable rules once and reuses them directly without redundant re-evaluation.

---

## 5. Security & Governance Boundary (Member 4)

> **Member 2 rule_decision is not execution authorization. Member 4 TrustGate is the final execution authorization authority.**  
> `rule_decision` represents developer/project constraints only. It is NOT the final security or execution authorization.

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
| `tests/test_ingestion_embeddings.py` | 14 | 0 | 14 | Normalization, chunking, deduplication, local embeddings, edge cases |
| `tests/test_retrieval_context.py` | 12 | 0 | 12 | Hybrid search, ranking, thresholding, context assembly |
| `tests/test_rag_validation.py` | 44 | 0 | 44 | RAG validation suite, adversarial evaluation runner, edge cases |
| `tests/test_rules_engine.py` | 37 | 0 | 37 | Rule parsing, PyYAML & JSON edge-cases, scopes, resolver, conflict traces |
| `tests/test_laya_intelligence_integration.py` | 11 | 0 | 11 | LayaIntelligenceService facade and integration |
| `tests/test_stage51_hardening.py` | 19 | 0 | 19 | Safety hardening, tri-state statuses, error vs empty |
| `tests/test_final_cross_member_integration.py` | 25 | 0 | 25 | Cross-member adapter, target preservation, deterministic cache key, cache invalidation, frozen dataclass compliance, single-evaluation, whitespace normalization |
| **Total Member 2 Suite** | **167** | **0** | **167** | **Authoritative verified count** |

### Running RAG Evaluations:
```bash
# 1. Historical baseline evaluation (25 queries)
python scripts/evaluate_retrieval.py

# 2. Adversarial diagnostic evaluation (20 queries)
python scripts/evaluate_retrieval_adversarial.py
```

### Running Member 4 Test Runner:
```bash
python run_tests.py
```

---

## 8. RAG Evaluation Metrics

> **Note on Architecture & Embedding Baseline:**
> Member 2's full RAG retrieval architecture with a lightweight deterministic lexical/hash embedding baseline (chunking, deduplication, hybrid retrieval, ranking, context bounding) is implemented. The default `LocalBaselineEmbeddingProvider` is a lightweight lexical/hash baseline (64-dim character n-gram hash projection). It is **NOT** a neural semantic embedding model (such as BERT, sentence-transformers, or OpenAI embeddings) and has no learned weights. Retrieval uses **hybrid cosine similarity + keyword overlap**.

### 8.1. Historical Baseline Evaluation (`tests/fixtures/retrieval_eval.json`)
Evaluated against 10 documents, 58 chunks, and 25 queries:

| Metric | K=1 | K=3 | K=5 |
|---|---|---|---|
| **Recall@K** | 66.0% | 84.0% | 88.0% |
| **Precision@K** | 76.0% | 46.7% | 36.0% |

- **Mean Reciprocal Rank (MRR):** 0.817
- **Succeeded (@5):** 23 / 25 queries
- **Failed (@5):** 2 / 25 queries (due to vocabulary mismatch in hash-bucket baseline)

### 8.2. Adversarial Diagnostic Evaluation (`tests/fixtures/retrieval_eval_adversarial.json`)
Evaluated against 12 documents, 64 chunks, and 20 challenging adversarial queries:
- **Total Queries:** 20 (16 Positive Queries, 4 Negative Queries)
- **Overall Succeeded (@5):** 15 / 20 queries (75.0%)
- **Overall Failed (@5):** 5 / 20 queries (25.0%)

#### Positive Query Metrics (16 Queries — Unpolluted by Negatives):
| Metric | K=1 | K=3 | K=5 |
|---|---|---|---|
| **Recall@K** | 58.3% | 66.7% | 69.8% |
| **Precision@K** | 68.8% | 41.7% | 33.8% |

- **Mean Reciprocal Rank (MRR):** 0.731
- **Positive Succeeded (@5):** 13 / 16 queries
- **Positive Failed (@5):** 3 / 16 queries (attributed to `relevant candidate ranked below top-K`)

#### Negative Query Rejection Metrics (4 Queries):
- **True Negatives (Clean Rejection):** 2 / 4 queries (50.0% rejection rate)
- **False Positives:** 2 / 4 queries (50.0% false-positive rate)
- **Average Candidates Retrieved Above Min Score:** 2.50 candidates

#### Causal Failure Attribution Breakdown (5 Total Failures):
- `relevant candidate ranked below top-K`: 3 queries (extreme synonymy where character n-gram baseline lacked projection)
- `false positive candidates retrieved`: 2 queries (irrelevant queries whose character n-gram noise passed the 0.10 threshold)

---

## 9. Performance Baseline & Storage Scaling (Local Measurements)

### Latency Profiles:
Measured on local SSD workstation storage:
- **Ingestion (10 docs):** ~58.2 ms (~5.8 ms / document)
- **Rule Creation (10 rules):** ~11.4 ms (~1.1 ms / rule)
- **Retrieval:** ~1.5 ms (for 58 chunks)
- **Rule Resolution:** ~63.0 ms
- **Unified Context Construction:** ~19.8 ms

### SQLite Vector Search Scaling Characterization (`scripts/characterize_sqlite_scaling.py`):
| Corpus Size (Chunks) | Avg Search Latency | Throughput (QPS) | Architectural Assessment |
|---|---|---|---|
| **100** | 3.14 ms | 318.8 | Hackathon MVP Ready |
| **500** | 12.23 ms | 81.8 | Hackathon MVP Ready |
| **1,000** | 23.81 ms | 42.0 | Hackathon MVP Upper Bound |
| **2,500** | 58.01 ms | 17.2 | Latency degradation noticeable |
| **5,000** | 121.29 ms | 8.2 | Unacceptable for live keystroke search |

- **Storage Reality:** Search is an in-memory linear table scan $\mathcal{O}(N)$ in SQLite followed by pure-Python cosine loops. Suitable for local Hackathon MVP (<1,000 chunks); ANN vector indexing (sqlite-vec, FAISS, pgvector) is future work.
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
