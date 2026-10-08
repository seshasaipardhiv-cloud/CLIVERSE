"""
Context Packet Assembler — Member 2 (RAG + Rules)

Assembles ranked, deduplicated search results into a bounded, source-backed
ContextPacket suitable for direct injection into Member 1's (Laya) prompt engine.
Preserves line-level provenance and provides deterministic token estimation.
"""

import math
from typing import List
from ..models import MemorySearchResult, ContextItem, ContextPacket


def estimate_tokens(text: str) -> int:
    """
    Deterministic approximate token estimator.
    Approximates tokens as max(1, ceil(character_count / 4.0)).
    """
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4.0))


class ContextAssembler:
    """
    Assembles retrieval hits into structured markdown prompt text and ContextPacket.
    """

    def __init__(self, default_budget_tokens: int = 2000):
        self.default_budget_tokens = default_budget_tokens

    def assemble(
        self,
        task: str,
        results: List[MemorySearchResult],
        budget_tokens: int = 2000,
    ) -> ContextPacket:
        """
        Assembles ranked results into a bounded ContextPacket.

        Args:
            task: The user task or prompt.
            results: Ordered, deduplicated list of MemorySearchResult.
            budget_tokens: Maximum token budget for assembled prompt text.

        Returns:
            ContextPacket containing items, formatted markdown, and provenance summary.
        """
        if not results:
            return ContextPacket(
                task=task,
                items=[],
                assembled_prompt_text="",
                token_estimate=0,
                provenance_summary=[],
            )

        items: List[ContextItem] = []
        prompt_blocks: List[str] = []
        total_tokens = 0

        # Header for the context block
        header = "### Retrieved Project Context\n"
        total_tokens += estimate_tokens(header)

        source_paths: set[str] = set()
        source_types: set[str] = set()
        session_ids: set[str] = set()
        scores: List[float] = []

        for idx, res in enumerate(results, start=1):
            # Format source string with line provenance
            if res.start_line is not None and res.end_line is not None:
                source_str = f"{res.source_path}:{res.start_line}-{res.end_line}"
            else:
                source_str = res.source_path

            # Format memory block for Laya consumption
            block = (
                f"[MEMORY {idx}]\n"
                f"Source: {source_str}\n"
                f"Type: {res.source_type}\n"
                f"Relevance: {res.score:.2f}\n\n"
                f"{res.content.strip()}\n"
            )
            block_tokens = estimate_tokens(block)

            # Enforce context budget strictly — even for the first item.
            # Callers that need at least one result regardless of size should
            # pass a budget large enough to contain it.
            if total_tokens + block_tokens > budget_tokens:
                break

            total_tokens += block_tokens
            prompt_blocks.append(block)

            items.append(ContextItem(
                source=source_str,
                source_type=res.source_type,
                relevance_score=res.score,
                snippet=res.content.strip(),
            ))

            source_paths.add(res.source_path)
            source_types.add(res.source_type)
            if res.session_id:
                session_ids.add(res.session_id)
            scores.append(res.score)

        assembled_prompt = header + "\n" + "\n".join(prompt_blocks)

        # Build provenance summary
        min_score = min(scores) if scores else 0.0
        max_score = max(scores) if scores else 0.0
        provenance_summary = [
            f"Total items retrieved: {len(items)}",
            f"Sources: {', '.join(sorted(source_paths))}",
            f"Types: {', '.join(sorted(source_types))}",
            f"Score range: [{min_score:.2f}, {max_score:.2f}]",
        ]
        if session_ids:
            provenance_summary.append(f"Sessions: {', '.join(sorted(session_ids))}")

        return ContextPacket(
            task=task,
            items=items,
            assembled_prompt_text=assembled_prompt.strip(),
            token_estimate=total_tokens,
            provenance_summary=provenance_summary,
        )
