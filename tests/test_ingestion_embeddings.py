"""
Unit & Integration Tests for Stage 2: Ingestion, Chunking, Deduplication, and Embeddings
Compatible with pytest and unittest standard library.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from memory.embeddings.base import EmbeddingProvider
from memory.embeddings.local_engine import LocalBaselineEmbeddingProvider
from memory.ingestion.normalizer import normalize_text
from memory.ingestion.chunker import TextChunker
from memory.ingestion.deduplicator import ContentDeduplicator, IngestionStatus
from memory.ingestion.pipeline import IngestionPipeline
from memory.storage.sqlite_store import SQLiteMemoryStorage


class TestStage2IngestionAndEmbeddings(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cliverse_stage2_test_")
        self.db_path = Path(self.temp_dir) / "test_stage2.db"
        self.storage = SQLiteMemoryStorage(db_path=str(self.db_path))
        self.embedding_provider = LocalBaselineEmbeddingProvider(dimension=64)
        self.pipeline = IngestionPipeline(
            storage=self.storage,
            embedding_provider=self.embedding_provider,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ── 1. NORMALIZATION TESTS ───────────────────────────────────────────────

    def test_normalization_line_endings_and_whitespace(self):
        raw = "line 1   \r\nline 2\t  \rline 3   \r\n\r\n\r\n"
        norm = normalize_text(raw)
        # Windows & Mac CR/CRLF normalized to LF
        self.assertNotIn("\r", norm)
        # Trailing line spaces stripped, trailing excess blanks collapsed
        self.assertEqual(norm, "line 1\nline 2\nline 3\n")

    def test_normalization_preserves_code_indentation_and_blocks(self):
        code = (
            "def calculate(a, b):\n"
            "    # Leading 4 spaces preserved\n"
            "    if a > b:   \n"
            "        return a - b  \n"
            "    return a + b\n"
        )
        norm = normalize_text(code)
        self.assertIn("    # Leading 4 spaces preserved", norm)
        self.assertIn("        return a - b", norm)

    def test_normalization_markdown_and_empty(self):
        md = "# Header 1  \n\nSome paragraph text.  \n## Subheader   \n"
        norm = normalize_text(md)
        self.assertEqual(norm, "# Header 1\n\nSome paragraph text.\n## Subheader\n")

        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text("   \n\r\n  \t  "), "")

    # ── 2. CHUNKING TESTS ────────────────────────────────────────────────────

    def test_chunking_deterministic_and_provenance(self):
        chunker = TextChunker(chunk_size=100, chunk_overlap=20)
        doc = (
            "# Introduction\n"
            "CLIVERSE sits above existing AI CLIs.\n"
            "# Architecture\n"
            "It provides persistent memory, rules, and governance.\n"
        )
        chunks1 = chunker.chunk(doc, record_id="rec-01", source_type="doc")
        chunks2 = chunker.chunk(doc, record_id="rec-01", source_type="doc")

        # Determinism check
        self.assertEqual(len(chunks1), len(chunks2))
        for c1, c2 in zip(chunks1, chunks2):
            self.assertEqual(c1.content, c2.content)
            self.assertEqual(c1.content_hash, c2.content_hash)
            self.assertEqual(c1.start_line, c2.start_line)
            self.assertEqual(c1.end_line, c2.end_line)

        # Line bounds and index check
        self.assertEqual(chunks1[0].chunk_index, 0)
        self.assertEqual(chunks1[0].start_line, 1)
        self.assertTrue(chunks1[0].end_line >= 1)
        self.assertTrue(len(chunks1) >= 2)

    def test_chunking_code_boundaries(self):
        chunker = TextChunker(chunk_size=120, chunk_overlap=10)
        code = (
            "class AuthService:\n"
            "    def __init__(self):\n"
            "        self.token = None\n"
            "\n"
            "def authenticate_user(username, password):\n"
            "    return username == 'admin'\n"
        )
        chunks = chunker.chunk(code, record_id="code-01", source_type="code")
        self.assertTrue(len(chunks) >= 2)
        self.assertEqual(chunks[0].record_id, "code-01")
        self.assertIn("class AuthService", chunks[0].content)

    def test_chunking_empty_document(self):
        chunker = TextChunker()
        self.assertEqual(chunker.chunk("", record_id="rec-00"), [])
        self.assertEqual(chunker.chunk("   \n  ", record_id="rec-00"), [])

    # ── 3. EMBEDDING TESTS ───────────────────────────────────────────────────

    def test_embedding_dimensions_and_determinism(self):
        provider = LocalBaselineEmbeddingProvider(dimension=64)
        self.assertEqual(provider.dimension, 64)
        self.assertEqual(provider.model_name, "cliverse-local-baseline-v1")

        query_vec = provider.embed_query("authentication system")
        self.assertEqual(len(query_vec), 64)

        doc_vecs = provider.embed_documents(["authentication system", "database storage"])
        self.assertEqual(len(doc_vecs), 2)
        self.assertEqual(len(doc_vecs[0]), 64)
        self.assertEqual(len(doc_vecs[1]), 64)

        # Determinism
        query_vec_repeat = provider.embed_query("authentication system")
        self.assertEqual(query_vec, query_vec_repeat)

    def test_embedding_empty_and_invalid_inputs(self):
        provider = LocalBaselineEmbeddingProvider(dimension=32)
        self.assertEqual(provider.embed_documents([]), [])

        empty_vec = provider.embed_query("")
        self.assertEqual(len(empty_vec), 32)
        self.assertTrue(all(v == 0.0 for v in empty_vec))

        with self.assertRaises(ValueError):
            LocalBaselineEmbeddingProvider(dimension=0)

    # ── 4. DEDUPLICATION TESTS ───────────────────────────────────────────────

    def test_deduplication_lifecycle(self):
        dedup = ContentDeduplicator()
        h1 = dedup.compute_hash("Initial document content\n")
        h2 = dedup.compute_hash("Initial document content\n")
        h3 = dedup.compute_hash("Modified document content\n")

        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)

        # Check against clean storage
        status, rec = dedup.check_status(self.storage, "proj-1", "docs/intro.md", h1)
        self.assertEqual(status, IngestionStatus.NEW)
        self.assertIsNone(rec)

    # ── 5. PIPELINE INTEGRATION & PROJECT ISOLATION ──────────────────────────

    def test_pipeline_full_flow_and_incremental_indexing(self):
        content_v1 = "# Overview\nCLIVERSE is a local-first development environment.\n"
        res1 = self.pipeline.ingest(
            content=content_v1,
            project_id="proj-alpha",
            source_type="doc",
            source_path="docs/overview.md",
            title="Overview Doc",
        )

        self.assertEqual(res1.status, "NEW")
        self.assertTrue(res1.is_new)
        self.assertFalse(res1.is_modified)
        self.assertTrue(res1.chunks_created > 0)
        self.assertEqual(res1.chunks_skipped, 0)
        self.assertEqual(res1.embedding_dimension, 64)

        # Ingest IDENTICAL content again -> UNMODIFIED (skip)
        res2 = self.pipeline.ingest(
            content=content_v1,
            project_id="proj-alpha",
            source_type="doc",
            source_path="docs/overview.md",
        )
        self.assertEqual(res2.status, "UNMODIFIED")
        self.assertFalse(res2.is_new)
        self.assertFalse(res2.is_modified)
        self.assertEqual(res2.chunks_created, 0)
        self.assertEqual(res2.chunks_skipped, res1.chunks_created)
        self.assertEqual(res2.record_id, res1.record_id)

        # Ingest MODIFIED content -> MODIFIED (update)
        content_v2 = "# Overview\nCLIVERSE is a local-first AI development environment with RAG and rules.\n"
        res3 = self.pipeline.ingest(
            content=content_v2,
            project_id="proj-alpha",
            source_type="doc",
            source_path="docs/overview.md",
        )
        self.assertEqual(res3.status, "MODIFIED")
        self.assertFalse(res3.is_new)
        self.assertTrue(res3.is_modified)
        self.assertTrue(res3.chunks_created > 0)
        self.assertEqual(res3.record_id, res1.record_id)  # Preserves stable ID

    def test_pipeline_project_isolation(self):
        shared_content = "def connect_db(): return True\n"

        # Project A
        res_a = self.pipeline.ingest(
            content=shared_content,
            project_id="project-A",
            source_type="code",
            source_path="src/db.py",
        )
        # Project B with identical relative file path
        res_b = self.pipeline.ingest(
            content=shared_content,
            project_id="project-B",
            source_type="code",
            source_path="src/db.py",
        )

        self.assertNotEqual(res_a.record_id, res_b.record_id)
        self.assertEqual(res_a.status, "NEW")
        self.assertEqual(res_b.status, "NEW")

        # Verify storage isolation
        records_a = self.storage.list_records(project_id="project-A")
        records_b = self.storage.list_records(project_id="project-B")
        self.assertEqual(len(records_a), 1)
        self.assertEqual(len(records_b), 1)
        self.assertEqual(records_a[0].project_id, "project-A")
        self.assertEqual(records_b[0].project_id, "project-B")

    def test_provenance_preservation(self):
        doc = (
            "Line 1: Beginning of specification.\n"
            "Line 2: Important architecture decision.\n"
            "Line 3: Database must use PostgreSQL.\n"
        )
        res = self.pipeline.ingest(
            content=doc,
            project_id="proj-prov",
            source_type="doc",
            source_path="specs/database.md",
        )
        chunks = self.storage.get_chunks(res.record_id)
        self.assertTrue(len(chunks) > 0)
        self.assertEqual(chunks[0].start_line, 1)
        self.assertTrue(chunks[0].end_line >= 1)
        self.assertEqual(chunks[0].metadata["source_path"], "specs/database.md")
        self.assertEqual(chunks[0].metadata["project_id"], "proj-prov")
        self.assertIsNotNone(chunks[0].embedding)
        self.assertEqual(len(chunks[0].embedding), 64)

    # ── 6. HEURISTIC CHUNKING & TOKEN ESTIMATION EDGE CASES ───────────────────

    def test_heuristic_chunking_edge_cases_and_complex_code(self):
        """
        Verifies that heuristic structure-aware chunking handles complex real-world code
        (multiline decorators, TypeScript interfaces, embedded SQL) deterministically without crashing.
        """
        chunker = TextChunker(chunk_size=100, chunk_overlap=15)

        # Complex Python with multiline decorators and embedded SQL
        complex_code = (
            "@app.post(\n"
            "    '/api/v1/users/{user_id}/permissions',\n"
            "    response_model=UserPermissionResponse,\n"
            "    dependencies=[Depends(require_admin_auth)]\n"
            ")\n"
            "async def update_user_permissions(user_id: str, perms: PermissionUpdateRequest) -> UserPermissionResponse:\n"
            "    sql = '''\n"
            "        UPDATE user_permissions\n"
            "        SET role = :role, updated_at = NOW()\n"
            "        WHERE user_id = :uid\n"
            "    '''\n"
            "    await db.execute(sql, {'role': perms.role, 'uid': user_id})\n"
            "    return UserPermissionResponse(user_id=user_id, status='SUCCESS')\n"
        )
        chunks = chunker.chunk(complex_code, record_id="code-complex", source_type="code")
        self.assertTrue(len(chunks) >= 1)
        # Content preserved without corruption
        reconstructed_snippet = "".join(c.content for c in chunks)
        self.assertIn("update_user_permissions", reconstructed_snippet)
        self.assertIn("UPDATE user_permissions", reconstructed_snippet)

        # TypeScript interface with generics
        ts_code = (
            "export interface CloudWorkerNode<T extends BaseResource> {\n"
            "    readonly id: string;\n"
            "    status: 'ACTIVE' | 'DRAINING' | 'TERMINATED';\n"
            "    payload: T;\n"
            "    processEvent: (event: EventEnvelope<T>) => Promise<DispatchResult>;\n"
            "}\n"
        )
        ts_chunks = chunker.chunk(ts_code, record_id="ts-complex", source_type="code")
        self.assertTrue(len(ts_chunks) >= 1)
        self.assertIn("CloudWorkerNode", ts_chunks[0].content)

    def test_approximate_token_counting_properties(self):
        """
        Verifies token counting is approximate, deterministic, character-based,
        and monotonic across code, punctuation, Unicode, and long lines.
        """
        from memory.retrieval.assembler import estimate_tokens

        # Empty string
        self.assertEqual(estimate_tokens(""), 0)

        # Short text
        self.assertEqual(estimate_tokens("word"), 1)
        self.assertEqual(estimate_tokens("two words!"), 3)

        # Code with dense punctuation and symbols
        code_str = "def fn(a: int, b: list[str] = []) -> None: pass"
        est_code = estimate_tokens(code_str)
        self.assertGreaterEqual(est_code, 10)
        self.assertLessEqual(est_code, 20)

        # Unicode text
        unicode_str = "Configuration de la base de données et clés API."
        est_uni = estimate_tokens(unicode_str)
        self.assertGreater(est_uni, 0)
        self.assertEqual(est_uni, estimate_tokens(unicode_str))  # Deterministic

        # Monotonic property: longer text produces >= tokens
        short_text = "short"
        medium_text = short_text * 10
        long_text = short_text * 100
        self.assertLess(estimate_tokens(short_text), estimate_tokens(medium_text))
        self.assertLess(estimate_tokens(medium_text), estimate_tokens(long_text))


if __name__ == "__main__":
    unittest.main()

