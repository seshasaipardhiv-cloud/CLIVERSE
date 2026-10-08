"""
Memory Data Models — Member 2 (RAG + Rules)

Defines Pydantic v2 schemas for memory records, chunks, search results,
and assembled context packets with full provenance tracking.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


def current_iso_timestamp() -> str:
    """Returns current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


class MemoryChunk(BaseModel):
    """
    Atomic searchable chunk of a memory record.
    Includes line numbers and source provenance.
    """
    chunk_id: str = Field(default_factory=lambda: str(uuid4()))
    record_id: str
    chunk_index: int = 0
    content: str
    content_hash: str
    embedding: Optional[List[float]] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryRecord(BaseModel):
    """
    Top-level indexed document, file, session, or architectural note.
    """
    record_id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str = "default"
    session_id: Optional[str] = None
    source_type: str = "doc"  # "code" | "doc" | "conversation" | "decision" | "rule"
    source_path: str
    title: str
    content: str
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=current_iso_timestamp)
    updated_at: str = Field(default_factory=current_iso_timestamp)


class MemorySearchResult(BaseModel):
    """
    Ranked search hit from vector/keyword similarity retrieval.
    """
    chunk_id: str
    record_id: str
    source_path: str
    source_type: str
    content: str
    score: float = Field(ge=0.0, le=1.0)
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ContextItem(BaseModel):
    """
    A single piece of contextual knowledge with strict provenance.
    Answers: 'Where did this piece of context come from?'
    """
    source: str  # e.g., "docs/architecture.md:45-80" or "session-001"
    source_type: str
    relevance_score: float
    snippet: str


class ContextPacket(BaseModel):
    """
    Consolidated context packet assembled for Member 1 (Laya).
    Contains raw items, token estimates, and a ready-to-inject markdown prompt.
    """
    task: str
    items: List[ContextItem] = Field(default_factory=list)
    assembled_prompt_text: str = ""
    token_estimate: int = 0
    provenance_summary: List[str] = Field(default_factory=list)
