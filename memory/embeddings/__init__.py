"""
Embeddings Subpackage — Member 2 (RAG + Rules)
"""

from .base import EmbeddingProvider
from .local_engine import LocalBaselineEmbeddingProvider

__all__ = ["EmbeddingProvider", "LocalBaselineEmbeddingProvider"]
