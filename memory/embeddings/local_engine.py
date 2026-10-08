"""
Local Baseline Embedding Provider — Member 2 (RAG + Rules)

IMPORTANT:
This is a lightweight, deterministic local baseline provider designed for
offline development, unit testing, and fast zero-dependency execution.
It is NOT equivalent to neural transformer semantic embeddings (e.g. BERT,
OpenAI, or SentenceTransformers).

It implements the identical `EmbeddingProvider` interface so that production
neural providers (Ollama, SentenceTransformers, OpenAI, Gemini) can be
swapped in via configuration without modifying any pipeline code.
"""

import hashlib
import math
import re
from typing import List

from .base import EmbeddingProvider


class LocalBaselineEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic local baseline vectorizer based on n-gram and token hashing.

    Produces normalized float vectors of a fixed dimensionality using
    Murmur/SHA-256 token bucket projections and L2 normalization.
    """

    def __init__(self, dimension: int = 64, model_name: str = "cliverse-local-baseline-v1"):
        if dimension <= 0:
            raise ValueError(f"Embedding dimension must be positive, got {dimension}")
        self._dimension = dimension
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _tokenize_features(self, text: str) -> List[str]:
        """Extracts word tokens and character 3-grams from text."""
        cleaned = text.lower().strip()
        if not cleaned:
            return []

        # 1. Word tokens
        words = re.findall(r"\b[a-z0-9_]+\b", cleaned)

        # 2. Character 3-grams for subword robustness
        ngrams: List[str] = []
        for word in words:
            if len(word) >= 3:
                for i in range(len(word) - 2):
                    ngrams.append(word[i : i + 3])

        return words + ngrams

    def _vectorize_text(self, text: str) -> List[float]:
        """Maps text features into a normalized float vector."""
        features = self._tokenize_features(text)
        if not features:
            return [0.0] * self._dimension

        vector = [0.0] * self._dimension

        for feat in features:
            # Deterministic bucket index via SHA-256 hash
            digest = hashlib.sha256(feat.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], byteorder="big") % self._dimension
            # Sign hash for balanced projections (+1 / -1)
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        # L2-normalization
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0.0:
            vector = [round(x / norm, 6) for x in vector]

        # Ensure exact dimension
        assert len(vector) == self._dimension, f"Vector dimension mismatch: {len(vector)} != {self._dimension}"
        return vector

    def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """Generates vectors for a list of documents."""
        if not documents:
            return []
        return [self._vectorize_text(doc) for doc in documents]

    def embed_query(self, query: str) -> List[float]:
        """Generates a vector for a single search query."""
        return self._vectorize_text(query)
