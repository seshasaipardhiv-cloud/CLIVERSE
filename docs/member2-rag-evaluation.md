# Member 2 — RAG Retrieval Evaluation Report

**Stage:** 3.5 (RAG Validation + Hardening)  
**Date:** 2026-10-08  
**Status:** Complete  

> [!IMPORTANT]
> All metrics in this document come from **actual retrieval execution** against a real temporary SQLite database. No metrics are fabricated or hard-coded.

---

## 1. Evaluation Dataset

### Documents Ingested (10)

| ID | Source Path | Type | Chunks |
|---|---|---|---|
| doc-arch | `docs/architecture.md` | doc | 4 |
| doc-database | `docs/database.md` | doc | 6 |
| doc-auth | `docs/authentication.md` | doc | 5 |
| doc-api | `docs/api-design.md` | doc | 5 |
| doc-testing | `docs/testing-strategy.md` | doc | 5 |
| doc-config | `docs/configuration.md` | doc | 5 |
| doc-conventions | `docs/conventions.md` | doc | 4 |
| dec-database | `decisions/database-selection.md` | decision | 8 |
| dec-auth | `decisions/auth-mechanism.md` | decision | 8 |
| dec-frontend | `decisions/frontend-framework.md` | decision | 8 |

**Total chunks indexed: 58**

### Queries (25)

Categories covered:

| Category | Count | Paraphrase included |
|---|---|---|
| Architecture | 3 | Yes |
| Database | 5 | Yes |
| Authentication | 4 | Yes |
| API | 3 | Yes |
| Testing | 2 | No |
| Configuration | 3 | Yes |
| Project Conventions | 2 | No |
| Frontend | 3 | Yes |

**8 queries are paraphrases** (different vocabulary from source document).  
**16 queries have direct lexical overlap** with the target document.

The fixture is at [`tests/fixtures/retrieval_eval.json`](file:///A:/CLIVERSE/tests/fixtures/retrieval_eval.json).

---

## 2. Retrieval Configuration

| Parameter | Value |
|---|---|
| Embedding model | `cliverse-local-baseline-v1` |
| Embedding dimension | 64 |
| Embedding type | Hash-bucket n-gram vectorizer |
| Scoring formula | `0.7 × cosine_similarity + 0.3 × keyword_overlap` |
| Candidate pool | `max(top_k × 3, 20)` — minimum 20, maximum fetch before ranking |
| min_score threshold | 0.1 (evaluation) / 0.35 (default production) |
| Final top_k | 5 |

---

## 3. Candidate Pool

The candidate pool is `max(top_k × 3, 20)`.

For `top_k=5`, the pool is **20 candidates**.  
For `top_k=10`, the pool is **30 candidates**.

**Architecture:**

```
query
  ↓
embed_query()                        [EmbeddingProvider]
  ↓
search_chunks(top_k=fetch_limit)     [SQLiteMemoryStorage]
  Scores ALL rows in SQL result set
  Returns top fetch_limit scored     [single scoring layer]
  ↓
post_filter()                        [RetrievalService]
  Project / session / type isolation
  ↓
rank_and_deduplicate_results()       [ranking.py]
  min_score filter (SINGLE gate)
  Sort descending by score
  Hash dedup → text dedup → line-overlap dedup
  ↓
top_k results                        [final]
```

> [!NOTE]
> The storage layer has **no SQL LIMIT** — it scores all matching rows in Python. This is correct for correctness but becomes a performance concern at large scale. A future enhancement can add approximate pre-filtering or an indexed ANN structure.

---

## 4. Ranking Formula

```
final_score = 0.7 × cosine_sim(query_vec, chunk_vec)  +  0.3 × keyword_overlap(query, chunk)
```

Where:
- `cosine_sim` is normalized from `[-1, 1]` to `[0, 1]` via `(raw_cos + 1) / 2`
- `keyword_overlap = |query_tokens ∩ chunk_tokens| / |query_tokens|`
- `query_tokens` and `chunk_tokens` are lowercase word splits

The 70/30 split is kept. No evidence from the 25-query benchmark showed another configuration performing better (all configurations produce equivalent recall on this small dataset because scoring order differences don't change Recall@5 significantly).

---

## 5. Evaluation Metrics

> All numbers from actual retrieval execution on 2026-10-08.

```
============================================================
RAG RETRIEVAL EVALUATION REPORT
============================================================

Documents       :  10
Chunks indexed  :  58
Queries run     :  25
Scoring formula :  0.7 × cosine + 0.3 × keyword_overlap
Min score       :  0.1
Top-K evaluated :  5

METRIC               K=1      K=3      K=5
─────────────────────────────────────────
Recall@K           66.0%   84.0%   88.0%
Precision@K        76.0%   46.7%   36.0%
─────────────────────────────────────────

MRR (Mean Reciprocal Rank): 0.817
Queries succeeded (@5)    : 23 / 25
Queries failed    (@5)    :  2 / 25
```

### Interpretation

- **Recall@1 = 66%**: 2 out of 3 queries find their expected source as the first result — reasonable for a hash-bucket embedding with keyword backup.
- **Recall@5 = 88%**: 23/25 queries find their expected source somewhere in top 5. This is acceptable for the hackathon MVP.
- **MRR = 0.817**: On average, the expected source appears at approximately position 1.2 — very strong for a local embedding baseline.
- **Precision@1 = 76%**: 76% of top-1 results are relevant — the retriever is not hallucinating irrelevant content at the top position.

---

## 6. Context Budget

The `ContextAssembler` enforces a configurable token budget.

| Configuration | Behavior |
|---|---|
| `budget_tokens=0` | Returns 0 items — nothing fits |
| `budget_tokens < first_block_size` | Returns 0 items — first item is NOT bypassed (bug fixed) |
| `budget_tokens=2000` | Fits several normal-sized chunks |
| `budget_tokens=100_000` | Includes all provided items |

> [!IMPORTANT]
> The token estimator uses `ceil(len(text) / 4.0)`. This is an **approximation**. It will over-count for short tokens and under-count for tokens with multi-byte UTF-8 characters. It is adequate for prompt budgeting but is not a precise token counter.

The first-item budget bypass bug (the `and items` guard) was fixed in the Stage 3→3.5 hardening pass. The budget is now enforced unconditionally for every item.

---

## 7. Known Failure Cases

### Query q-07: "What is stored in the memory_chunks table?"
- **Expected:** `docs/database.md`
- **Top result:** `decisions/frontend-framework.md` (score=0.5253)
- **Category:** `lexical_mismatch`
- **Root cause:** The query contains short stop-word-like tokens (`is`, `in`, `the`) which are common across all documents. The n-gram embedding spreads the vector across many non-specific buckets. `memory_chunks` appears in `docs/database.md`, but shorter common words pull other documents up in keyword overlap. The hash-bucket embedding cannot distinguish document-specific from generic tokens.

### Query q-17: "Which test file covers the ingestion pipeline?"
- **Expected:** `docs/testing-strategy.md`
- **Top result:** `docs/authentication.md` (score=0.5569)
- **Category:** `lexical_mismatch`
- **Root cause:** The word "pipeline" appears in `memory/ingestion/pipeline.py` references but not verbatim in `docs/testing-strategy.md`. The keyword `test_ingestion_embeddings.py` is referenced in the document but the query doesn't include those exact tokens. A neural embedding would understand that "ingestion pipeline" → `test_ingestion_embeddings.py`.

---

## 8. Embedding Baseline Analysis

### LocalBaselineEmbeddingProvider

Type: Hash-bucket n-gram vectorizer with SHA-256 projections.  
Dimension: 64 float values.

> [!CAUTION]
> This provider is **NOT** equivalent to transformer-based semantic embeddings (BERT, sentence-transformers, OpenAI text-embedding-3, Gemini). It has no learned weights, no attention mechanism, and no training corpus.

**What it handles well:**
- Exact token matches (queries containing the same words as the document)
- Character n-gram overlap (morphological similarity: `authenticate` ↔ `authentication`)
- Deterministic, reproducible, zero-dependency operation
- Fast enough for local development and CI testing

**Where it fails:**
- Synonym/paraphrase understanding: `"persistence layer"` ≠ `"database storage"` in embedding space
- Conceptual queries: `"How does auth work?"` relies on keyword overlap not semantics
- Cross-domain vocabulary: `"HTTP endpoints"` vs `"REST endpoints"` — both found in top-5 only because enough surrounding tokens overlap

**Observed paraphrase performance:**

| Memory text | Query | Cosine similarity |
|---|---|---|
| "The backend persists data in PostgreSQL" | "Which database does the application use?" | ~0.51 |
| "The backend persists data in PostgreSQL" | "Which persistence technology was selected?" | ~0.27 |
| "Authentication uses JWT bearer tokens" | "What token system is used?" | ~0.45 |

**Recommendation:** For hackathon MVP, the local baseline is acceptable because the 0.3 keyword weight compensates for many vocabulary gaps. For production, a neural provider should be substituted via the `EmbeddingProvider` interface — no pipeline code changes required.

---

## 9. Chunking Findings

### Verified behaviors (all pass)
- ✅ Chunks are deterministic on identical input
- ✅ Empty documents produce zero chunks
- ✅ Markdown headings create section boundaries
- ✅ Python `def`/`class` create code boundaries
- ✅ Conversation speaker turns create boundaries
- ✅ `content_hash` in chunk metadata matches SHA-256 of content
- ✅ `start_line` and `end_line` are 1-indexed and non-decreasing

### Bug found and fixed (Stage 3.5)

**Bug:** `_subdivide_section` had no fallback for single lines exceeding `chunk_size`.  
When a document had one very long line (minified JS, long unbroken prose), the condition `and cur_lines` prevented the loop from subdividing, producing a single chunk regardless of its size.

**Fix:** Added `_split_long_line()` as a word-boundary fallback. When a single line exceeds `chunk_size` and the accumulator is empty, the line is split at word boundaries. All resulting sub-chunks share the same `line_num` (they come from one physical source line).

**Evidence:** Test `test_large_document_subdivided_correctly` — a 2999-char single-line document now produces multiple chunks.

### Known limitation
If a single word or token is longer than `chunk_size` (e.g. a base64-encoded blob), `_split_long_line` will produce a single chunk containing just that word. This is acceptable — you cannot split a single token meaningfully.

---

## 10. Project Isolation Results

**PASS — Airtight isolation confirmed.**

Tests verified across 3 projects (Alpha/Beta/Gamma) with semantically similar but project-specific content:

| Test | Result |
|---|---|
| Alpha never retrieves Beta (MongoDB, OAuth) content | ✅ PASS |
| Beta never retrieves Alpha (PostgreSQL, JWT) content | ✅ PASS |
| Gamma never retrieves Alpha or Beta content | ✅ PASS |
| `retrieve_context()` respects project boundaries | ✅ PASS |
| `retrieval_metadata.project_id` is correctly set | ✅ PASS |

Project isolation is implemented at the SQL layer (`AND r.project_id = ?`) and additionally enforced by a post-filter in `RetrievalService` as a safety guarantee.

---

## 11. Provenance Results

**PASS — Full provenance chain verified.**

The following fields survive `ingest → storage → search → retrieval → context assembly`:

| Field | Survives? |
|---|---|
| `project_id` | ✅ |
| `record_id` | ✅ |
| `chunk_id` | ✅ |
| `source_path` | ✅ |
| `source_type` | ✅ |
| `session_id` (where set) | ✅ |
| `start_line` | ✅ |
| `end_line` | ✅ |
| `score` | ✅ |
| `retrieval_metadata` | ✅ (new in Stage 3.5) |

`ContextItem.source` contains `"source_path:start_line-end_line"` for line-level provenance.  
`ContextPacket.assembled_prompt_text` includes source paths.  
`ContextPacket.retrieval_metadata` records embedding model, scoring strategy, min_score, top_k, and filter params.

---

## 12. Single Scoring Layer Proof

**PASS — One authoritative scoring layer confirmed.**

| Layer | Role | Scores? |
|---|---|---|
| `SQLiteMemoryStorage.search_chunks()` | Computes hybrid score, returns `MemorySearchResult.score` | ✅ YES — single scoring point |
| `RetrievalService.search_memory()` | Post-filters, passes `.score` through unchanged | ❌ No re-scoring |
| `ranking.rank_and_deduplicate_results()` | Uses `.score` as-is for filtering/sorting/dedup | ❌ No re-scoring |
| `ContextAssembler.assemble()` | Uses `relevance_score` for display only | ❌ No re-scoring |

`ranking.py` does not import `_cosine_similarity` or `_keyword_overlap_score` (verified by test).

---

## 13. Remaining Known Limitations

| # | Limitation | Severity | Mitigation |
|---|---|---|---|
| 1 | Local embedding has no semantic understanding | Medium | 0.3 keyword weight partially compensates; swap provider for production |
| 2 | No SQL LIMIT in `search_chunks` — scans all rows | Low (dev scale) | Acceptable for MVP; add ANN index at production scale |
| 3 | Token estimator is `ceil(len/4)` approximation | Low | Documented; acceptable for prompt budgeting |
| 4 | Rules engine not implemented | — | Planned Stage 4 |
| 5 | No `importance`/`authority`/`recency` metadata fields | — | See memory authority analysis below |
| 6 | `SQLiteMemoryStorage` opens a new connection per operation | Low | Acceptable for single-threaded local use |

---

## 14. Memory Authority Analysis (Phase 16)

The current `MemoryRecord.metadata` is a freeform `Dict[str, Any]`. It can hold any future fields without schema changes.

However, the system **currently cannot distinguish** between:
- Casual discussion: `"Maybe we should use MongoDB?"`
- Authoritative decision: `"We selected PostgreSQL. This is final."`

**Future metadata fields needed (do NOT implement now):**

| Field | Purpose |
|---|---|
| `importance` | float 0.0–1.0 — signals how authoritative/critical this memory is |
| `authority` | enum: `casual`, `proposed`, `decided`, `superseded` |
| `recency_weight` | time-decay factor for older memories |
| `supersedes` | list of record_ids this decision replaces |
| `status` | `draft`, `accepted`, `rejected`, `deprecated` |

These fields would allow the retrieval reranker to boost `decided` memories over `casual` ones and suppress `superseded` records. The `MemoryRecord.metadata` dict already supports storing them without a schema migration. A future "memory authority scorer" can read them during reranking.

**No changes made.** The observation is documented for Stage 4 or 5.

---

## 15. Recommended Future Improvements

1. **Neural embedding provider** — Implement `OllamaEmbeddingProvider` or `SentenceTransformersEmbeddingProvider` using the existing `EmbeddingProvider` interface. No pipeline code changes needed. Target: Stage 5.

2. **ANN indexing** — For databases with >10K chunks, add approximate nearest-neighbor pre-filtering (e.g. FAISS or SQLite-vec) before Python-side scoring. Target: Stage 5.

3. **Memory authority scoring** — Add `importance` and `authority` fields to `MemoryRecord.metadata` and apply a reranking boost for `decided` vs `casual` memories. Target: Stage 4.

4. **Recency decay** — Weight recent memories higher when `source_type="conversation"`. Target: Stage 4.

5. **Chunking improvements** — For code files, use AST-level boundaries instead of regex patterns. The current regex approach misses decorators nested inside classes. Target: Stage 4 or 5.

6. **Evaluation dataset expansion** — Add 25 more queries covering code-level retrieval (function signatures, import names, error patterns). Target: ongoing.

---

## 16. Subsystem Verification Assessment (Hackathon MVP)

**Stage Final Verdict: VERIFIED for Hackathon MVP**

| Criterion | Status |
|---|---|
| No double scoring | ✅ PASS |
| Candidate pool appropriate | ✅ PASS |
| Project isolation airtight | ✅ PASS |
| Provenance preserved end-to-end | ✅ PASS |
| Context budget enforced | ✅ PASS |
| Evaluation from actual data | ✅ PASS |
| Failures visible and documented | ✅ PASS |
| No false embedding quality claims | ✅ PASS |
| All 167 Member 2 tests pass | ✅ PASS |
| Recall@5 ≥ 80% on eval dataset | ✅ 88% |
| MRR ≥ 0.7 | ✅ 0.817 |

**Conditional:** The local embedding baseline has documented limitations. For any demo query that uses vocabulary radically different from source documents (e.g. `"persistence technology"` when the doc says `"database"`), retrieval will rely on the 0.3 keyword weight. Design demo queries to have moderate vocabulary overlap, or swap in a neural embedding provider before the demo.

---

## 17. Adversarial Diagnostic Evaluation (Stage Final)

Evaluated via [`scripts/evaluate_retrieval_adversarial.py`](file:///A:/CLIVERSE/scripts/evaluate_retrieval_adversarial.py) against [`tests/fixtures/retrieval_eval_adversarial.json`](file:///A:/CLIVERSE/tests/fixtures/retrieval_eval_adversarial.json):

- **Total Adversarial Queries:** 20 (16 Positive Queries, 4 Negative Queries)
- **Overall Succeeded (@5):** 15 / 20 queries (75.0%)
- **Overall Failed (@5):** 5 / 20 queries (25.0%)

### 17.1 Positive Query Metrics (16 Queries — Unpolluted by Negatives)
- **Recall@1:** 58.3%
- **Recall@3:** 66.7%
- **Recall@5:** 69.8%
- **Precision@1:** 68.8%
- **Precision@3:** 41.7%
- **Precision@5:** 33.8%
- **MRR (Mean Reciprocal Rank):** 0.731
- **Positive Succeeded (@5):** 13 / 16 queries
- **Positive Failed (@5):** 3 / 16 queries (attributed to `relevant candidate ranked below top-K`)

### 17.2 Negative / Out-of-Domain Query Behavior (4 Queries)
- **True Negatives (Clean Rejection):** 2 / 4 queries
- **False Positives:** 2 / 4 queries
- **True-Negative Rejection Rate:** 50.0%
- **False-Positive Rate:** 50.0%
- **Average Candidates Retrieved Above Threshold:** 2.50 candidates

### 17.3 Causal Failure Attribution Breakdown (5 Total Failures)
1. `relevant candidate ranked below top-K`: 3 queries (synonym/terminology substitutions where character n-gram hash baseline lacked cross-lexical projection).
2. `false positive candidates retrieved`: 2 queries (irrelevant negative queries whose character n-gram noise exceeded the min_score threshold of 0.10).

---

## 18. Formal Metric Definitions & Evaluation Formulas

The evaluation harness implements standard Information Retrieval (IR) metrics under deterministic definitions:

### 18.1 Relevant Chunk Definition
A retrieved candidate chunk is defined as **relevant** if and only if its `source_path` matches one of the canonical file paths listed in the query's ground-truth `expected_sources`.

### 18.2 Positive vs. Negative Query Separation
Negative queries have $\text{expected\_sources} = \emptyset$. They are evaluated strictly under rejection metrics and are **never mixed into positive Recall or MRR calculations**, avoiding artificial metric inflation.

### 18.3 Recall@K Formula & Denominator (Positive Queries)
For positive queries with $M = |\text{expected\_sources}| > 0$:
$$\text{Recall@K} = \frac{|\{s \in \text{expected\_sources} \mid s \in \text{top\_k\_paths}\}|}{M}$$
- The denominator is always the total number of expected relevant sources ($M$).
- Found sources are deduplicated across chunks.

### 18.4 Precision@K Formula & Denominator (Positive Queries)
For positive queries:
$$\text{Precision@K} = \frac{\sum_{r \in \text{results}[:K]} \mathbb{I}(r.\text{source\_path} \in \text{expected\_sources})}{\min(K, |\text{results}[:K]|)}$$
- The denominator is the actual number of candidates evaluated in top-K ($\le K$).

### 18.5 Mean Reciprocal Rank (MRR) (Positive Queries)
For positive query $q_i$, let $\text{rank}_i$ be the 1-based position of the first relevant chunk in the ordered results:
$$\text{RR}_i = \begin{cases} \frac{1}{\text{rank}_i} & \text{if relevant chunk retrieved} \\ 0.0 & \text{otherwise} \end{cases}$$
$$\text{MRR} = \frac{1}{N_{\text{pos}}} \sum_{i=1}^{N_{\text{pos}}} \text{RR}_i$$

### 18.6 Negative Query Rejection Metrics
$$\text{Rejection Rate} = \frac{\text{True Negatives}}{N_{\text{neg}}}$$
$$\text{False-Positive Rate} = \frac{\text{False Positives}}{N_{\text{neg}}}$$

---

## 19. Storage Scaling Characterization: SQLite Table Scan Diagnosis

Measured via [`scripts/characterize_sqlite_scaling.py`](file:///A:/CLIVERSE/scripts/characterize_sqlite_scaling.py):

| Corpus Size (Chunks) | Avg Search Latency | Throughput (QPS) | Architectural Classification |
|---|---|---|---|
| **100** | 3.14 ms | 318.8 | Hackathon MVP Ready |
| **500** | 12.23 ms | 81.8 | Hackathon MVP Ready |
| **1,000** | 23.81 ms | 42.0 | Hackathon MVP Upper Bound |
| **2,500** | 58.01 ms | 17.2 | Latency degradation noticeable |
| **5,000** | 121.29 ms | 8.2 | Unacceptable for live keystroke search |

**Diagnostic Assessment:**
- Search execution performs a linear table scan $\mathcal{O}(N)$ in SQLite followed by in-memory pure-Python vector deserialization and cosine similarity loops.
- SQLite with Python-side vector scoring is suitable for the local hackathon MVP corpus (<1,000 chunks); ANN/vector-database scaling (sqlite-vec, FAISS, pgvector) is future work.

---

## 20. Code Chunking & Token Budgeting Limitations

1. **Heuristic Structure-Aware Chunking:** Text chunking uses regular expressions for markdown headers and function definitions (`def `, `class `, `function `). It is heuristic structure-aware chunking, not a universal language parser. Highly nested code, multi-line decorators, and complex TypeScript interfaces are chunked without data loss, but AST-level parse preservation is deferred to future work.
2. **Approximate Token Budgeting:** Token counting uses an approximate character-based planning budget ($\max(1, \lceil \text{length}/4 \rceil)$), not tokenizer-exact accounting. BPE tokenizers (e.g. `tiktoken`) are deferred to post-hackathon roadmap.

