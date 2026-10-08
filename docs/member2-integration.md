# Member 2 Integration Guide: Memory & Retrieval Interfaces

**Subsystem:** CLIVERSE — Member 2 (Memory / RAG + Rules Intelligence)  
**Status:** Stage 1, 2 & 3 Complete (Models, Ingestion, Deduplication, Embeddings, Retrieval, Context Assembly)  
**Target Consumers:** Member 1 (Core + Laya Engine), Member 3 (Dashboard UI)  

---

## 1. Overview & Current Status

This guide specifies how external subsystems interact with Member 2's persistent memory, ingestion, semantic search, and context assembly services.

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
| **Rules Engine & Resolver** | ⏳ *Planned (Stage 4)* | Rule parser, priority weighting, and conflict resolution trace |
| **REST API Router** | ⏳ *Planned (Stage 5)* | FastAPI endpoints for Member 3 Dashboard |

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

The primary entry point consumed by Member 1 (Laya) is `RetrievalService`.

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
# Output ready to inject into Laya prompt:
# ### Retrieved Project Context
# [MEMORY 1]
# Source: decisions/002-auth.md:1-5
# Type: decision
# Relevance: 0.88
# ...
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
