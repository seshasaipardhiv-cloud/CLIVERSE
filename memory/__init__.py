"""
CLIVERSE Memory & RAG Subsystem — Member 2

Provides persistent knowledge indexing, normalization, chunking, deduplication,
embeddings, storage, hybrid retrieval, and context assembly with strict
provenance tracking and project isolation.
"""

from .models import (
    MemoryRecord,
    MemoryChunk,
    MemorySearchResult,
    ContextItem,
    ContextPacket,
)
from .storage.base import MemoryStorage
from .storage.sqlite_store import SQLiteMemoryStorage
from .embeddings.base import EmbeddingProvider
from .embeddings.local_engine import LocalBaselineEmbeddingProvider
from .ingestion.normalizer import normalize_text
from .ingestion.chunker import TextChunker
from .ingestion.deduplicator import ContentDeduplicator, IngestionStatus
from .ingestion.pipeline import IngestionPipeline, IngestionResult
from .retrieval.search import RetrievalService
from .retrieval.ranking import rank_and_deduplicate_results
from .retrieval.assembler import ContextAssembler, estimate_tokens
from .intelligence import LayaIntelligenceContext, LayaIntelligenceService

__all__ = [
    "MemoryRecord",
    "MemoryChunk",
    "MemorySearchResult",
    "ContextItem",
    "ContextPacket",
    "MemoryStorage",
    "SQLiteMemoryStorage",
    "EmbeddingProvider",
    "LocalBaselineEmbeddingProvider",
    "normalize_text",
    "TextChunker",
    "ContentDeduplicator",
    "IngestionStatus",
    "IngestionPipeline",
    "IngestionResult",
    "RetrievalService",
    "rank_and_deduplicate_results",
    "ContextAssembler",
    "estimate_tokens",
    "LayaIntelligenceContext",
    "LayaIntelligenceService",
]
