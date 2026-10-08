"""
Retrieval Service — Member 2 (RAG + Rules)

Orchestrates semantic vector search, lexical keyword matching, metadata filtering,
deduplication, and context assembly into a unified service.
Consumes only abstract MemoryStorage and EmbeddingProvider interfaces.
"""

from typing import Any, Dict, List, Optional

from ..models import MemorySearchResult, ContextPacket
from ..storage.base import MemoryStorage
from ..embeddings.base import EmbeddingProvider
from .ranking import rank_and_deduplicate_results
from .assembler import ContextAssembler


def _default_storage() -> MemoryStorage:
    """Lazy import to avoid hard-coding a concrete implementation at module level."""
    from ..storage.sqlite_store import SQLiteMemoryStorage
    return SQLiteMemoryStorage()


def _default_embedding_provider() -> EmbeddingProvider:
    """Lazy import to keep concrete classes off the public import surface."""
    from ..embeddings.local_engine import LocalBaselineEmbeddingProvider
    return LocalBaselineEmbeddingProvider()


class RetrievalService:
    """
    Unified retrieval service consumed by Member 1 (Laya) and Member 3 (Dashboard).
    """

    def __init__(
        self,
        storage: Optional[MemoryStorage] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        assembler: Optional[ContextAssembler] = None,
    ):
        self.storage = storage or _default_storage()
        self.embedding_provider = embedding_provider or _default_embedding_provider()
        self.assembler = assembler or ContextAssembler()

    def search_memory(
        self,
        query: str,
        project_id: Optional[str] = None,
        top_k: int = 5,
        min_score: float = 0.35,
        memory_types: Optional[List[str]] = None,
        source_types: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        source_path: Optional[str] = None,
    ) -> List[MemorySearchResult]:
        """
        Performs hybrid semantic and lexical search across stored memory chunks.

        Args:
            query: User task or search text.
            project_id: Project identifier for strict multi-tenant isolation.
            top_k: Maximum number of search results to return.
            min_score: Minimum relevance score threshold (0.0 to 1.0).
            memory_types: Alias for source_types ("doc", "code", "decision", "conversation").
            source_types: Filter to specific source types.
            session_id: Filter to a specific CLI session.
            source_path: Filter to a specific file or document path.

        Returns:
            Ranked, deduplicated list of MemorySearchResult.
        """
        if not query or not query.strip():
            return []

        # Merge memory_types into source_types
        active_source_types = list(source_types or [])
        if memory_types:
            for mt in memory_types:
                if mt not in active_source_types:
                    active_source_types.append(mt)
        filter_types = active_source_types if active_source_types else None

        # 1. Generate query vector embedding
        query_vec = self.embedding_provider.embed_query(query)

        # 2. Retrieve broader candidate pool from storage — NO pre-filtering on score.
        #    rank_and_deduplicate_results is the single authoritative threshold gate.
        #    Pre-filtering here caused silent loss of borderline candidates due to
        #    floating-point rounding between the two independent filter passes.
        fetch_limit = max(top_k * 3, 20)
        candidates = self.storage.search_chunks(
            query_vector=query_vec,
            query_text=query,
            top_k=fetch_limit,
            project_id=project_id,
            min_score=0.0,  # fetch all; ranking applies the real threshold
            source_types=filter_types,
            session_id=session_id,
            source_path=source_path,
        )

        # 3. Post-filtering (guarantees project isolation and metadata filters)
        filtered_candidates: List[MemorySearchResult] = []
        for c in candidates:
            if project_id and c.project_id and c.project_id != project_id:
                continue
            if filter_types and c.source_type not in filter_types:
                continue
            if session_id and c.session_id and c.session_id != session_id:
                continue
            if source_path and c.source_path != source_path:
                continue
            filtered_candidates.append(c)

        # 4. Rank and remove redundant/overlapping results (single threshold enforcement)
        return rank_and_deduplicate_results(
            candidates=filtered_candidates,
            min_score=min_score,
            top_k=top_k,
        )

    def retrieve_context(
        self,
        task: str,
        project_id: Optional[str] = None,
        top_k: int = 5,
        min_score: float = 0.35,
        memory_types: Optional[List[str]] = None,
        source_types: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        source_path: Optional[str] = None,
        context_budget_tokens: int = 2000,
    ) -> ContextPacket:
        """
        Retrieves relevant memory and packages it into a bounded ContextPacket.

        Args:
            task: Task description from user.
            project_id: Project identifier.
            top_k: Number of memory items to target.
            min_score: Minimum similarity score threshold.
            memory_types: Filter to specific source/memory types.
            source_types: Filter to specific source types.
            session_id: Filter to specific session.
            source_path: Filter to specific path.
            context_budget_tokens: Approximate token budget limit.

        Returns:
            ContextPacket ready for consumption by Member 1 (Laya).
            The `retrieval_metadata` field records the embedding model, score
            strategy, thresholds, and filter params used — fully auditable.
        """
        # Build retrieval metadata upfront for full auditability
        active_types: List[str] = list(source_types or [])
        if memory_types:
            for mt in memory_types:
                if mt not in active_types:
                    active_types.append(mt)

        retrieval_meta: Dict[str, Any] = {
            "embedding_model": self.embedding_provider.model_name,
            "embedding_dimension": self.embedding_provider.dimension,
            "score_strategy": "hybrid(0.7*cosine + 0.3*keyword_overlap)",
            "min_score": min_score,
            "top_k_requested": top_k,
            "budget_tokens": context_budget_tokens,
            "project_id": project_id,
            "session_id_filter": session_id,
            "source_path_filter": source_path,
            "source_type_filters": active_types or None,
        }

        # Fetch relevant items
        results = self.search_memory(
            query=task,
            project_id=project_id,
            top_k=top_k,
            min_score=min_score,
            memory_types=memory_types,
            source_types=source_types,
            session_id=session_id,
            source_path=source_path,
        )

        # Assemble bounded packet with line provenance
        packet = self.assembler.assemble(
            task=task,
            results=results,
            budget_tokens=context_budget_tokens,
        )
        retrieval_meta["results_returned"] = len(results)
        packet.retrieval_metadata = retrieval_meta
        return packet
