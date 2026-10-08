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


import hashlib
import json


def _canonicalize_for_cache(val: Any) -> Any:
    """Recursively converts data structures to canonical JSON-serializable primitives with sorted keys."""
    if isinstance(val, dict):
        return {str(k): _canonicalize_for_cache(v) for k, v in sorted(val.items(), key=lambda item: str(item[0]))}
    elif isinstance(val, (list, tuple)):
        return [_canonicalize_for_cache(x) for x in val]
    elif isinstance(val, set):
        return sorted([_canonicalize_for_cache(x) for x in val], key=lambda x: str(x))
    elif hasattr(val, "model_dump") and callable(val.model_dump):
        return _canonicalize_for_cache(val.model_dump())
    elif hasattr(val, "as_dict") and callable(val.as_dict):
        return _canonicalize_for_cache(val.as_dict())
    elif isinstance(val, (int, float, bool, str)) or val is None:
        return val
    else:
        return str(val)


def compute_adapter_context_cache_key(
    task: Any,
    project_id: Optional[str] = None,
    cli_name: Optional[str] = None,
    task_metadata: Optional[Dict[str, Any]] = None,
    task_rules: Optional[List[Any]] = None,
    mutation_version: int = 0,
) -> str:
    """
    Computes a deterministic cryptographic SHA-256 fingerprint of all inputs affecting intelligence context.

    Guarantees:
      1. Normalizes task text (using LayaIntelligenceService._extract_task_text).
      2. Includes normalized task text, project_id, cli_name, metadata fingerprint,
         task_rules fingerprint, and mutation_version.
      3. Independent of object identity and dictionary key insertion order.
      4. Deterministic list and nested structure handling.
      5. Pure cryptographic SHA-256 (no process-randomized hash()).
    """
    try:
        norm_task = LayaIntelligenceService._extract_task_text(task)
    except Exception:
        norm_task = str(task).strip()

    combined_meta: Dict[str, Any] = {}
    if hasattr(task, "as_dict") and callable(task.as_dict):
        try:
            combined_meta.update(task.as_dict())
        except Exception:
            pass
    if task_metadata:
        combined_meta.update(task_metadata)

    canonical_meta = _canonicalize_for_cache(combined_meta)

    canonical_rules = []
    if task_rules:
        for r in task_rules:
            if hasattr(r, "model_dump") and callable(r.model_dump):
                canonical_rules.append(_canonicalize_for_cache(r.model_dump()))
            elif hasattr(r, "as_dict") and callable(r.as_dict):
                canonical_rules.append(_canonicalize_for_cache(r.as_dict()))
            else:
                canonical_rules.append(_canonicalize_for_cache(str(r)))
        canonical_rules.sort(key=lambda x: json.dumps(x, sort_keys=True))

    payload = {
        "task": norm_task,
        "project_id": str(project_id) if project_id is not None else None,
        "cli_name": str(cli_name) if cli_name is not None else None,
        "metadata": canonical_meta,
        "rules": canonical_rules,
        "mutation_version": mutation_version,
    }

    canonical_json_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json_str.encode("utf-8")).hexdigest()


def parse_cliverse_rule_semantics(rule: CliverseRule) -> Dict[str, Any]:
    """
    Extracts all Member 2 rule semantics preserved across Member 1's public Rule contract.
    Returns:
        dict with: rule_id, description, scope, priority, effect, is_mandatory, target, version
    """
    rule_id = rule.rule_id
    scope = rule.scope
    priority = rule.priority

    content = rule.content
    effect = "ALLOW"
    is_mandatory = False
    description = content

    if content.startswith("[") and "]" in content:
        prefix, rest = content[1:].split("]", 1)
        description = rest.strip()
        parts = prefix.split()
        if parts:
            effect = parts[0]
            if "MANDATORY" in parts:
                is_mandatory = True

    target = "unknown"
    version = 1

    # Deterministic JSON metadata parsing (preserves targets containing semicolons, equals, unicode, spaces)
    if ";meta=" in rule.source:
        try:
            meta_json = rule.source.split(";meta=", 1)[1]
            data = json.loads(meta_json)
            if "target" in data:
                target = data["target"]
            if "effect" in data:
                effect = data["effect"]
            if "mandatory" in data:
                is_mandatory = bool(data["mandatory"])
            if "version" in data:
                version = int(data["version"])
        except Exception:
            pass
    elif rule.source.startswith("rules:"):
        source_body = rule.source[len("rules:"):]
        segments = source_body.split(";")
        if segments:
            first_seg = segments[0].strip()
            if "=" in first_seg:
                k, v = first_seg.split("=", 1)
                if k.strip().lower() == "target":
                    target = v.strip()
            elif first_seg:
                target = first_seg
            for seg in segments[1:]:
                if "=" in seg:
                    k, v = seg.split("=", 1)
                    k = k.strip().lower()
                    v = v.strip()
                    if k == "effect":
                        effect = v
                    elif k == "mandatory":
                        is_mandatory = (v.lower() == "true")
                    elif k == "version":
                        try:
                            version = int(v)
                        except ValueError:
                            pass
                    elif k == "target":
                        target = v


    return {
        "rule_id": rule_id,
        "description": description,
        "scope": scope,
        "priority": priority,
        "effect": effect,
        "is_mandatory": is_mandatory,
        "target": target,
        "version": version,
    }


class CliverseMemoryProviderAdapter:
    """
    Adapter implementing Member 1's MemoryProvider protocol.
    Delegates retrieval and rule resolution to LayaIntelligenceService.

    Performance note:
        Member 1's RequestPlanner calls retrieve_context() and get_applicable_rules()
        in sequence for the same task. To prevent two full build_intelligence_context()
        evaluations (double SQLite read + double rule resolution), the adapter maintains a
        deterministic single-entry cache keyed on cryptographic SHA-256 fingerprint of all
        result-affecting inputs. Consecutive calls with identical arguments share one evaluation result.
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
        # Single-slot cache: deterministic SHA-256 fingerprint → LayaIntelligenceContext
        self._cached_key: Optional[str] = None
        self._cached_context: Optional[LayaIntelligenceContext] = None

    def invalidate_cache(self) -> None:
        """Explicitly invalidates the cached intelligence context."""
        self._cached_key = None
        self._cached_context = None

    def _get_or_build_context(
        self,
        task: Any,
        task_metadata: Optional[Dict[str, Any]] = None,
        task_rules: Optional[List[Any]] = None,
    ) -> LayaIntelligenceContext:
        """Returns cached context if all result-affecting inputs match; builds otherwise.

        This eliminates the double build_intelligence_context() call that occurs when
        Member 1's RequestPlanner invokes retrieve_context() then get_applicable_rules()
        for the same task in a single plan() request.
        """
        mutation_ver = getattr(self.service, "mutation_version", 0)
        cache_key = compute_adapter_context_cache_key(
            task=task,
            project_id=self.project_id,
            cli_name=self.cli_name,
            task_metadata=task_metadata,
            task_rules=task_rules,
            mutation_version=mutation_ver,
        )

        if self._cached_key == cache_key and self._cached_context is not None:
            return self._cached_context

        intel: LayaIntelligenceContext = self.service.build_intelligence_context(
            task=task,
            project_id=self.project_id,
            cli_name=self.cli_name,
            task_metadata=task_metadata,
            task_rules=task_rules,
        )
        self._cached_key = cache_key
        self._cached_context = intel
        self.last_intelligence_context = intel
        return intel

    def get_last_intelligence_context(self) -> Optional[LayaIntelligenceContext]:
        """Returns the full untruncated LayaIntelligenceContext from the latest call."""
        return self.last_intelligence_context

    def get_member2_rule(self, rule_id: str) -> Optional[Any]:
        """Returns the complete Member 2 Rule model for a given rule_id.

        This is an auxiliary lookup/debug mechanism on the adapter. The adapted
        CliverseRule dataclass itself does not carry private attributes and is 100%
        compliant with Member 1's frozen dataclass model.
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

            # Preserve structured metadata (target, effect, mandatory, version) in source provenance
            meta_payload = {
                "target": r.target,
                "effect": r.effect.value,
                "mandatory": r.is_mandatory,
                "version": r.version,
            }
            json_meta = json.dumps(meta_payload, sort_keys=True)
            source_str = (
                f"rules:{r.target};target={r.target};effect={r.effect.value};mandatory={r.is_mandatory};version={r.version};meta={json_meta}"
            )

            cliverse_rule = CliverseRule(
                rule_id=r.rule_id,
                content=content_str,
                scope=r.scope.value.lower(),
                priority=effective_prio,
                source=source_str,
            )
            # Standard public fields only — no object.__setattr__ private mutation
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
        self.invalidate_cache()
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
