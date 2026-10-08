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

    Performance note:
        Member 1's RequestPlanner calls retrieve_context() and get_applicable_rules()
        in sequence for the same task. To prevent two full build_intelligence_context()
        evaluations (double SQLite read + double rule resolution), the adapter maintains a
        one-slot cache keyed on (task_str, project_id, cli_name). Consecutive calls with
        identical arguments share one evaluation result.
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
        self.last_intelligence_context: Optional[LayaIntelligenceContext] = None
        self.last_member2_rules: Dict[str, Any] = {}
        # Single-slot cache: (task_str, project_id, cli_name) → LayaIntelligenceContext
        self._cache_key: Optional[tuple] = None
        self._cached_context: Optional[LayaIntelligenceContext] = None

    def _get_or_build_context(self, task: Any) -> LayaIntelligenceContext:
        """Returns cached context if task/project/cli match last call; builds otherwise.

        This eliminates the double build_intelligence_context() call that occurs when
        Member 1's RequestPlanner invokes retrieve_context() then get_applicable_rules()
        for the same task in a single plan() request.
        """
        # Normalise task to string for cache key
        task_str: str
        if isinstance(task, str):
            task_str = task.strip()
        elif hasattr(task, "task"):
            task_str = str(getattr(task, "task", "")).strip()
        else:
            task_str = str(task).strip()

        cache_key = (task_str, self.project_id, self.cli_name)
        if self._cache_key == cache_key and self._cached_context is not None:
            return self._cached_context

        intel: LayaIntelligenceContext = self.service.build_intelligence_context(
            task=task,
            project_id=self.project_id,
            cli_name=self.cli_name,
        )
        self._cache_key = cache_key
        self._cached_context = intel
        self.last_intelligence_context = intel
        return intel

    def get_last_intelligence_context(self) -> Optional[LayaIntelligenceContext]:
        """Returns the full untruncated LayaIntelligenceContext from the latest call."""
        return self.last_intelligence_context

    def get_member2_rule(self, rule_id: str) -> Optional[Any]:
        """Returns the complete Member 2 Rule model for a given rule_id.

        This is the reliable access path. The _member2_rule attribute attached directly
        to frozen CliverseRule dataclasses via object.__setattr__ is best-effort and
        will not survive pickle, deepcopy, or dataclass replace() operations.
        Use this method for safe downstream access.
        """
        return self.last_member2_rules.get(rule_id)

    def retrieve_context(self, task: Any) -> ContextBundle:
        """
        Retrieves context items and provenance from Member 2 and packs
        them into Member 1's ContextBundle.
        """
        intel = self._get_or_build_context(task)
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
        them into Member 1's Rule dataclass without discarding critical semantics.
        Preserves effect, mandatory state, target domain, and version.

        Uses the single-entry context cache: if retrieve_context() was already called
        for the same task, this returns from the cached result at zero extra cost.
        """
        intel = self._get_or_build_context(task)
        self.last_member2_rules = {r.rule_id: r for r in intel.rule_resolution.winning_rules}

        result_rules: List[CliverseRule] = []
        for r in intel.rule_resolution.winning_rules:
            # Preserve effect and mandatory state prominently in content
            if r.is_mandatory:
                content_str = f"[{r.effect.value} MANDATORY] {r.description}"
                # Ensure mandatory rules carry highest effective priority
                effective_prio = 9999 + getattr(r, "effective_priority", r.priority)
            else:
                content_str = f"[{r.effect.value}] {r.description}"
                effective_prio = getattr(r, "effective_priority", r.priority)

            # Preserve structured metadata (effect, mandatory, version) in source provenance
            source_str = (
                f"rules:{r.target};effect={r.effect.value};mandatory={r.is_mandatory};version={r.version}"
            )

            cliverse_rule = CliverseRule(
                rule_id=r.rule_id,
                content=content_str,
                scope=r.scope.value.lower(),
                priority=effective_prio,
                source=source_str,
            )
            # Best-effort: attach full Member 2 Rule to the frozen dataclass for
            # consumers that inspect _member2_rule directly. WARNING: this attribute
            # is NOT preserved across pickle, deepcopy, or dataclass.replace().
            # Use adapter.get_member2_rule(rule_id) for reliable downstream access.
            try:
                object.__setattr__(cliverse_rule, "_member2_rule", r)
            except (TypeError, AttributeError) as e:
                import warnings
                warnings.warn(
                    f"Could not attach _member2_rule to CliverseRule '{r.rule_id}': {e}. "
                    "Use adapter.get_member2_rule(rule_id) instead.",
                    RuntimeWarning,
                    stacklevel=2,
                )

            result_rules.append(cliverse_rule)

        return result_rules

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
