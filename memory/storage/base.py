"""
Abstract Storage Interface — Member 2 (RAG + Rules)

Defines the contract for persistent memory storage. All higher-level
memory components (ingestion, retrieval, manager) depend on this protocol,
allowing seamless migration from SQLite to PostgreSQL + pgvector without
modifying business logic.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from ..models import MemoryRecord, MemoryChunk, MemorySearchResult


class MemoryStorage(ABC):
    """Abstract base repository for persistent memory and vector storage."""

    @abstractmethod
    def save_record(self, record: MemoryRecord, chunks: List[MemoryChunk]) -> None:
        """Saves a top-level memory record and its associated searchable chunks."""
        pass

    @abstractmethod
    def get_record(self, record_id: str) -> Optional[MemoryRecord]:
        """Retrieves a single memory record by its identifier."""
        pass

    @abstractmethod
    def get_record_by_path(self, project_id: str, source_path: str) -> Optional[MemoryRecord]:
        """Retrieves a single memory record by project_id and source_path."""
        pass

    @abstractmethod
    def delete_record(self, record_id: str) -> bool:
        """Deletes a record and cascades deletion to all associated chunks."""
        pass

    @abstractmethod
    def list_records(
        self,
        project_id: Optional[str] = None,
        source_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryRecord]:
        """Lists stored memory records, optionally filtered by project or source type."""
        pass

    @abstractmethod
    def get_chunks(self, record_id: str) -> List[MemoryChunk]:
        """Retrieves all chunks belonging to a specific record."""
        pass

    @abstractmethod
    def search_chunks(
        self,
        query_vector: Optional[List[float]],
        query_text: str,
        top_k: int = 5,
        project_id: Optional[str] = None,
        min_score: float = 0.0,
        source_types: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        source_path: Optional[str] = None,
    ) -> List[MemorySearchResult]:
        """Performs ranked similarity and/or keyword search over chunks with optional filtering."""
        pass

    @abstractmethod
    def store_conversation_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Stores a single message turn from an AI CLI session."""
        pass

    @abstractmethod
    def get_conversation(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieves chronological interaction history for a session."""
        pass
