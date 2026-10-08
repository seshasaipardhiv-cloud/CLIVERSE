"""
Embedding Provider Abstraction — Member 2 (RAG + Rules)

Defines the clean interface for generating vector embeddings from text.
All components in the ingestion and retrieval subsystems depend strictly
on this abstraction, avoiding vendor lock-in.
"""

from abc import ABC, abstractmethod
from typing import List


class EmbeddingProvider(ABC):
    """
    Abstract contract for text embedding models.

    Implementations may be local baseline engines, local neural models
    (sentence-transformers, Ollama), or remote APIs (OpenAI, Gemini).
    """

    @abstractmethod
    def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """
        Generates vector embeddings for a batch of text documents.

        Args:
            documents: List of text strings to embed.

        Returns:
            List of float vectors, each of length `dimension`.
        """
        pass

    @abstractmethod
    def embed_query(self, query: str) -> List[float]:
        """
        Generates a vector embedding for a single search query.

        Args:
            query: Search query text.

        Returns:
            A single float vector of length `dimension`.
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifier of the embedding model."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of the output vectors (e.g., 64, 128, 768, 1536)."""
        pass
