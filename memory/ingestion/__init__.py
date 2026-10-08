"""
Ingestion Subpackage — Member 2 (RAG + Rules)
"""

from .normalizer import normalize_text
from .chunker import TextChunker
from .deduplicator import ContentDeduplicator, IngestionStatus
from .pipeline import IngestionPipeline, IngestionResult

__all__ = [
    "normalize_text",
    "TextChunker",
    "ContentDeduplicator",
    "IngestionStatus",
    "IngestionPipeline",
    "IngestionResult",
]
