"""
Cliverse Member 1 MemoryProvider Adapter — Member 2 (Memory/RAG + Rules)

Bridges Member 2's LayaIntelligenceService to Member 1's MemoryProvider Protocol
(defined in src/cliverse/contracts.py).

Allows Member 1's RequestPlanner to consume real Member 2 cognitive context
and engineering rules without modifying Member 1 internals.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# Ensure src/ is on sys.path if repository layout contains it
_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if _SRC_DIR.is_dir() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from memory.intelligence import LayaIntelligenceContext, LayaIntelligenceService

# Safely import Member 1 contracts if available
try:
    from cliverse.contracts import (
        ContextBundle,
        ContextItem,
        MemoryHit,
        MemoryRef,
        Rule as CliverseRule,
        StructuredTask,
    )
except ImportError:
    # Fallback dataclasses if cliverse package is not in sys.path
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class ContextItem:  # type: ignore[no-redef]
        item_id: str
        content: str
        source: str
        score: Optional[float] = None

    @dataclass(frozen=True)
    class ContextBundle:  # type: ignore[no-redef]
        items: tuple[ContextItem, ...]
        provenance: tuple[str, ...]
        retrieved_at: str

        @classmethod
        def empty(cls, reason: str) -> "ContextBundle":
            return cls(
                items=(),
                provenance=(reason,),
                retrieved_at=datetime.now(timezone.utc).isoformat(),
            )

    @dataclass(frozen=True)
    class CliverseRule:  # type: ignore[no-redef]
        rule_id: str
        content: str
        scope: str
        priority: int
        source: str

    @dataclass(frozen=True)
    class MemoryRef:  # type: ignore[no-redef]
        memory_id: str
        source: str
        stored_at: str

    @dataclass(frozen=True)
    class MemoryHit:  # type: ignore[no-redef]
        memory_id: str
        content: str
        source: str
        score: Optional[float] = None

    StructuredTask = Any  # type: ignore[assignment,misc]


class CliverseMemoryProviderAdapter:
    """
    Adapter implementing Member 1's MemoryProvider protocol.
    Delegates retrieval and rule resolution to LayaIntelligenceService.
    """

    def __init__(
        self,
        service: Optional[LayaIntelligenceService] = None,
        project_id: Optional[str] = None,
        cli_name: Optional[str] = None,
    ) -> None:
        self.service = service or LayaIntelligenceService()
        self.project_id = project_id
        self.cli_name = cli_name

    def retrieve_context(self, task: Any) -> ContextBundle:
        """
        Retrieves context items and provenance from Member 2 and packs
        them into Member 1's ContextBundle.
        """
        intel: LayaIntelligenceContext = self.service.build_intelligence_context(
            task=task,
            project_id=self.project_id,
            cli_name=self.cli_name,
        )
        items = tuple(
            ContextItem(
                item_id=f"mem-{idx}",
                content=item.snippet,
                source=item.source,
                score=item.relevance_score,
            )
            for idx, item in enumerate(intel.memory_context.items, start=1)
        )
        provenance = (
            tuple(intel.context_sources)
            if intel.context_sources
            else ("Member 2 Knowledge Index (no matching chunks)",)
        )
        return ContextBundle(
            items=items,
            provenance=provenance,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )

    def get_applicable_rules(self, task: Any) -> List[CliverseRule]:
        """
        Retrieves winning rules from Member 2 deterministic resolution and maps
        them into Member 1's Rule dataclass.
        """
        intel: LayaIntelligenceContext = self.service.build_intelligence_context(
            task=task,
            project_id=self.project_id,
            cli_name=self.cli_name,
        )
        return [
            CliverseRule(
                rule_id=r.rule_id,
                content=r.description,
                scope=r.scope.value.lower(),
                priority=r.priority,
                source=f"rules:{r.target}",
            )
            for r in intel.rule_resolution.winning_rules
        ]

    def store_memory(self, data: Dict[str, Any]) -> MemoryRef:
        """Stores a memory record via Member 2 IngestionPipeline."""
        content = data.get("content", "")
        project_id = data.get("project_id", self.project_id or "default")
        source_type = data.get("source_type", "doc")
        source_path = data.get("source_path", "unknown")
        title = data.get("title")

        res = self.service.store_memory(
            content=content,
            project_id=project_id,
            source_type=source_type,
            source_path=source_path,
            title=title,
        )
        return MemoryRef(
            memory_id=res.record_id,
            source=source_path,
            stored_at=datetime.now(timezone.utc).isoformat(),
        )

    def search_memory(self, query: str) -> List[MemoryHit]:
        """Searches memory via Member 2 RetrievalService."""
        hits = self.service.search_memory(
            query=query,
            project_id=self.project_id,
        )
        return [
            MemoryHit(
                memory_id=hit.chunk_id,
                content=hit.content,
                source=hit.source_path,
                score=hit.score,
            )
            for hit in hits
        ]
