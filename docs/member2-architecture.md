# Member 2 Architecture Specification: RAG & Rules Intelligence

**Subsystem:** CLIVERSE — Member 2 (Memory / RAG + Rules Intelligence)  
**Status:** All Stages (Stage 1 — Foundation, Stage 2 — Ingestion + Embedding Foundation, Stage 3 — Retrieval + Context Assembly, Stage 3.5 — RAG Validation + Hardening, Stage 4 — Rules Intelligence, Stage 5 — Unified Laya Intelligence Contract, Stage 5.1 — Integration Safety Hardening, Stage 6 — Real Cross-Member Integration, Final — Hardening + Handoff) Complete — 145 Tests Green (Final Handoff Ready)  
**Authors:** Member 2 Engineering Lead  

---

## 1. System Vision & Purpose

Member 2 is the **Cognitive Backbone** of CLIVERSE. While other members handle execution (Member 1), UI (Member 3), and security/trust gates (Member 4), Member 2 guarantees that:

1. **AI CLIs do not suffer from amnesia:** Past discussions, user architectural decisions, project conventions, and session summaries are preserved across sessions.
2. **AI CLIs operate under strict engineering guardrails:** Rules defined at the Global, Project, CLI, and Task levels are prioritized, resolved deterministically, and injected directly into prompt planning before execution occurs.
3. **Every retrieved fact has full provenance:** When context is provided to Laya, every snippet knows exactly what file, line number, or session ID it originated from.

---

## 2. Team Architecture & Ownership Boundary

```
                       ┌─────────────────────────┐
                       │   MEMBER 3: Dashboard   │
                       │   (React / Next / WS)   │
                       └────────────┬────────────┘
                                    │ Reads memory / Edits rules via REST
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        MEMBER 1: Core & Laya                           │
│  • Task Planning & Prompt Assembly       • CLI Adapter Execution       │
│  • Git & Undo Engine                     • Session Metadata            │
└──────────────┬──────────────────────────────────────────┬──────────────┘
               │ Calls Public Interfaces                  │ Calls TrustGate
               ▼                                          ▼
┌────────────────────────────────────────┐ ┌─────────────────────────────┐
│       MEMBER 2: Memory & Rules         │ │ MEMBER 4: Security & Trust  │
│  • Persistent RAG & Knowledge Store    │ │  • Identity & Permissions   │
│  • Hierarchical Rules Engine           │ │  • Sandbox & Secrets        │
│  • Context Assembly & Vector Search    │ │  • Regulatory Governance    │
│  • Explainable Rule Conflicts          │ │  • Audit Ledger             │
└────────────────────────────────────────┘ └─────────────────────────────┘
```

### Strict Ownership Boundaries:
* **Member 1 owns:** CLI lifecycle, git commits, diff detection, undo, session directories, and Laya intent processing.
* **Member 2 owns:** Ingestion, normalization, chunking, deduplication, embedding, vector search, context assembly, rule parsing, rule prioritization, rule conflict resolution, and memory persistence.
* **Member 3 owns:** Web Dashboard, frontend UI, user settings, visual inspection of memories and rules.
* **Member 4 owns:** Agent identity tokens, execution permission checks, command sandboxing, secrets vault, regulatory compliance checking, and cryptographic audit logging.

---

## 3. Member 2 Internal Module Structure

```
CLIVERSE/
├── memory/
│   ├── __init__.py
│   ├── models.py            # Pydantic schemas (MemoryRecord, MemoryChunk, ContextPacket)
│   ├── ingestion/           # File, codebase, doc, and session parsing
│   │   ├── __init__.py
│   │   ├── normalizer.py    # Whitespace, line-ending, and syntax normalization
│   │   ├── chunker.py       # Header-aware markdown & line/AST code chunkers
│   │   └── deduplicator.py  # Content-hash (SHA-256) deduplication
│   ├── embeddings/          # Embedding abstraction & implementations
│   │   ├── __init__.py
│   │   ├── base.py          # EmbeddingProvider protocol/abstract base class
│   │   └── local_engine.py  # Local zero-dependency semantic vectorizer
│   ├── storage/             # Persistence abstraction & SQLite store
│   │   ├── __init__.py
│   │   ├── base.py          # MemoryStorage abstract base class
│   │   └── sqlite_store.py  # SQLite implementation (.envcore/memory/cliverse_memory.db)
│   ├── retrieval/           # Vector & text search engine
│   │   ├── __init__.py
│   │   ├── search.py        # Cosine similarity + BM25 hybrid ranker
│   │   ├── ranking.py       # Deterministic deduplication and threshold filtering
│   │   └── assembler.py     # ContextPacket assembler with provenance tags
│   └── manager.py           # Unified MemoryManager facade
│
├── rules/
│   ├── __init__.py          # Public exports
│   ├── models.py            # Pydantic schemas (Rule, RuleScope, RuleEffect, RuleResolution)
│   ├── parser.py            # RuleParser (YAML/JSON loading, normalization, duplicate detection)
│   ├── validator.py         # RuleValidator (syntax, regex, condition validation)
│   ├── applicability.py     # RuleApplicabilityChecker (scope, project, CLI, condition matching)
│   ├── storage.py           # RuleStore (version-controlled storage in .cliverse/rules & .envcore/rules)
│   ├── resolver.py          # RuleResolver (conflict detection, mandatory guardrails, explanation trace)
│   └── engine.py            # RulesEngine (high-level facade integrating storage, applicability, resolver)
│
├── rag_rules_service.py     # Public facade consumed directly by Member 1 (Laya)
├── memory_rules_api.py      # FastAPI APIRouter consumed by Member 3 (Dashboard)
└── tests/
    ├── test_memory_storage_models.py          # Storage & models (5 tests)
    ├── test_ingestion_embeddings.py           # Ingestion & embeddings (12 tests)
    ├── test_retrieval_context.py              # Retrieval & context (12 tests)
    ├── test_rag_validation.py                 # RAG validation & edge cases (43 tests)
    ├── test_rules_engine.py                   # Rules intelligence & resolver (29 tests)
    ├── test_laya_intelligence_integration.py  # Facade integration (11 tests)
    ├── test_stage51_hardening.py              # Safety & contract hardening (19 tests)
    └── test_final_cross_member_integration.py # Real cross-member integration (14 tests)
```

---

## 4. Memory Pipeline Architecture

```
Files / Sessions / Docs
       │
       ▼
 ┌───────────┐
 │ Ingestion │ ── Read files, session markdown, or raw user notes
 └─────┬─────┘
       ▼
 ┌──────────────┐
 │ Normalization│ ── Normalize line endings, strip junk, detect content type
 └─────┬────────┘
       ▼
 ┌───────────┐
 │  Chunking │ ── Header-aware for markdown (H1/H2), token sliding window for code
 └─────┬─────┘
       ▼
 ┌───────────────┐
 │ Deduplication │ ── SHA-256 hash checking against existing chunks
 └─────┬─────────┘
       ▼
 ┌────────────┐
 │ Embeddings │ ── Vector representation generation (dim=64/128/1536)
 └─────┬──────┘
       ▼
 ┌───────────┐
 │  Storage  │ ── SQLite persistent tables: records, chunks, embeddings
 └─────┬─────┘
       ▼
 ┌───────────┐
 │ Retrieval │ ── Hybrid cosine similarity + BM25 keyword reranker
 └─────┬─────┘
       ▼
 ┌──────────────────┐
 │ Context Assembly │ ── Construct formatted ContextPacket with explicit provenance
 └─────┬────────────┘
       ▼
  Member 1 Laya
```

---

## 5. Rules Intelligence Architecture & Semantics

### Rule Scopes & Weights

Rules are categorized into four hierarchical tiers:

$$\text{TASK (Weight 400)} \succ \text{CLI (Weight 300)} \succ \text{PROJECT (Weight 200)} \succ \text{GLOBAL (Weight 100)}$$

| Scope | Scope Weight | Description | Source / Storage |
|---|---|---|---|
| **GLOBAL** | 100 | Applies to all projects across the user's workstation. | `~/.cliverse/rules/` or `.envcore/rules/global/` |
| **PROJECT** | 200 | Project-specific architecture & coding standards. | `.cliverse/rules/` or `.envcore/rules/project/` |
| **CLI** | 300 | Specific to a designated CLI adapter (e.g. `aider`, `claude-cli`). | Configuration files mapped by CLI identifier |
| **TASK** | 400 | Ephemeral or task-specific instructions passed by the user. | Attached directly to invocation / Laya prompt |

### Rule Precedence & Conflict Resolution Algorithm

1. **Effective Priority Score:**
   $$\text{Score} = \text{Scope Weight} + \text{Rule Priority (0--99)}$$
2. **Conflict Definition:**
   Two rules conflict when they target the same subject/property (e.g., `tech_stack:orm`, `package_installation`, `file_modification`) with opposing effects (e.g., `ENFORCE PostgreSQL` vs `ENFORCE MySQL`, or `ALLOW` vs `DENY`).
3. **Resolution Rules:**
   * **Scope Specificity:** A rule in a higher scope overrides a lower scope rule (e.g. Task rule overrides Project rule).
   * **Mandatory Safety Override (Fail-Safe):** If a lower-scope rule has `is_mandatory=True` and `effect=DENY` (e.g., a Project-level rule: "Never modify production `.env` files"), a weaker Task-level rule **CANNOT** override it. The mandatory restriction wins.
   * **Deterministic Tie-Breaking:** If two conflicting rules share identical effective scores:
     1. More specific target pattern wins.
     2. `DENY` takes precedence over `ALLOW`.
     3. Older rule (earliest `created_at` timestamp) wins.
4. **Explainable Trace:** Every resolution outputs a `RuleResolution` containing:
   - `active_rules`: Set of winning rules to be injected into Laya.
   - `suppressed_rules`: Set of rules overridden with reasons.
   - `conflicts`: Explicit conflict pairs detected.
   - `trace`: Human-readable markdown explanation for developer inspection.

---

## 6. Public Data Contracts (Pydantic v2 Specifications)

### Memory Data Models

```python
class MemoryRecord(BaseModel):
    record_id: str                      # Unique UUID
    project_id: str                     # Associated project name/path
    session_id: Optional[str] = None    # Associated session ID if conversation
    source_type: str                    # "code" | "doc" | "conversation" | "decision"
    source_path: str                    # e.g., "docs/architecture.md" or "session-001"
    title: str                          # Short descriptive title
    content: str                        # Full content body
    tags: List[str] = []
    metadata: Dict[str, Any] = {}
    created_at: str
    updated_at: str

class MemoryChunk(BaseModel):
    chunk_id: str                       # UUID
    record_id: str                      # Foreign key to MemoryRecord
    chunk_index: int                    # Sequential chunk index
    content: str                        # Chunk text
    content_hash: str                   # SHA-256 for deduplication
    embedding: Optional[List[float]] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    metadata: Dict[str, Any] = {}

class MemorySearchResult(BaseModel):
    chunk_id: str
    record_id: str
    source_path: str
    source_type: str
    content: str
    score: float                        # Similarity score (0.0 to 1.0)
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    metadata: Dict[str, Any] = {}

class ContextItem(BaseModel):
    source: str                         # Provenance: "docs/arch.md:12-45"
    source_type: str
    relevance_score: float
    snippet: str

class ContextPacket(BaseModel):
    task: str
    items: List[ContextItem]
    assembled_prompt_text: str          # Markdown block ready for Laya's prompt
    token_estimate: int
    provenance_summary: List[str]       # List of distinct sources cited
```

### Rules Data Models

```python
class RuleScope(str, Enum):
    GLOBAL = "GLOBAL"
    PROJECT = "PROJECT"
    CLI = "CLI"
    TASK = "TASK"

class RuleEffect(str, Enum):
    ALLOW   = "ALLOW"    # Explicitly permits. No restriction.
    WARN    = "WARN"     # Advisory only; action may continue.
    ENFORCE = "ENFORCE"  # Synonym for REQUIRE (backward compat). Maps to RuleDecision.REQUIRE.
    REQUIRE = "REQUIRE"  # Positive prerequisite constraint ("Tests must pass first").
    ASK     = "ASK"      # Human confirmation required before continuing.
    DENY    = "DENY"     # Hard prohibition; action is blocked.

# NOTE: ENFORCE and REQUIRE are equivalent and both map to RuleDecision.REQUIRE.
# REQUIRE is not a form of DENY — it represents a precondition, not a prohibition.

class Rule(BaseModel):
    rule_id: str                        # Unique slug (e.g., "proj-use-typescript")
    name: str                           # Readable title
    scope: RuleScope                    # GLOBAL | PROJECT | CLI | TASK
    description: str                    # Full instruction text
    target: str                         # Category/domain (e.g., "language", "database", "git")
    effect: RuleEffect                  # ENFORCE | DENY | WARN | ALLOW
    priority: int = 50                  # Local priority (0 to 99)
    is_mandatory: bool = False          # If True, cannot be overridden by higher scopes
    cli_filter: Optional[str] = None    # Apply only to specific CLI if set
    project_id: Optional[str] = None    # Project isolation key
    enabled: bool = True
    created_at: str
    metadata: Dict[str, Any] = {}

class RuleConflict(BaseModel):
    winning_rule_id: str
    suppressed_rule_id: str
    reason: str

class RuleResolution(BaseModel):
    task: str
    applicable_rules: List[Rule]        # Final set of active rules
    conflicts: List[RuleConflict]       # Detected conflicts
    explanation_trace: str              # Step-by-step resolution reasoning
    constraints_prompt_text: str        # Formatted constraints block for Laya
```

---

## 7. Public API Contracts (For Member 1 & Member 3)

### Interface for Member 1 (Laya Facade: `rag_rules_service.py`)

Member 1 consumes Member 2 exclusively through this interface:

```python
# Canonical import (from public facade only)
from rag_rules_service import (
    LayaIntelligenceService,
    LayaIntelligenceContext,
    SubsystemStatus,  # OK_WITH_RESULTS | OK_EMPTY | ERROR
    RuleDecision,     # ALLOW | WARN | REQUIRE | ASK | DENY | UNKNOWN
    TaskLike,         # Protocol: .task: str + .as_dict() -> dict
)

class LayaIntelligenceService:
    def build_intelligence_context(
        self,
        task: Union[str, TaskLike, Any],  # str, StructuredTask, or TaskLike-compatible
        project_id: Optional[str] = None,
        cli_name: Optional[str] = None,
        task_rules: Optional[List[Rule]] = None,
        top_k: int = 5,
        min_score: float = 0.35,
        context_budget_tokens: int = 2000,
        task_metadata: Optional[Dict[str, Any]] = None,
    ) -> LayaIntelligenceContext:
        """
        Primary Stage 5 Unified Integration API. Orchestrates memory retrieval,
        rule applicability, deterministic conflict resolution, and prompt formatting.

        Guarantees (Stage 5.1):
          - memory_status: OK_WITH_RESULTS | OK_EMPTY | ERROR (never conflated)
          - rules_status: OK_WITH_RESULTS | OK_EMPTY | ERROR (never conflated)
          - rule_decision: UNKNOWN on rules engine failure (never silently ALLOW)
          - memory_status=ERROR prompt text ≠ "No relevant project memory found"

        rule_decision represents developer/project rule resolution only.
        It is NOT the final security or execution authorization (Member 4 TrustGate).
        """
        ...

    def retrieve_context(
        self,
        task: str,
        project_id: Optional[str] = None,
        top_k: int = 5,
        min_score: float = 0.35,
    ) -> ContextPacket:
        """
        Retrieves top relevant project knowledge & conversation history,
        returning an assembled ContextPacket with explicit source provenance.
        """
        ...

    def get_applicable_rules(
        self,
        task: str,
        cli_name: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> List[Rule]:
        """
        Returns all applicable, active rules relevant to the task and CLI.
        """
        ...

    def resolve_rules(
        self,
        task: str,
        cli_name: Optional[str] = None,
        project_id: Optional[str] = None,
        task_rules: Optional[List[Rule]] = None,
    ) -> RuleResolution:
        """
        Resolves conflicts across Global, Project, CLI, and Task rules.
        Returns active rules and a human-readable explanation trace.
        """
        ...

    def store_memory(
        self,
        content: str,
        source_type: str,
        source_path: str,
        title: Optional[str] = None,
        project_id: str = "default",
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryRecord:
        """
        Ingests, normalizes, chunks, embeds, and stores a new piece of memory.
        """
        ...

    def search_memory(
        self,
        query: str,
        project_id: Optional[str] = None,
        top_k: int = 5,
    ) -> List[MemorySearchResult]:
        """
        Performs raw hybrid semantic search over all memory chunks.
        """
        ...

    def delete_memory(self, record_id: str) -> bool:
        """
        Deletes a memory record and its corresponding chunks/embeddings.
        """
        ...
```

### REST Endpoints for Member 3 (Dashboard Router: `memory_rules_api.py`)

Mounted at `/api/v1/memory` and `/api/v1/rules`:

* **Memory:**
  - `POST /api/v1/memory/store` — Store new memory item
  - `POST /api/v1/memory/search` — Vector/keyword search
  - `GET  /api/v1/memory/records` — List indexed records with provenance
  - `DELETE /api/v1/memory/records/{record_id}` — Remove a memory record
* **Rules:**
  - `GET  /api/v1/rules` — List all rules (filterable by scope)
  - `POST /api/v1/rules` — Create a new rule
  - `PUT  /api/v1/rules/{rule_id}` — Update existing rule
  - `DELETE /api/v1/rules/{rule_id}` — Delete a rule
  - `POST /api/v1/rules/resolve` — Test conflict resolution for a given task

---

## 8. Storage & Embedding Abstractions

### Storage Abstraction (`memory/storage/base.py`)
```python
class MemoryStorage(ABC):
    @abstractmethod
    def save_record(self, record: MemoryRecord, chunks: List[MemoryChunk]) -> None: ...
    @abstractmethod
    def get_record(self, record_id: str) -> Optional[MemoryRecord]: ...
    @abstractmethod
    def delete_record(self, record_id: str) -> bool: ...
    @abstractmethod
    def search_chunks(self, query_vector: List[float], query_text: str, top_k: int, project_id: Optional[str]) -> List[MemorySearchResult]: ...
    @abstractmethod
    def list_records(self, project_id: Optional[str] = None) -> List[MemoryRecord]: ...
```
* **MVP Implementation:** SQLite database at `.envcore/memory/cliverse_memory.db`.
* **Zero Infrastructure Overhead:** Requires no external database daemon, works out-of-the-box on Windows/Linux/macOS.
* **Migration Ready:** Upgrades to PostgreSQL + `pgvector` in the future require only a new implementation of `MemoryStorage`, leaving all higher layers unchanged.

### Embedding Abstraction (`memory/embeddings/base.py`)
```python
class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]: ...
    @abstractmethod
    def embed_query(self, text: str) -> List[float]: ...
    @property
    @abstractmethod
    def dimension(self) -> int: ...
    @property
    @abstractmethod
    def model_name(self) -> str: ...
```
* **MVP Default Engine:** `LocalSemanticEmbeddingProvider` (zero third-party dependencies, dense n-gram token vectorizer with cosine normalization, sub-millisecond execution).
* **Pluggable Extensions:** Ready for OpenAI (`text-embedding-3-small`), Gemini embeddings, or local Ollama embeddings without API changes.

---

## 9. Comprehensive Test Strategy

The test suite will be located at `tests/test_memory_rules.py` and compatible with both `pytest` and `run_tests.py` using standard temporary directories (`tempfile.mkdtemp`):

1. **Ingestion & Normalization:** Test stripping excess blank lines, handling UTF-8 characters, and header parsing.
2. **Chunking & Deduplication:** Verify sliding-window bounds, code preservation, and that duplicate content hashes are discarded.
3. **Embeddings & Search:** Test vector dimensionality, similarity ranking ordering, and score thresholds.
4. **Project Isolation:** Verify queries for Project A never leak chunks belonging to Project B.
5. **Provenance Verification:** Ensure every `ContextItem` accurately reports its source file, line numbers, and score.
6. **Rule Priority & Hierarchy:** Verify Task (400) > CLI (300) > Project (200) > Global (100).
7. **Rule Conflict Resolution:** Test opposing rules (`ALLOW` vs `DENY`), verify mandatory rule protection, and ensure the resolution trace correctly explains the winning decision.
8. **End-to-End Facade Integration:** Test `retrieve_context()`, `resolve_rules()`, `store_memory()`, and `delete_memory()`.

---

## 10. Risk Analysis & Open Decisions

| Risk / Consideration | Severity | Mitigation Strategy |
|---|---|---|
| **Large Codebase Indexing Overhead** | Medium | Chunk incrementally; store content hashes in SQLite to skip re-indexing unmodified files. |
| **Conflicting Rules Confusion** | Low | Generate a human-readable explanation trace for every resolution, displayed in the dashboard and Laya logs. |
| **Cross-Platform Path Incompatibilities** | Low | Use `pathlib.Path` consistently across all storage and indexing code (ensures Windows compatibility). |
| **Heavy Dependency Breakage** | Medium | Maintain zero heavy binary dependencies for the default engine so the test runner executes in under 1 second. |

---

## 11. Implementation Roadmap (Post-Stage 1)

* **Step 1:** Data Models & SQLite Schema (`memory/models.py`, `rules/models.py`, `memory/storage/sqlite_store.py`).
* **Step 2:** Ingestion, Chunker & Local Embedding Engine (`memory/ingestion/`, `memory/embeddings/`, `memory/retrieval/`).
* **Step 3:** Rules Engine, Parser, Priority Matrix & Resolver (`rules/`).
* **Step 4:** Laya Facade (`rag_rules_service.py`) & Dashboard REST Router (`memory_rules_api.py`).
* **Step 5:** Test Suite (`tests/test_memory_rules.py`), runner integration (`run_tests.py`), and documentation update.
