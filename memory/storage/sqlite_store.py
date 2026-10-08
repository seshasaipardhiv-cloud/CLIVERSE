"""
SQLite Memory Storage Implementation — Member 2 (RAG + Rules)

Provides a lightweight, zero-dependency, local-first persistent storage
engine backed by SQLite and standard library math. Stores records, chunks,
vector embeddings, and conversation histories in .envcore/memory/cliverse_memory.db.
"""

import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..models import (
    MemoryRecord,
    MemoryChunk,
    MemorySearchResult,
    current_iso_timestamp,
)
from .base import MemoryStorage


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Computes cosine similarity between two float vectors in [0.0, 1.0]."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    sim = dot / (norm1 * norm2)
    # Normalize from [-1, 1] to [0, 1] for unified scoring
    return max(0.0, min(1.0, (sim + 1.0) / 2.0))


def _keyword_overlap_score(query: str, text: str) -> float:
    """Calculates simple normalized token overlap between query and text."""
    if not query or not text:
        return 0.0
    query_tokens = set(query.lower().split())
    if not query_tokens:
        return 0.0
    text_tokens = set(text.lower().split())
    overlap = len(query_tokens.intersection(text_tokens))
    return overlap / len(query_tokens)


class SQLiteMemoryStorage(MemoryStorage):
    """
    SQLite-backed persistent storage for memory records, chunks, and sessions.
    """

    def __init__(self, db_path: str = ".envcore/memory/cliverse_memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        """Creates tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS memory_records (
                    record_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    session_id TEXT,
                    source_type TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    record_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    embedding TEXT,
                    start_line INTEGER,
                    end_line INTEGER,
                    metadata TEXT NOT NULL,
                    FOREIGN KEY (record_id) REFERENCES memory_records(record_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS conversation_turns (
                    turn_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_records_project ON memory_records(project_id);
                CREATE INDEX IF NOT EXISTS idx_records_path ON memory_records(project_id, source_path);
                CREATE INDEX IF NOT EXISTS idx_records_type ON memory_records(source_type);
                CREATE INDEX IF NOT EXISTS idx_chunks_record ON memory_chunks(record_id);
                CREATE INDEX IF NOT EXISTS idx_chunks_hash ON memory_chunks(content_hash);
                CREATE INDEX IF NOT EXISTS idx_conv_session ON conversation_turns(session_id);
            """)

    def save_record(self, record: MemoryRecord, chunks: List[MemoryChunk]) -> None:
        """Saves or updates a record and replaces all of its chunks atomically."""
        with self._get_connection() as conn:
            # 1. Upsert Record
            conn.execute("""
                INSERT INTO memory_records (
                    record_id, project_id, session_id, source_type, source_path,
                    title, content, tags, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(record_id) DO UPDATE SET
                    project_id = excluded.project_id,
                    session_id = excluded.session_id,
                    source_type = excluded.source_type,
                    source_path = excluded.source_path,
                    title = excluded.title,
                    content = excluded.content,
                    tags = excluded.tags,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
            """, (
                record.record_id,
                record.project_id,
                record.session_id,
                record.source_type,
                record.source_path,
                record.title,
                record.content,
                json.dumps(record.tags),
                json.dumps(record.metadata),
                record.created_at,
                record.updated_at,
            ))

            # 2. Clear old chunks for this record
            conn.execute("DELETE FROM memory_chunks WHERE record_id = ?", (record.record_id,))

            # 3. Insert new chunks
            for ch in chunks:
                emb_json = json.dumps(ch.embedding) if ch.embedding is not None else None
                conn.execute("""
                    INSERT INTO memory_chunks (
                        chunk_id, record_id, chunk_index, content, content_hash,
                        embedding, start_line, end_line, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ch.chunk_id,
                    record.record_id,
                    ch.chunk_index,
                    ch.content,
                    ch.content_hash,
                    emb_json,
                    ch.start_line,
                    ch.end_line,
                    json.dumps(ch.metadata),
                ))

    def get_record(self, record_id: str) -> Optional[MemoryRecord]:
        """Retrieves a single memory record by ID."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM memory_records WHERE record_id = ?", (record_id,))
            row = cur.fetchone()
            if not row:
                return None
            return MemoryRecord(
                record_id=row["record_id"],
                project_id=row["project_id"],
                session_id=row["session_id"],
                source_type=row["source_type"],
                source_path=row["source_path"],
                title=row["title"],
                content=row["content"],
                tags=json.loads(row["tags"]),
                metadata=json.loads(row["metadata"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def get_record_by_path(self, project_id: str, source_path: str) -> Optional[MemoryRecord]:
        """Retrieves a single memory record by project_id and source_path."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM memory_records WHERE project_id = ? AND source_path = ? LIMIT 1",
                (project_id, source_path),
            )
            row = cur.fetchone()
            if not row:
                return None
            return MemoryRecord(
                record_id=row["record_id"],
                project_id=row["project_id"],
                session_id=row["session_id"],
                source_type=row["source_type"],
                source_path=row["source_path"],
                title=row["title"],
                content=row["content"],
                tags=json.loads(row["tags"]),
                metadata=json.loads(row["metadata"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def delete_record(self, record_id: str) -> bool:
        """Deletes a record and its chunks."""
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM memory_records WHERE record_id = ?", (record_id,))
            return cur.rowcount > 0

    def list_records(
        self,
        project_id: Optional[str] = None,
        source_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryRecord]:
        """Lists records with optional filtering."""
        query = "SELECT * FROM memory_records WHERE 1=1"
        params: list[Any] = []

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if source_type:
            query += " AND source_type = ?"
            params.append(source_type)

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        records: List[MemoryRecord] = []
        with self._get_connection() as conn:
            cur = conn.execute(query, params)
            for row in cur.fetchall():
                records.append(MemoryRecord(
                    record_id=row["record_id"],
                    project_id=row["project_id"],
                    session_id=row["session_id"],
                    source_type=row["source_type"],
                    source_path=row["source_path"],
                    title=row["title"],
                    content=row["content"],
                    tags=json.loads(row["tags"]),
                    metadata=json.loads(row["metadata"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                ))
        return records

    def get_chunks(self, record_id: str) -> List[MemoryChunk]:
        """Returns all chunks belonging to a record."""
        chunks: List[MemoryChunk] = []
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM memory_chunks WHERE record_id = ? ORDER BY chunk_index ASC", (record_id,))
            for row in cur.fetchall():
                emb = json.loads(row["embedding"]) if row["embedding"] else None
                chunks.append(MemoryChunk(
                    chunk_id=row["chunk_id"],
                    record_id=row["record_id"],
                    chunk_index=row["chunk_index"],
                    content=row["content"],
                    content_hash=row["content_hash"],
                    embedding=emb,
                    start_line=row["start_line"],
                    end_line=row["end_line"],
                    metadata=json.loads(row["metadata"]),
                ))
        return chunks

    def search_chunks(
        self,
        query_vector: Optional[List[float]],
        query_text: str,
        top_k: int = 5,
        project_id: Optional[str] = None,
        min_score: float = 0.0,
    ) -> List[MemorySearchResult]:
        """Performs hybrid vector & keyword similarity search across chunks."""
        sql = """
            SELECT c.chunk_id, c.record_id, c.content, c.embedding, c.start_line, c.end_line,
                   c.metadata as chunk_meta, r.source_path, r.source_type, r.project_id
            FROM memory_chunks c
            JOIN memory_records r ON c.record_id = r.record_id
            WHERE 1=1
        """
        params: list[Any] = []
        if project_id:
            sql += " AND r.project_id = ?"
            params.append(project_id)

        candidates: List[tuple[float, MemorySearchResult]] = []
        with self._get_connection() as conn:
            cur = conn.execute(sql, params)
            for row in cur.fetchall():
                text = row["content"]
                vec_score = 0.0
                if query_vector and row["embedding"]:
                    emb = json.loads(row["embedding"])
                    vec_score = _cosine_similarity(query_vector, emb)

                kw_score = _keyword_overlap_score(query_text, text)

                # Combined score
                if query_vector:
                    final_score = (0.7 * vec_score) + (0.3 * kw_score)
                else:
                    final_score = kw_score

                if final_score >= min_score:
                    chunk_meta = json.loads(row["chunk_meta"]) if row["chunk_meta"] else {}
                    res = MemorySearchResult(
                        chunk_id=row["chunk_id"],
                        record_id=row["record_id"],
                        source_path=row["source_path"],
                        source_type=row["source_type"],
                        content=text,
                        score=round(final_score, 4),
                        start_line=row["start_line"],
                        end_line=row["end_line"],
                        metadata=chunk_meta,
                    )
                    candidates.append((final_score, res))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [res for _, res in candidates[:top_k]]

    def store_conversation_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Stores a conversation turn in chronological sequence."""
        turn_id = f"turn-{uuid4().hex[:8]}"
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO conversation_turns (turn_id, session_id, role, content, metadata, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                turn_id,
                session_id,
                role,
                content,
                json.dumps(metadata or {}),
                current_iso_timestamp(),
            ))
        return turn_id

    def get_conversation(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieves all conversation turns for a session."""
        turns: List[Dict[str, Any]] = []
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM conversation_turns WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            )
            for row in cur.fetchall():
                turns.append({
                    "turn_id": row["turn_id"],
                    "session_id": row["session_id"],
                    "role": row["role"],
                    "content": row["content"],
                    "metadata": json.loads(row["metadata"]),
                    "timestamp": row["timestamp"],
                })
        return turns
