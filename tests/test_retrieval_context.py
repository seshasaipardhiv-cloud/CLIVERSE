"""
Comprehensive Unit & Integration Test Suite for Stage 3: Retrieval Engine + Context Assembly
Compatible with pytest and unittest standard library.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from memory.embeddings.local_engine import LocalBaselineEmbeddingProvider
from memory.ingestion.pipeline import IngestionPipeline
from memory.models import MemorySearchResult
from memory.retrieval.assembler import ContextAssembler, estimate_tokens
from memory.retrieval.ranking import rank_and_deduplicate_results
from memory.retrieval.search import RetrievalService
from memory.storage.sqlite_store import SQLiteMemoryStorage


class TestStage3RetrievalAndContext(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cliverse_stage3_test_")
        self.db_path = Path(self.temp_dir) / "test_stage3.db"
        self.storage = SQLiteMemoryStorage(db_path=str(self.db_path))
        self.embedding_provider = LocalBaselineEmbeddingProvider(dimension=64)
        self.ingestion = IngestionPipeline(
            storage=self.storage,
            embedding_provider=self.embedding_provider,
        )
        self.retrieval = RetrievalService(
            storage=self.storage,
            embedding_provider=self.embedding_provider,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ── 1. BASIC RETRIEVAL & RELEVANCE RANKING ───────────────────────────────

    def test_basic_retrieval_ranks_relevant_content_first(self):
        self.ingestion.ingest(
            content="Project uses PostgreSQL for relational data storage.",
            project_id="proj-db",
            source_type="decision",
            source_path="decisions/database.md",
        )
        self.ingestion.ingest(
            content="Authentication uses JWT tokens signed with RS256.",
            project_id="proj-db",
            source_type="decision",
            source_path="decisions/auth.md",
        )
        self.ingestion.ingest(
            content="Frontend uses React with Tailwind CSS styling.",
            project_id="proj-db",
            source_type="doc",
            source_path="docs/frontend.md",
        )

        results = self.retrieval.search_memory(
            query="database architecture and storage",
            project_id="proj-db",
            top_k=3,
            min_score=0.1,
        )

        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0].source_path, "decisions/database.md")
        self.assertIn("PostgreSQL", results[0].content)

    # ── 2. PROJECT ISOLATION ─────────────────────────────────────────────────

    def test_project_isolation_strict_boundary(self):
        self.ingestion.ingest(
            content="Database architecture is built on PostgreSQL.",
            project_id="project-A",
            source_type="doc",
            source_path="specs/db.md",
        )
        self.ingestion.ingest(
            content="Database architecture is built on MongoDB collections.",
            project_id="project-B",
            source_type="doc",
            source_path="specs/db.md",
        )

        # Query Project A
        results_a = self.retrieval.search_memory(
            query="database architecture",
            project_id="project-A",
            min_score=0.1,
        )
        self.assertTrue(len(results_a) > 0)
        for r in results_a:
            self.assertEqual(r.project_id, "project-A")
            self.assertNotIn("MongoDB", r.content)

        # Query Project B
        results_b = self.retrieval.search_memory(
            query="database architecture",
            project_id="project-B",
            min_score=0.1,
        )
        self.assertTrue(len(results_b) > 0)
        for r in results_b:
            self.assertEqual(r.project_id, "project-B")
            self.assertNotIn("PostgreSQL", r.content)

    # ── 3. SCORE ORDERING, MIN_SCORE & TOP_K ─────────────────────────────────

    def test_score_descending_order(self):
        self.ingestion.ingest(
            content="High match keyword keyword keyword token.",
            project_id="proj-scores",
            source_type="doc",
            source_path="doc1.md",
        )
        self.ingestion.ingest(
            content="Medium match keyword once.",
            project_id="proj-scores",
            source_type="doc",
            source_path="doc2.md",
        )
        self.ingestion.ingest(
            content="Unrelated text about completely different topics.",
            project_id="proj-scores",
            source_type="doc",
            source_path="doc3.md",
        )

        results = self.retrieval.search_memory(
            query="keyword token",
            project_id="proj-scores",
            top_k=5,
            min_score=0.0,
        )
        self.assertTrue(len(results) >= 2)
        for i in range(len(results) - 1):
            self.assertGreaterEqual(results[i].score, results[i + 1].score)

    def test_min_score_filter(self):
        self.ingestion.ingest(
            content="Some random peripheral notes.",
            project_id="proj-filter",
            source_type="doc",
            source_path="notes.md",
        )

        # High min_score filters out weakly matching results
        strict_results = self.retrieval.search_memory(
            query="cryptographic blockchain validation",
            project_id="proj-filter",
            min_score=0.95,
        )
        self.assertEqual(len(strict_results), 0)

    def test_top_k_limit(self):
        for i in range(10):
            self.ingestion.ingest(
                content=f"Item number {i} with common identifier.",
                project_id="proj-topk",
                source_type="doc",
                source_path=f"item_{i}.md",
            )

        results = self.retrieval.search_memory(
            query="common identifier",
            project_id="proj-topk",
            top_k=3,
            min_score=0.1,
        )
        self.assertLessEqual(len(results), 3)

    # ── 4. METADATA FILTERING ────────────────────────────────────────────────

    def test_metadata_filters_source_type_and_session(self):
        self.ingestion.ingest(
            content="Code definition for auth service.",
            project_id="proj-meta",
            source_type="code",
            source_path="src/auth.py",
        )
        self.ingestion.ingest(
            content="Documentation guide for auth service.",
            project_id="proj-meta",
            source_type="doc",
            source_path="docs/auth.md",
        )
        self.ingestion.ingest(
            content="Session decision for auth service.",
            project_id="proj-meta",
            session_id="session-101",
            source_type="decision",
            source_path="sessions/decisions.md",
        )

        # Filter by source_type='code'
        code_results = self.retrieval.search_memory(
            query="auth service",
            project_id="proj-meta",
            source_types=["code"],
            min_score=0.1,
        )
        self.assertEqual(len(code_results), 1)
        self.assertEqual(code_results[0].source_type, "code")

        # Filter by session_id='session-101'
        session_results = self.retrieval.search_memory(
            query="auth service",
            project_id="proj-meta",
            session_id="session-101",
            min_score=0.1,
        )
        self.assertEqual(len(session_results), 1)
        self.assertEqual(session_results[0].session_id, "session-101")

    # ── 5. PROVENANCE & LINE RANGE PRESERVATION ──────────────────────────────

    def test_provenance_and_line_numbers_preserved(self):
        doc = (
            "# Section 1\n"
            "First section content.\n"
            "# Section 2\n"
            "Second section with database instructions.\n"
        )
        self.ingestion.ingest(
            content=doc,
            project_id="proj-line",
            source_type="doc",
            source_path="docs/sections.md",
        )

        packet = self.retrieval.retrieve_context(
            task="database instructions",
            project_id="proj-line",
            min_score=0.1,
        )

        self.assertTrue(len(packet.items) > 0)
        item = packet.items[0]
        self.assertTrue(item.source.startswith("docs/sections.md:"))
        self.assertEqual(item.source_type, "doc")
        self.assertIn("docs/sections.md", packet.assembled_prompt_text)

    # ── 6. DEDUPLICATION & OVERLAP REMOVAL ────────────────────────────────────

    def test_ranking_deduplication_removes_exact_duplicates_and_overlaps(self):
        c1 = MemorySearchResult(
            chunk_id="c1",
            record_id="rec-1",
            source_path="file.py",
            source_type="code",
            content="Exact duplicate content",
            score=0.9,
            start_line=1,
            end_line=10,
        )
        c2 = MemorySearchResult(
            chunk_id="c2",
            record_id="rec-1",
            source_path="file.py",
            source_type="code",
            content="Exact duplicate content",
            score=0.85,
            start_line=1,
            end_line=10,
        )
        c3 = MemorySearchResult(
            chunk_id="c3",
            record_id="rec-1",
            source_path="file.py",
            source_type="code",
            content="Distinct lines in same file",
            score=0.8,
            start_line=50,
            end_line=60,
        )

        deduped = rank_and_deduplicate_results([c1, c2, c3], min_score=0.5, top_k=5)
        # Should drop c2 (exact text dup) and keep c1 and c3
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0].chunk_id, "c1")
        self.assertEqual(deduped[1].chunk_id, "c3")

    # ── 7. CONTEXT BUDGET & TOKEN BOUNDING ───────────────────────────────────

    def test_context_budget_bounding(self):
        assembler = ContextAssembler(default_budget_tokens=100)
        content_item = "Word " * 15  # ~75 chars, ~20 tokens per item

        results = [
            MemorySearchResult(
                chunk_id=f"c_{i}",
                record_id=f"rec_{i}",
                source_path=f"file_{i}.txt",
                source_type="doc",
                content=f"Item {i}: {content_item}",
                score=0.9 - (i * 0.05),
                start_line=1,
                end_line=5,
            )
            for i in range(10)
        ]

        packet = assembler.assemble(task="Test budget", results=results, budget_tokens=100)
        self.assertLessEqual(packet.token_estimate, 110)
        self.assertTrue(len(packet.items) < len(results))

    # ── 8. EMPTY RESULT SAFETY & DETERMINISM ─────────────────────────────────

    def test_empty_search_returns_valid_packet_without_exception(self):
        packet = self.retrieval.retrieve_context(
            task="Nonexistent topics completely missing",
            project_id="empty-project",
            min_score=0.8,
        )
        self.assertEqual(len(packet.items), 0)
        self.assertEqual(packet.assembled_prompt_text, "")
        self.assertEqual(packet.token_estimate, 0)
        self.assertEqual(packet.provenance_summary, [])

    def test_retrieval_determinism(self):
        for i in range(3):
            self.ingestion.ingest(
                content=f"Fact {i}: Deterministic ordering test.",
                project_id="proj-det",
                source_type="doc",
                source_path=f"fact_{i}.md",
            )

        res1 = self.retrieval.search_memory("Deterministic test", project_id="proj-det", min_score=0.1)
        res2 = self.retrieval.search_memory("Deterministic test", project_id="proj-det", min_score=0.1)

        self.assertEqual([r.chunk_id for r in res1], [r.chunk_id for r in res2])
        self.assertEqual([r.score for r in res1], [r.score for r in res2])

    # ── 9. REALISTIC INTEGRATION SCENARIO (PHASE 13) ─────────────────────────

    def test_realistic_laya_integration_scenario(self):
        # Store realistic project knowledge
        self.ingestion.ingest(
            content="The backend uses FastAPI for API routing and asynchronous endpoints.",
            project_id="cliverse-app",
            source_type="doc",
            source_path="architecture/backend.md",
            title="Backend Architecture",
        )
        self.ingestion.ingest(
            content="The database is PostgreSQL with SQLAlchemy 2.0 ORM.",
            project_id="cliverse-app",
            source_type="decision",
            source_path="decisions/001-database.md",
            title="Database Decision",
        )
        self.ingestion.ingest(
            content="Authentication will use JWT tokens with bearer authorization header.",
            project_id="cliverse-app",
            source_type="decision",
            source_path="decisions/002-auth.md",
            title="Authentication Decision",
        )
        self.ingestion.ingest(
            content="Authentication endpoints are under /api/auth (login, register, refresh).",
            project_id="cliverse-app",
            source_type="doc",
            source_path="docs/api/auth.md",
            title="Auth API Docs",
        )

        packet = self.retrieval.retrieve_context(
            task="Add JWT authentication",
            project_id="cliverse-app",
            top_k=5,
            min_score=0.2,
        )

        # Verification of ContextPacket structure for Laya
        self.assertTrue(len(packet.items) >= 2)
        self.assertIn("JWT", packet.assembled_prompt_text)
        self.assertIn("[MEMORY 1]", packet.assembled_prompt_text)
        self.assertIn("Source:", packet.assembled_prompt_text)
        self.assertIn("Type:", packet.assembled_prompt_text)
        self.assertIn("Relevance:", packet.assembled_prompt_text)

        # Provenance summary verification
        self.assertTrue(len(packet.provenance_summary) >= 3)
        self.assertTrue(any("Sources:" in s for s in packet.provenance_summary))
        self.assertTrue(any("Score range:" in s for s in packet.provenance_summary))


if __name__ == "__main__":
    unittest.main()
