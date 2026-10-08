"""
Ranking and Deduplication Engine — Member 2 (RAG + Rules)

Ranks candidate retrieval hits descending by score, removes redundant/overlapping
chunks from the same document, and enforces score thresholds and top_k limits.
"""

from typing import List
from ..models import MemorySearchResult


def rank_and_deduplicate_results(
    candidates: List[MemorySearchResult],
    min_score: float = 0.35,
    top_k: int = 5,
    overlap_threshold: float = 0.6,
) -> List[MemorySearchResult]:
    """
    Ranks and deduplicates candidate retrieval results:
    1. Filters out candidates below `min_score`.
    2. Sorts candidates descending by relevance `score`.
    3. Deduplicates identical content hashes or identical text bodies (keeps highest-scored).
    4. Detects significant line overlap (> overlap_threshold) between chunks from the same
       record and keeps the higher-scored representative while preserving genuinely distinct
       sections.
    5. Returns up to `top_k` distinct, highest-ranked results.

    Args:
        candidates: Raw retrieval hits from storage.
        min_score: Minimum relevance score to include a result (0.0 – 1.0).
        top_k: Maximum number of results to return.
        overlap_threshold: Fraction of a chunk's lines that must overlap with an already-
            accepted chunk (from the same record) before the chunk is considered redundant.
            Default 0.6 (60%). Lower values are more aggressive; higher values are more
            permissive. Set to 1.0 to disable line-overlap deduplication entirely.
    """
    if not candidates:
        return []

    # 1. Filter by minimum score threshold
    valid = [c for c in candidates if c.score >= min_score]
    if not valid:
        return []

    # 2. Sort descending by score
    valid.sort(key=lambda x: x.score, reverse=True)

    deduped: List[MemorySearchResult] = []
    seen_hashes: set[str] = set()
    seen_texts: set[str] = set()

    for item in valid:
        # Check explicit content hash in metadata
        content_hash = item.metadata.get("content_hash")
        if content_hash and content_hash in seen_hashes:
            continue

        # Check normalized exact text
        cleaned_text = item.content.strip().lower()
        if cleaned_text in seen_texts:
            continue

        # Check overlapping line ranges for the same record_id
        is_redundant_overlap = False
        if item.start_line is not None and item.end_line is not None:
            for accepted in deduped:
                if accepted.record_id == item.record_id and accepted.start_line is not None and accepted.end_line is not None:
                    # Calculate line overlap
                    overlap_start = max(item.start_line, accepted.start_line)
                    overlap_end = min(item.end_line, accepted.end_line)
                    if overlap_start <= overlap_end:
                        overlap_lines = overlap_end - overlap_start + 1
                        item_lines = item.end_line - item.start_line + 1
                        if item_lines > 0 and (overlap_lines / item_lines) > overlap_threshold:
                            is_redundant_overlap = True
                            break

        if is_redundant_overlap:
            continue

        # Accept this result
        if content_hash:
            seen_hashes.add(content_hash)
        seen_texts.add(cleaned_text)
        deduped.append(item)

        if len(deduped) >= top_k:
            break

    return deduped
