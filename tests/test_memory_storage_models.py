"""
Unit Tests for Member 2 (Memory Models, Rules Models & SQLite Storage)
Compatible with pytest and unittest standard library.
"""

import math
import shutil
import tempfile
import unittest
from pathlib import Path

from memory.models import (
    MemoryRecord,
    MemoryChunk,
    MemorySearchResult,
    ContextItem,
    ContextPacket,
)
from memory.storage.sqlite_store import (
    SQLiteMemoryStorage,
    _cosine_similarity,
    _keyword_overlap_score,
)
from rules.models import (
    Rule,
    RuleScope,
    RuleEffect,
    RuleCondition,
    RuleConflict,
    RuleResolution,
)


class TestMemoryAndRulesStep1(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cliverse_mem_test_")
        self.db_path = Path(self.temp_dir) / "test_memory.db"
        self.storage = SQLiteMemoryStorage(db_path=str(self.db_path))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_memory_models_instantiation(self):
        record = MemoryRecord(
            project_id="proj-alpha",
            source_type="doc",
            source_path="docs/architecture.md",
            title="System Architecture",
            content="CLIVERSE sits above AI CLIs.",
            tags=["architecture", "core"],
        )
        self.assertIsNotNone(record.record_id)
        self.assertEqual(record.project_id, "proj-alpha")
        self.assertEqual(record.tags, ["architecture", "core"])

        chunk = MemoryChunk(
            record_id=record.record_id,
            chunk_index=0,
            content="CLIVERSE sits above AI CLIs.",
            content_hash="abc123hash",
            embedding=[0.1, 0.2, 0.3],
            start_line=1,
            end_line=10,
        )
        self.assertEqual(chunk.chunk_index, 0)
        self.assertEqual(len(chunk.embedding), 3)

        context_item = ContextItem(
            source="docs/architecture.md:1-10",
            source_type="doc",
            relevance_score=0.92,
            snippet="CLIVERSE sits above AI CLIs.",
        )
        packet = ContextPacket(
            task="Explain architecture",
            items=[context_item],
            assembled_prompt_text="### Relevant Architecture\n...",
            token_estimate=150,
            provenance_summary=["docs/architecture.md:1-10"],
        )
        self.assertEqual(len(packet.items), 1)
        self.assertEqual(packet.token_estimate, 150)

    def test_rules_models_and_priority_calculation(self):
        global_rule = Rule(
            name="Global Postgres Rule",
            scope=RuleScope.GLOBAL,
            description="Use PostgreSQL for persistent storage",
            target="database",
            effect=RuleEffect.ENFORCE,
            priority=50,
        )
        project_rule = Rule(
            name="Project MySQL Rule",
            scope=RuleScope.PROJECT,
            description="Override with MySQL for this project",
            target="database",
            effect=RuleEffect.ENFORCE,
            priority=50,
        )
        task_rule = Rule(
            name="Task In-Memory Rule",
            scope=RuleScope.TASK,
            description="Use SQLite in-memory for testing",
            target="database",
            effect=RuleEffect.ENFORCE,
            priority=50,
        )

        # Hierarchy: TASK (400) > PROJECT (200) > GLOBAL (100)
        self.assertEqual(global_rule.effective_priority, 150)
        self.assertEqual(project_rule.effective_priority, 250)
        self.assertEqual(task_rule.effective_priority, 450)
        self.assertTrue(task_rule.effective_priority > project_rule.effective_priority > global_rule.effective_priority)

    def test_math_helpers(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        v3 = [0.0, 1.0, 0.0]

        # Identical vectors -> normalized cosine similarity 1.0
        self.assertAlmostEqual(_cosine_similarity(v1, v2), 1.0, places=4)
        # Orthogonal vectors -> normalized cosine similarity 0.5
        self.assertAlmostEqual(_cosine_similarity(v1, v3), 0.5, places=4)

        score = _keyword_overlap_score("auth login", "this module implements auth login system")
        self.assertEqual(score, 1.0)
        score_partial = _keyword_overlap_score("auth database", "only auth is here")
        self.assertEqual(score_partial, 0.5)

    def test_sqlite_storage_record_lifecycle(self):
        record = MemoryRecord(
            project_id="cliverse-dev",
            source_type="code",
            source_path="src/main.py",
            title="Main Entrypoint",
            content="def main(): pass",
            tags=["entrypoint"],
        )
        chunks = [
            MemoryChunk(
                record_id=record.record_id,
                chunk_index=0,
                content="def main(): pass",
                content_hash="h1",
                embedding=[0.5, 0.5, 0.0],
                start_line=1,
                end_line=2,
            )
        ]

        self.storage.save_record(record, chunks)

        # Retrieve
        fetched = self.storage.get_record(record.record_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.title, "Main Entrypoint")

        fetched_chunks = self.storage.get_chunks(record.record_id)
        self.assertEqual(len(fetched_chunks), 1)
        self.assertEqual(fetched_chunks[0].content, "def main(): pass")

        # List
        records = self.storage.list_records(project_id="cliverse-dev")
        self.assertEqual(len(records), 1)

        # Search
        results = self.storage.search_chunks(
            query_vector=[0.5, 0.5, 0.0],
            query_text="main pass",
            top_k=5,
            project_id="cliverse-dev",
        )
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0].record_id, record.record_id)
        self.assertTrue(results[0].score > 0.8)

        # Delete
        self.assertTrue(self.storage.delete_record(record.record_id))
        self.assertIsNone(self.storage.get_record(record.record_id))
        self.assertEqual(len(self.storage.get_chunks(record.record_id)), 0)

    def test_sqlite_conversation_turns(self):
        turn_id = self.storage.store_conversation_turn(
            session_id="session-test-01",
            role="user",
            content="Build authentication system.",
            metadata={"cli": "claude-cli"},
        )
        self.assertIsNotNone(turn_id)

        history = self.storage.get_conversation("session-test-01")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[0]["content"], "Build authentication system.")
        self.assertEqual(history[0]["metadata"]["cli"], "claude-cli")


if __name__ == "__main__":
    unittest.main()
