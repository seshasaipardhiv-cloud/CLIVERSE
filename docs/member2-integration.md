# Member 2 Integration Guide: Memory & Retrieval Interfaces

**Subsystem:** CLIVERSE — Member 2 (Memory / RAG + Rules Intelligence)  
**Status:** Stages 1, 2, 3, 3.5, 4, 5, 5.1 & 6 Complete — 142 Tests Green (Final Handoff Ready)  
**Target Consumers:** Member 1 (Core + Laya Engine), Member 3 (Dashboard UI)  

---

## 1. Overview & Current Status

This guide specifies how external subsystems interact with Member 2's persistent memory, ingestion, semantic search, rules evaluation, and unified intelligence context services.

| Component | Status | Description |
|---|---|---|
| **Models & Storage** | ✅ **Implemented (Stage 1)** | `MemoryRecord`, `MemoryChunk`, `SQLiteMemoryStorage` |
| **Rules Models** | ✅ **Implemented (Stage 1)** | `Rule`, `RuleScope`, `RuleEffect`, `RuleConflict` |
| **Text Normalization** | ✅ **Implemented (Stage 2)** | Unicode NFC, CRLF $\rightarrow$ LF, trailing whitespace strip, structure preservation |
| **Deterministic Chunker** | ✅ **Implemented (Stage 2)** | Natural boundary detection (Markdown headers, code blocks, conversation turns) + line-level bounds |
| **SHA-256 Deduplication** | ✅ **Implemented (Stage 2)** | Incremental indexing: `NEW`, `MODIFIED`, and `UNMODIFIED` (skip) |
| **Embedding Abstraction** | ✅ **Implemented (Stage 2)** | `EmbeddingProvider` interface + `LocalBaselineEmbeddingProvider` (deterministic offline engine) |
| **Ingestion Pipeline** | ✅ **Implemented (Stage 2)** | `IngestionPipeline.ingest(...)` orchestration with strict project isolation and provenance |
| **Retrieval Engine & Hybrid Search** | ✅ **Implemented (Stage 3)** | Semantic vector search + lexical overlap scoring with min_score and top_k |
| **Ranking & Deduplication** | ✅ **Implemented (Stage 3)** | Line overlap detection, exact text duplicate stripping, score-descending order |
| **Context Assembly** | ✅ **Implemented (Stage 3)** | `ContextAssembler` generating source-backed markdown blocks bounded by token budget |
| **Rules Engine & Resolver** | ✅ **Implemented (Stage 4)** | Rule parser, priority weighting, mandatory guardrails, conflict resolution trace |
| **Unified Intelligence Contract** | ✅ **Implemented (Stage 5)** | `build_intelligence_context()` coordinating Memory + Rules for Member 1 (Laya) |
| **Safety + Contract Hardening** | ✅ **Implemented (Stage 5.1)** | `SubsystemStatus`, `RuleDecision`, `TaskLike` protocol; strict ERROR vs OK_EMPTY semantics |
| **REST API Router** | ⏳ *Planned (Post-Hackathon)* | FastAPI endpoints for Member 3 Dashboard |

---

## 2. Ingestion Pipeline Interface (Stage 2)

### Python Usage Example

```python
from memory.ingestion import IngestionPipeline, IngestionResult

pipeline = IngestionPipeline()

result: IngestionResult = pipeline.ingest(
    content="# Auth Guide\nUse JWT tokens for session auth.\n",
    project_id="my-project",
    source_type="doc",            # "doc" | "code" | "conversation" | "decision"
    source_path="docs/auth.md",    # Filepath or source identifier
    title="Authentication Guide",  # Optional human-readable title
    session_id=None,               # Optional session ID
    tags=["auth", "security"],     # Optional tag list
    metadata={"author": "team"},   # Optional custom metadata
)
```

---

## 3. Retrieval & Context Assembly Interfaces (Stage 3)

The primary entry point consumed by Member 1 (Laya) for memory-only queries is `RetrievalService`.

```python
from memory.retrieval import RetrievalService
from memory.models import ContextPacket, MemorySearchResult

memory_service = RetrievalService()
```

### 3.1 Raw Memory Search (`search_memory`)

Returns ranked search hits with line ranges, relevance scores, and metadata:

```python
results = memory_service.search_memory(
    query="database architecture",
    project_id="my-project",
    top_k=5,
    min_score=0.35,
    source_types=["decision", "doc"],  # Optional filter
    session_id=None,                   # Optional session filter
    source_path=None,                  # Optional path filter
)

for hit in results:
    print(f"[{hit.score:.2f}] {hit.source_path}:{hit.start_line}-{hit.end_line} ({hit.source_type})")
    print(hit.content)
```

### 3.2 Context Packet Retrieval for Laya (`retrieve_context`)

Retrieves relevant items and formats them into a structured prompt block bounded by a token budget:

```python
context: ContextPacket = memory_service.retrieve_context(
    task="Add JWT authentication",
    project_id="my-project",
    top_k=5,
    min_score=0.2,
    context_budget_tokens=2000,
)

print(context.assembled_prompt_text)
```

---

## 4. Scoring, Filtering & Deduplication Semantics

### Hybrid Scoring Formula
$$\text{Final Score} = 0.7 \times \text{Cosine Similarity} + 0.3 \times \text{Keyword Overlap}$$
* If no vector embedding is present, falls back to normalized lexical overlap.
* Scores are strictly normalized in $[0.0, 1.0]$.

### Deterministic Deduplication
* **Exact Duplicate Content / Hashes:** Automatically collapses duplicate text across chunks, retaining the highest-scoring candidate.
* **Overlapping Line Ranges:** If two chunks from the same document share $>60\%$ line overlap, only the higher-scoring chunk is included. Distinct sections from the same file remain fully preserved.

### Token Budget & Provenance
* Token estimation: $\max(1, \lceil \text{length} / 4 \rceil)$.
* Stops appending items when cumulative tokens reach `context_budget_tokens`.
* `ContextPacket.provenance_summary` includes item counts, source file lists, source types, score ranges, and session IDs.

---

## 5. Rules Intelligence Engine Interfaces (Stage 4)

The primary service for rules management is [`RulesEngine`](file:///A:/CLIVERSE/rules/engine.py).

```python
from rules import RulesEngine, Rule, RuleScope, RuleEffect, RuleResolution

engine = RulesEngine()
```

### 5.1 Querying Applicable Rules (`get_applicable_rules`)

```python
rules = engine.get_applicable_rules(
    task="Deploy production database migration",
    project_id="my-project",
    cli_name="claude-cli",
)
```

### 5.2 Deterministic Conflict Resolution (`resolve_rules`)

Returns winning rules, suppressed rules, detected conflicts, human-readable trace, and structured prompt text:

```python
resolution: RuleResolution = engine.resolve_rules(
    task="Deploy production database migration",
    project_id="my-project",
    cli_name="claude-cli",
)
```

---

## 6. Stage 5 / 5.1 Unified Intelligence Contract (`build_intelligence_context`)

The primary facade coordinating both Memory and Rules into one unified Laya-ready package is [`LayaIntelligenceService`](file:///A:/CLIVERSE/memory/intelligence.py). Import exclusively from the canonical public entry point:

```python
from rag_rules_service import (
    LayaIntelligenceService,
    LayaIntelligenceContext,
    SubsystemStatus,   # OK_WITH_RESULTS | OK_EMPTY | ERROR
    RuleDecision,      # ALLOW | WARN | REQUIRE | ASK | DENY | UNKNOWN
    TaskLike,          # Protocol for StructuredTask-compatible objects
)

service = LayaIntelligenceService()

intelligence: LayaIntelligenceContext = service.build_intelligence_context(
    task="Add JWT authentication and update database schema",
    project_id="my-project",
    cli_name="claude-cli",
    top_k=5,
    min_score=0.35,
    context_budget_tokens=2000,
)
```

`task` may be a `str`, Member 1's `StructuredTask`, or any object satisfying the `TaskLike` protocol (has `.task: str` and `.as_dict() -> dict`).

### 6.1 Subsystem Status Semantics (Stage 5.1)

> **Rule:** `OK_EMPTY` and `ERROR` are **never interchangeable.**

| `memory_status` / `rules_status` | Meaning | Prompt text |
|---|---|---|
| `OK_WITH_RESULTS` | Subsystem ran; found data | Items/rules shown |
| `OK_EMPTY` | Subsystem ran; found nothing (valid) | "No relevant project memory found" / "No applicable engineering rules" |
| `ERROR` | Subsystem raised an exception | "Memory subsystem error: …" / "Rules subsystem error: …" |

Always check status before acting on the result:

```python
if intelligence.memory_status == SubsystemStatus.ERROR:
    # Do NOT treat this as "no relevant memory"
    handle_memory_error(intelligence.metadata["memory_error"])

if intelligence.rules_status == SubsystemStatus.ERROR:
    # rule_decision is UNKNOWN — do NOT default to ALLOW
    handle_rules_error(intelligence.metadata["rules_error"])
```

### 6.2 RuleDecision Semantics (Stage 5.1)

> **`rule_decision` represents developer/project rule resolution only.**  
> **It is NOT the final security or execution authorization (owned by Member 4).**

| `rule_decision` | Meaning |
|---|---|
| `ALLOW` | No applicable rules, or all rules permit |
| `WARN` | Advisory warning; action may continue |
| `REQUIRE` | Positive prerequisite constraint (e.g. "Tests must pass") |
| `ASK` | Human confirmation required before continuing |
| `DENY` | Hard prohibition; action is blocked by guardrail |
| `UNKNOWN` | Rules engine failed; resolution unavailable — do NOT treat as ALLOW |

### 6.3 Quick Usage

```python
# Overall rule decision
print("Decision:", intelligence.decision)         # str alias of rule_decision
print("Rule decision:", intelligence.rule_decision)  # RuleDecision enum

# Subsystem health
print("Memory:", intelligence.memory_status)
print("Rules:", intelligence.rules_status)

# Unified formatted prompt text
print(intelligence.combined_laya_context)

# Granular access
print("Memory items:", len(intelligence.memory_context.items))
print("Winning rules:", len(intelligence.rule_resolution.winning_rules))
print("Sources cited:", intelligence.context_sources)
```
