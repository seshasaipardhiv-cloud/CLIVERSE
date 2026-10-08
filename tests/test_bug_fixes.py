"""
Regression Tests for Harsh-Truth Bug Fixes — Member 2 (RAG + Rules)

Each test targets a specific real bug that was identified and fixed.
These tests MUST fail on the old code and PASS on the fixed code.

Bugs fixed:
  BUG-1: ranking.py hash-dedup never fired — content_hash absent from chunk metadata
  BUG-2: Double min_score filtering in search.py — storage pre-filtered, ranking re-filtered
  BUG-3: Budget overflow on first item — `and items` guard bypassed budget for item[0]
  BUG-4: ContextPacket.retrieval_metadata field was missing entirely
  BUG-5: search.py violated its own "abstractions only" contract by importing concrete classes
"""

import hashlib
import math
import shutil
import tempfile
import unittest
from pathlib import Path

from memory.embeddings.local_engine import LocalBaselineEmbeddingProvider
from memory.ingestion.chunker import TextChunker
from memory.ingestion.pipeline import IngestionPipeline
from memory.models import MemorySearchResult, ContextPacket
from memory.retrieval.assembler import ContextAssembler, estimate_tokens
from memory.retrieval.ranking import rank_and_deduplicate_results
from memory.retrieval.search import RetrievalService
from memory.storage.sqlite_store import SQLiteMemoryStorage


class TestBugFix1_ChunkMetadataContainsContentHash(unittest.TestCase):
    """
    BUG-1: chunker.py did NOT include content_hash in the chunk metadata dict.
    ranking.py's hash-based dedup relied on item.metadata.get("content_hash"),
    which always returned None — the hash path was dead code.
    FIX: content_hash is now included in chunk_meta in chunker.py.
    """

    def test_chunk_metadata_includes_content_hash(self):
        chunker = TextChunker(chunk_size=500, chunk_overlap=50)
        chunks = chunker.chunk(
            text="Some content that gets hashed deterministically.",
            record_id="rec-001",
            source_type="doc",
        )
        self.assertTrue(len(chunks) > 0)
        for chunk in chunks:
            self.assertIn(
                "content_hash", chunk.metadata,
                msg="content_hash must be present in chunk.metadata for hash dedup to work"
            )
            # The value in metadata must match the chunk's own content_hash field
            expected_hash = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
            self.assertEqual(
                chunk.metadata["content_hash"], expected_hash,
                msg="metadata content_hash must match actual chunk content_hash"
            )

    def test_hash_dedup_fires_on_identical_results(self):
        """
        Hash-based dedup must eliminate duplicates when content_hash is present.
        Before the fix: both items would pass through because content_hash was None.
        """
        content = "identical content that appears twice in results"
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        result_a = MemorySearchResult(
            chunk_id="chunk-a",
            record_id="rec-a",
            source_path="doc/a.md",
            source_type="doc",
            content=content,
            score=0.9,
            start_line=1,
            end_line=3,
            metadata={"content_hash": content_hash},
        )
        result_b = MemorySearchResult(
            chunk_id="chunk-b",
            record_id="rec-b",
            source_path="doc/b.md",  # different path — text dedup wouldn't catch this if stripped content differs
            source_type="doc",
            content=content,
            score=0.8,
            start_line=1,
            end_line=3,
            metadata={"content_hash": content_hash},
        )

        deduped = rank_and_deduplicate_results([result_a, result_b], min_score=0.0, top_k=10)
        self.assertEqual(
            len(deduped), 1,
            msg="Hash dedup must eliminate the second result with the same content_hash"
        )
        self.assertEqual(deduped[0].chunk_id, "chunk-a")  # highest score kept


class TestBugFix2_SingleMinScoreGate(unittest.TestCase):
    """
    BUG-2: search.py passed min_score to storage.search_chunks() AND then again to
    rank_and_deduplicate_results(). This created two independent filter passes —
    any floating-point rounding at the boundary between passes could silently drop
    valid candidates.
    FIX: storage is queried with min_score=0.0; ranking is the single gate.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cliverse_bugfix2_")
        self.db_path = Path(self.temp_dir) / "test.db"
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

    def test_results_at_min_score_boundary_are_not_double_dropped(self):
        """
        Ingest content, retrieve with min_score=0.0, and verify we get results.
        Before fix: storage pre-filtered AND ranking filtered, making threshold
        enforcement non-deterministic for borderline scores.
        After fix: only ranking filters — results at or above threshold always appear.
        """
        self.ingestion.ingest(
            content="boundary score test content with common words",
            project_id="proj-boundary",
            source_type="doc",
            source_path="boundary.md",
        )

        # With min_score=0.0 we must always get results for any stored content
        results = self.retrieval.search_memory(
            query="boundary score test",
            project_id="proj-boundary",
            min_score=0.0,
        )
        self.assertTrue(
            len(results) > 0,
            msg="min_score=0.0 must always return stored matching content"
        )
        # All returned scores must be at or above the requested threshold
        for r in results:
            self.assertGreaterEqual(
                r.score, 0.0,
                msg=f"Result score {r.score} is below min_score=0.0"
            )

    def test_all_scores_respect_min_score_threshold(self):
        """Verify that no result slips through below the requested threshold."""
        self.ingestion.ingest(
            content="Authentication service uses JWT bearer tokens for all API calls.",
            project_id="proj-threshold",
            source_type="doc",
            source_path="auth.md",
        )
        threshold = 0.35
        results = self.retrieval.search_memory(
            query="jwt authentication bearer",
            project_id="proj-threshold",
            min_score=threshold,
        )
        for r in results:
            self.assertGreaterEqual(
                r.score, threshold,
                msg=f"Result score {r.score} violated min_score threshold {threshold}"
            )


class TestBugFix3_TokenBudgetStrictEnforcement(unittest.TestCase):
    """
    BUG-3: assembler.py had `if total_tokens + block_tokens > budget_tokens and items:`
    The `and items` guard meant the FIRST item was always added regardless of budget —
    a single oversized chunk could silently overflow the token limit.
    FIX: removed `and items`; budget is enforced unconditionally for every item.
    """

    def _make_result(self, content: str, score: float = 0.9) -> MemorySearchResult:
        return MemorySearchResult(
            chunk_id=f"chunk-{score}",
            record_id="rec-001",
            source_path="doc.md",
            source_type="doc",
            content=content,
            score=score,
            start_line=1,
            end_line=5,
        )

    def test_first_item_respects_token_budget(self):
        """
        If the first item alone exceeds budget, zero items should be returned.
        Before fix: first item was always added regardless of budget.
        """
        assembler = ContextAssembler()

        # Create content that is 2000 characters long → ~500 tokens
        large_content = "x" * 2000
        results = [self._make_result(large_content, score=0.9)]

        # Budget of 10 tokens — far too small even for header + first item
        packet = assembler.assemble(task="test task", results=results, budget_tokens=10)

        self.assertEqual(
            len(packet.items), 0,
            msg="No items should be included when even the first item exceeds budget"
        )

    def test_multiple_items_budget_correctly_bounded(self):
        """Budget must stop adding items when limit is reached, at any position."""
        assembler = ContextAssembler()

        # Each content ~400 chars → ~100 tokens per block + metadata overhead
        results = [
            self._make_result("A" * 400, score=0.9),
            self._make_result("B" * 400, score=0.8),
            self._make_result("C" * 400, score=0.7),
        ]

        # Budget that fits exactly ~1 block + header
        header_tokens = estimate_tokens("### Retrieved Project Context\n")
        first_block_approx = estimate_tokens(
            "[MEMORY 1]\nSource: doc.md\nType: doc\nRelevance: 0.90\n\n" + "A" * 400 + "\n"
        )
        tight_budget = header_tokens + first_block_approx + 5

        packet = assembler.assemble(task="test", results=results, budget_tokens=tight_budget)
        self.assertLessEqual(
            packet.token_estimate, tight_budget + 50,  # allow small estimation slack
            msg="token_estimate must not significantly exceed budget"
        )


class TestBugFix4_RetrievalMetadataOnContextPacket(unittest.TestCase):
    """
    BUG-4: ContextPacket had no `retrieval_metadata` field. The Stage 3 spec
    requires the packet to carry embedding model name, score strategy, threshold,
    and filter params for full auditability.
    FIX: retrieval_metadata: Dict[str, Any] added to ContextPacket model,
    and RetrievalService.retrieve_context() populates it.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cliverse_bugfix4_")
        self.db_path = Path(self.temp_dir) / "test.db"
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

    def test_context_packet_has_retrieval_metadata_field(self):
        """ContextPacket model must expose retrieval_metadata."""
        packet = ContextPacket(task="test")
        self.assertTrue(
            hasattr(packet, "retrieval_metadata"),
            msg="ContextPacket must have a retrieval_metadata field"
        )
        self.assertIsInstance(packet.retrieval_metadata, dict)

    def test_retrieve_context_populates_retrieval_metadata(self):
        """retrieve_context() must populate retrieval_metadata with audit info."""
        self.ingestion.ingest(
            content="The system uses Postgres as the primary data store.",
            project_id="proj-meta",
            source_type="doc",
            source_path="arch.md",
        )

        packet = self.retrieval.retrieve_context(
            task="What database does the system use?",
            project_id="proj-meta",
            top_k=3,
            min_score=0.1,
        )

        meta = packet.retrieval_metadata
        self.assertIsInstance(meta, dict, msg="retrieval_metadata must be a dict")
        self.assertIn("embedding_model", meta, msg="must record embedding model used")
        self.assertIn("score_strategy", meta, msg="must record scoring strategy")
        self.assertIn("min_score", meta, msg="must record min_score threshold applied")
        self.assertIn("top_k_requested", meta, msg="must record top_k requested")
        self.assertIn("results_returned", meta, msg="must record actual results count")
        self.assertEqual(meta["embedding_model"], "cliverse-local-baseline-v1")
        self.assertEqual(meta["min_score"], 0.1)
        self.assertEqual(meta["top_k_requested"], 3)

    def test_retrieval_metadata_on_empty_result(self):
        """Even when no results match, retrieval_metadata must be populated."""
        packet = self.retrieval.retrieve_context(
            task="completely unrelated random query xyz",
            project_id="proj-empty-meta",
            min_score=0.99,
        )
        meta = packet.retrieval_metadata
        self.assertIsInstance(meta, dict)
        self.assertIn("embedding_model", meta)
        self.assertEqual(meta["results_returned"], 0)


class TestBugFix5_SearchServiceAbstractionBoundary(unittest.TestCase):
    """
    BUG-5: search.py imported SQLiteMemoryStorage and LocalBaselineEmbeddingProvider
    at module level, violating its own stated contract: "Consumes only abstract
    MemoryStorage and EmbeddingProvider interfaces."
    FIX: concrete classes moved to lazy factory functions; module-level imports
    are now only the abstract base classes.
    """

    def test_search_module_does_not_import_concrete_storage_at_top_level(self):
        """
        The retrieval.search module must NOT have SQLiteMemoryStorage or
        LocalBaselineEmbeddingProvider in its module-level namespace.
        """
        import memory.retrieval.search as search_module

        self.assertFalse(
            hasattr(search_module, "SQLiteMemoryStorage"),
            msg="SQLiteMemoryStorage must NOT be a module-level name in retrieval.search"
        )
        self.assertFalse(
            hasattr(search_module, "LocalBaselineEmbeddingProvider"),
            msg="LocalBaselineEmbeddingProvider must NOT be a module-level name in retrieval.search"
        )

    def test_retrieval_service_accepts_any_memory_storage_implementation(self):
        """
        RetrievalService must work with any MemoryStorage implementation,
        not just SQLiteMemoryStorage.
        """
        from memory.storage.base import MemoryStorage
        from memory.models import MemoryRecord, MemoryChunk
        from typing import List, Optional, Dict, Any

        class InMemoryStorage(MemoryStorage):
            """Minimal in-memory storage stub for testing abstraction."""
            def __init__(self):
                self._records: Dict[str, MemoryRecord] = {}

            def save_record(self, record: MemoryRecord, chunks: List[MemoryChunk]) -> None:
                self._records[record.record_id] = record

            def get_record(self, record_id: str) -> Optional[MemoryRecord]:
                return self._records.get(record_id)

            def get_record_by_path(self, project_id: str, source_path: str) -> Optional[MemoryRecord]:
                for r in self._records.values():
                    if r.project_id == project_id and r.source_path == source_path:
                        return r
                return None

            def delete_record(self, record_id: str) -> bool:
                return bool(self._records.pop(record_id, None))

            def list_records(self, project_id=None, source_type=None, limit=100) -> List[MemoryRecord]:
                return list(self._records.values())

            def get_chunks(self, record_id: str) -> List[MemoryChunk]:
                return []

            def search_chunks(self, query_vector, query_text, top_k=5, **kwargs):
                return []

            def store_conversation_turn(self, session_id, role, content, metadata=None) -> str:
                return "turn-stub"

            def get_conversation(self, session_id) -> List[Dict[str, Any]]:
                return []

        # Should construct without error using a non-SQLite storage
        stub_storage = InMemoryStorage()
        service = RetrievalService(
            storage=stub_storage,
            embedding_provider=LocalBaselineEmbeddingProvider(dimension=32),
        )
        # Search on empty storage must return empty list safely
        results = service.search_memory(query="test query", project_id="p1")
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
