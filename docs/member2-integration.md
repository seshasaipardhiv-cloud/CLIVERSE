# Member 2 Integration Guide: Memory & Ingestion Interfaces

**Subsystem:** CLIVERSE — Member 2 (Memory / RAG + Rules Intelligence)  
**Status:** Stage 2 Complete (Ingestion, Normalization, Chunking, Deduplication, Embeddings)  
**Target Consumers:** Member 1 (Core + Laya Engine), Member 3 (Dashboard UI)  

---

## 1. Overview & Current Status

This guide specifies how external subsystems interact with Member 2's data ingestion and embedding services.

| Component | Status | Description |
|---|---|---|
| **Models & Storage** | ✅ **Implemented (Stage 1)** | `MemoryRecord`, `MemoryChunk`, `SQLiteMemoryStorage` |
| **Rules Models** | ✅ **Implemented (Stage 1)** | `Rule`, `RuleScope`, `RuleEffect`, `RuleConflict` |
| **Text Normalization** | ✅ **Implemented (Stage 2)** | Unicode NFC, CRLF $\rightarrow$ LF, trailing whitespace strip, structure preservation |
| **Deterministic Chunker** | ✅ **Implemented (Stage 2)** | Natural boundary detection (Markdown headers, code blocks, conversation turns) + line-level bounds |
| **SHA-256 Deduplication** | ✅ **Implemented (Stage 2)** | Incremental indexing: `NEW`, `MODIFIED`, and `UNMODIFIED` (skip) |
| **Embedding Abstraction** | ✅ **Implemented (Stage 2)** | `EmbeddingProvider` interface + `LocalBaselineEmbeddingProvider` (deterministic offline engine) |
| **Ingestion Pipeline** | ✅ **Implemented (Stage 2)** | `IngestionPipeline.ingest(...)` orchestration with strict project isolation and provenance |
| **Retrieval & RAG Search** | ⏳ *Planned (Stage 3)* | Cosine vector search, BM25 hybrid ranking, and `ContextPacket` assembly |
| **Rules Engine & Resolver** | ⏳ *Planned (Stage 4)* | Rule parser, priority weighting, and conflict resolution trace |
| **REST API Router** | ⏳ *Planned (Stage 5)* | FastAPI endpoints for Member 3 Dashboard |

---

## 2. Ingestion Pipeline Interface

### Python Service Entrypoint

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

### `IngestionResult` Specification

| Field | Type | Description |
|---|---|---|
| `record_id` | `str` | UUID of the created or updated `MemoryRecord`. |
| `project_id` | `str` | Project namespace. |
| `source_path` | `str` | Path/identifier of the ingested artifact. |
| `status` | `str` | `"NEW"`, `"MODIFIED"`, or `"UNMODIFIED"`. |
| `chunks_created` | `int` | Number of chunks generated and embedded. |
| `chunks_skipped` | `int` | Chunks skipped due to unchanged content hash. |
| `content_hash` | `str` | SHA-256 digest of the normalized content. |
| `embedding_model` | `str` | Identifier of the embedding model used. |
| `embedding_dimension` | `int` | Output vector dimension (default: 64). |
| `is_new` | `bool` | `True` if record was newly inserted. |
| `is_modified` | `bool` | `True` if existing record was updated. |

---

## 3. Subsystem Behaviors

### Normalization (`memory/ingestion/normalizer.py`)
* Normalizes unicode using Unicode NFC (`unicodedata.normalize`).
* Converts `\r\n` and `\r` to standard `\n`.
* Trims trailing spaces per line while strictly preserving indentation (spaces/tabs at line starts).
* Preserves Markdown headings and code blocks.
* Trims redundant trailing blank lines at document end to a single trailing `\n`.

### Chunking (`memory/ingestion/chunker.py`)
* Preserves natural semantic boundaries:
  - **Markdown:** Splits on `#`, `##`, `###` headings and paragraphs.
  - **Code:** Splits on `class`, `def`, `async def`, `function`, `export`, etc.
  - **Conversations:** Splits on speaker turn markers (`User:`, `Assistant:`, etc.).
* Enforces `chunk_size` (default: 500 chars) and `chunk_overlap` (default: 50 chars).
* Every chunk records exact `start_line` and `end_line` (1-indexed) in original normalized text.

### Deduplication (`memory/ingestion/deduplicator.py`)
* Computes `SHA-256(normalized_content)`.
* When the same file is re-ingested:
  - If content hash matches existing record $\rightarrow$ **`UNMODIFIED`**: skips chunking and embedding, returns `chunks_skipped = count`.
  - If content hash differs $\rightarrow$ **`MODIFIED`**: re-chunks and re-embeds, replacing previous chunks while keeping stable `record_id`.
  - If no prior record exists $\rightarrow$ **`NEW`**: creates record and chunks.

### Embedding Provider Abstraction (`memory/embeddings/base.py`)
```python
class EmbeddingProvider(ABC):
    def embed_documents(self, documents: List[str]) -> List[List[float]]: ...
    def embed_query(self, query: str) -> List[float]: ...
    @property
    def model_name(self) -> str: ...
    @property
    def dimension(self) -> int: ...
```
* **Default Engine:** `LocalBaselineEmbeddingProvider` (deterministic, zero external dependencies, offline n-gram token projections).
* **Future Replacement:** Production models (SentenceTransformers, Ollama, OpenAI, Gemini) plug directly into this interface without modifying the pipeline.

---

## 4. Multi-Tenant Project Isolation & Provenance

* **Project Isolation:** Storage and deduplication are strictly keyed by `(project_id, source_path)`. Two different projects can ingest files at `src/main.py` without collision.
* **Provenance Tracking:** Chunks store `start_line`, `end_line`, `source_path`, and `source_type` in both typed fields and metadata dicts, ready to be surfaced in Laya prompt packets and Dashboard UI cards.
