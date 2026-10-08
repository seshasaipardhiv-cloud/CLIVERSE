"""
Ingestion Pipeline Orchestrator — Member 2 (RAG + Rules)

Orchestrates the complete data ingestion flow:
SOURCE CONTENT
    ↓
NORMALIZATION
    ↓
CONTENT HASHING
    ↓
DEDUPLICATION (Skip if UNMODIFIED, Update if MODIFIED, Insert if NEW)
    ↓
CHUNKING (Preserving line bounds & natural structures)
    ↓
EMBEDDINGS (Via pluggable EmbeddingProvider)
    ↓
PERSISTENCE (Atomic save to MemoryStorage)
"""

from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from ..models import MemoryRecord, current_iso_timestamp
from ..storage.base import MemoryStorage
from ..storage.sqlite_store import SQLiteMemoryStorage
from ..embeddings.base import EmbeddingProvider
from ..embeddings.local_engine import LocalBaselineEmbeddingProvider
from .normalizer import normalize_text
from .chunker import TextChunker
from .deduplicator import ContentDeduplicator, IngestionStatus


class IngestionResult(BaseModel):
    """Result summary returned by the IngestionPipeline."""
    record_id: str
    project_id: str
    source_path: str
    status: str  # "NEW" | "MODIFIED" | "UNMODIFIED"
    chunks_created: int = 0
    chunks_skipped: int = 0
    content_hash: str
    embedding_model: str
    embedding_dimension: int
    is_new: bool = False
    is_modified: bool = False


class IngestionPipeline:
    """
    Ingests documents, files, and session transcripts into persistent memory.
    """

    def __init__(
        self,
        storage: Optional[MemoryStorage] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        chunker: Optional[TextChunker] = None,
        deduplicator: Optional[ContentDeduplicator] = None,
    ):
        self.storage = storage or SQLiteMemoryStorage()
        self.embedding_provider = embedding_provider or LocalBaselineEmbeddingProvider()
        self.chunker = chunker or TextChunker()
        self.deduplicator = deduplicator or ContentDeduplicator()

    def ingest(
        self,
        content: str,
        project_id: str = "default",
        source_type: str = "doc",
        source_path: str = "unknown",
        title: Optional[str] = None,
        session_id: Optional[str] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IngestionResult:
        """
        Executes the full ingestion pipeline.

        Args:
            content: Raw text content to ingest.
            project_id: Project identifier for strict multi-tenant isolation.
            source_type: "doc" | "code" | "conversation" | "decision"
            source_path: Filepath or identifier of the source (e.g., "docs/auth.md").
            title: Human-readable title for the record.
            session_id: Optional session identifier if conversation-related.
            tags: Optional tags for categorization.
            metadata: User metadata to persist alongside the record.

        Returns:
            IngestionResult with status and execution statistics.
        """
        # 1. Normalize content
        normalized_content = normalize_text(content)
        content_hash = self.deduplicator.compute_hash(normalized_content)

        # 2. Check deduplication status
        status, existing_record = self.deduplicator.check_status(
            storage=self.storage,
            project_id=project_id,
            source_path=source_path,
            new_content_hash=content_hash,
        )

        # 3. Handle UNMODIFIED content (incremental indexing skip)
        if status == IngestionStatus.UNMODIFIED and existing_record is not None:
            existing_chunks = self.storage.get_chunks(existing_record.record_id)
            return IngestionResult(
                record_id=existing_record.record_id,
                project_id=project_id,
                source_path=source_path,
                status=status.value,
                chunks_created=0,
                chunks_skipped=len(existing_chunks),
                content_hash=content_hash,
                embedding_model=self.embedding_provider.model_name,
                embedding_dimension=self.embedding_provider.dimension,
                is_new=False,
                is_modified=False,
            )

        # 4. Determine Record ID (preserve ID if updating existing record)
        if status == IngestionStatus.MODIFIED and existing_record is not None:
            record_id = existing_record.record_id
            created_at = existing_record.created_at
        else:
            record_id = str(uuid4())
            created_at = current_iso_timestamp()

        # 5. Build MemoryRecord
        record_metadata = dict(metadata or {})
        record_metadata["content_hash"] = content_hash

        record = MemoryRecord(
            record_id=record_id,
            project_id=project_id,
            session_id=session_id,
            source_type=source_type,
            source_path=source_path,
            title=title or Path(source_path).name or "Untitled",
            content=normalized_content,
            tags=list(tags or []),
            metadata=record_metadata,
            created_at=created_at,
            updated_at=current_iso_timestamp(),
        )

        # 6. Chunk normalized text (preserves line bounds & provenance)
        chunks = self.chunker.chunk(
            text=normalized_content,
            record_id=record_id,
            source_type=source_type,
            metadata={"source_path": source_path, "project_id": project_id},
        )

        # 7. Generate vector embeddings for chunks
        if chunks:
            chunk_texts = [ch.content for ch in chunks]
            embeddings = self.embedding_provider.embed_documents(chunk_texts)
            for ch, emb in zip(chunks, embeddings):
                ch.embedding = emb

        # 8. Atomically persist record and chunks to storage
        self.storage.save_record(record, chunks)

        return IngestionResult(
            record_id=record.record_id,
            project_id=project_id,
            source_path=source_path,
            status=status.value,
            chunks_created=len(chunks),
            chunks_skipped=0,
            content_hash=content_hash,
            embedding_model=self.embedding_provider.model_name,
            embedding_dimension=self.embedding_provider.dimension,
            is_new=(status == IngestionStatus.NEW),
            is_modified=(status == IngestionStatus.MODIFIED),
        )
