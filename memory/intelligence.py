"""
Unified Laya Intelligence Context & Service — Member 2 (RAG + Rules)

Defines the stable intelligence contract consumed by Member 1 (Laya Engine).
Orchestrates semantic project memory, applicable engineering rules,
deterministic conflict resolution, and structured prompt context.
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from memory.models import ContextPacket, MemorySearchResult
from memory.retrieval.search import RetrievalService
from memory.storage.base import MemoryStorage
from memory.ingestion.pipeline import IngestionPipeline, IngestionResult
from memory.embeddings.base import EmbeddingProvider
from rules.models import (
    Rule,
    RuleConflict,
    RuleEffect,
    RuleResolution,
    RuleScope,
)
from rules.engine import RulesEngine


class LayaIntelligenceContext(BaseModel):
    """
    The unified context packet provided to Member 1 (Laya) for task planning.
    Fully serializable, source-backed, and deterministic.
    """
    task: str
    project_id: Optional[str] = None
    cli_name: Optional[str] = None
    memory_context: ContextPacket
    applicable_rules: List[Rule] = Field(default_factory=list)
    rule_resolution: RuleResolution
    context_sources: List[str] = Field(default_factory=list)
    rule_explanations: List[str] = Field(default_factory=list)
    combined_laya_context: str = ""
    decision: str = "ALLOW"  # ALLOW | WARN | ASK | DENY
    metadata: Dict[str, Any] = Field(default_factory=dict)


def format_combined_laya_context(
    memory_context: ContextPacket,
    rule_resolution: RuleResolution,
) -> str:
    """
    Renders a clean, structured Markdown block formatted for Laya prompt planning.
    Includes retrieved project memory, applicable rules, and conflict decisions.
    """
    sections: List[str] = []

    # ── 1. PROJECT CONTEXT ────────────────────────────────────────────────────
    sections.append("### PROJECT CONTEXT\n")
    if memory_context.items:
        for idx, item in enumerate(memory_context.items, start=1):
            sections.append(
                f"[MEMORY {idx}]\n"
                f"Source: {item.source}\n"
                f"Type: {item.source_type}\n"
                f"Relevance: {item.relevance_score:.2f}\n\n"
                f"{item.snippet.strip()}\n"
            )
    else:
        sections.append("*(No relevant project memory found)*\n")

    # ── 2. APPLICABLE RULES ───────────────────────────────────────────────────
    sections.append("### APPLICABLE RULES\n")
    winning = rule_resolution.winning_rules
    if winning:
        mand = [r for r in winning if r.is_mandatory]
        glob = [r for r in winning if not r.is_mandatory and r.scope == RuleScope.GLOBAL]
        proj = [r for r in winning if not r.is_mandatory and r.scope == RuleScope.PROJECT]
        cli = [r for r in winning if not r.is_mandatory and r.scope == RuleScope.CLI]
        tsk = [r for r in winning if not r.is_mandatory and r.scope == RuleScope.TASK]

        if mand:
            sections.append("[MANDATORY]")
            for r in mand:
                sections.append(f"* {r.description}")
            sections.append("")
        if glob:
            sections.append("[GLOBAL]")
            for r in glob:
                sections.append(f"* {r.description}")
            sections.append("")
        if proj:
            sections.append("[PROJECT]")
            for r in proj:
                sections.append(f"* {r.description}")
            sections.append("")
        if cli:
            sections.append("[CLI]")
            for r in cli:
                sections.append(f"* {r.description}")
            sections.append("")
        if tsk:
            sections.append("[TASK]")
            for r in tsk:
                sections.append(f"* {r.description}")
            sections.append("")
    else:
        sections.append("*(No applicable engineering rules)*\n")

    # ── 3. RULE RESOLUTION ────────────────────────────────────────────────────
    sections.append("### RULE RESOLUTION\n")
    has_deny = any(r.effect == RuleEffect.DENY for r in winning)
    has_ask = any(r.effect == RuleEffect.ASK for r in winning)
    has_warn = any(r.effect == RuleEffect.WARN for r in winning)
    has_conflicts = bool(rule_resolution.conflicts)

    if has_deny:
        sections.append("Decision: DENY")
        for r in winning:
            if r.effect == RuleEffect.DENY:
                sections.append(f"Prohibition: {r.description}")
    elif has_ask:
        sections.append("Decision: ASK")
        for r in winning:
            if r.effect == RuleEffect.ASK:
                sections.append(f"Confirmation Required: {r.description}")
    elif has_warn:
        sections.append("Decision: WARN")
        for r in winning:
            if r.effect == RuleEffect.WARN:
                sections.append(f"Advisory: {r.description}")
    else:
        sections.append("Decision: ALLOW")

    if has_conflicts:
        sections.append("\nResolved Conflicts:")
        for c in rule_resolution.conflicts:
            sections.append(f"* {c.reason}")
    elif not has_deny:
        sections.append("\nNo blocking conflict detected.")

    return "\n".join(sections).strip()


class LayaIntelligenceService:
    """
    Unified Member 2 Facade coordinating memory retrieval and rules intelligence.
    Exposes stable APIs for Member 1 (Laya) and Member 3 (Dashboard).
    """

    def __init__(
        self,
        retrieval_service: Optional[RetrievalService] = None,
        rules_engine: Optional[RulesEngine] = None,
        storage: Optional[MemoryStorage] = None,
        ingestion_pipeline: Optional[IngestionPipeline] = None,
    ):
        self.retrieval_service = retrieval_service or RetrievalService(storage=storage)
        self.rules_engine = rules_engine or RulesEngine()
        self._storage = storage
        self._ingestion_pipeline = ingestion_pipeline

    # ── Core Unified Facade ───────────────────────────────────────────────────

    def build_intelligence_context(
        self,
        task: Union[str, Any],
        project_id: Optional[str] = None,
        cli_name: Optional[str] = None,
        task_rules: Optional[List[Rule]] = None,
        top_k: int = 5,
        min_score: float = 0.35,
        context_budget_tokens: int = 2000,
        task_metadata: Optional[Dict[str, Any]] = None,
    ) -> LayaIntelligenceContext:
        """
        Builds complete LayaIntelligenceContext combining project memory,
        applicable rules, deterministic conflict resolution, and formatted prompt text.
        """
        task_str = self._extract_task_text(task)
        meta: Dict[str, Any] = {
            "project_id": project_id,
            "cli_name": cli_name,
            "memory_status": "ok",
            "rules_status": "ok",
        }
        if task_metadata:
            meta.update(task_metadata)
        if hasattr(task, "as_dict") and callable(task.as_dict):
            meta.update(task.as_dict())

        # 1. Retrieve project memory
        try:
            memory_packet = self.retrieval_service.retrieve_context(
                task=task_str,
                project_id=project_id,
                top_k=top_k,
                min_score=min_score,
                context_budget_tokens=context_budget_tokens,
            )
        except Exception as e:
            meta["memory_status"] = "error"
            meta["memory_error"] = str(e)
            memory_packet = ContextPacket(
                task=task_str,
                items=[],
                assembled_prompt_text="",
                token_estimate=0,
                provenance_summary=[],
                retrieval_metadata={"error": str(e)},
            )

        # 2. Evaluate applicable rules & resolve conflicts
        try:
            applicable_rules = self.rules_engine.get_applicable_rules(
                task=task_str,
                project_id=project_id,
                cli_name=cli_name,
                task_metadata=meta,
                task_rules=task_rules,
            )
            rule_resolution = self.rules_engine.resolve_rules(
                task=task_str,
                project_id=project_id,
                cli_name=cli_name,
                task_metadata=meta,
                task_rules=task_rules,
            )
        except Exception as e:
            meta["rules_status"] = "error"
            meta["rules_error"] = str(e)
            applicable_rules = []
            rule_resolution = RuleResolution(
                task=task_str,
                applicable_rules=[],
                conflicts=[],
                winning_rules=[],
                suppressed_rules=[],
                explanation_trace=f"Rules evaluation failed: {e}",
                constraints_prompt_text="",
            )

        # 3. Determine overall decision
        winning = rule_resolution.winning_rules
        if any(r.effect == RuleEffect.DENY for r in winning):
            overall_decision = "DENY"
        elif any(r.effect == RuleEffect.ASK for r in winning):
            overall_decision = "ASK"
        elif any(r.effect == RuleEffect.WARN for r in winning):
            overall_decision = "WARN"
        else:
            overall_decision = "ALLOW"

        # 4. Extract provenance & explanations
        context_sources = [item.source for item in memory_packet.items]
        rule_explanations = [c.reason for c in rule_resolution.conflicts]
        if not rule_explanations and rule_resolution.explanation_trace:
            rule_explanations.append(rule_resolution.explanation_trace)

        # 5. Format combined Laya context text
        combined_text = format_combined_laya_context(
            memory_context=memory_packet,
            rule_resolution=rule_resolution,
        )

        return LayaIntelligenceContext(
            task=task_str,
            project_id=project_id,
            cli_name=cli_name,
            memory_context=memory_packet,
            applicable_rules=applicable_rules,
            rule_resolution=rule_resolution,
            context_sources=context_sources,
            rule_explanations=rule_explanations,
            combined_laya_context=combined_text,
            decision=overall_decision,
            metadata=meta,
        )

    # ── Stable Memory Subsystem APIs ──────────────────────────────────────────

    def store_memory(
        self,
        content: str,
        project_id: str,
        source_type: str = "doc",
        source_path: str = "unknown",
        title: Optional[str] = None,
        session_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IngestionResult:
        """Stores a document or code artifact in persistent memory via IngestionPipeline."""
        pipeline = self._ingestion_pipeline or IngestionPipeline(storage=self._get_storage())
        return pipeline.ingest(
            content=content,
            project_id=project_id,
            source_type=source_type,
            source_path=source_path,
            title=title,
            session_id=session_id,
            tags=tags,
            metadata=metadata,
        )

    def search_memory(
        self,
        query: str,
        project_id: Optional[str] = None,
        top_k: int = 5,
        min_score: float = 0.35,
        source_types: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        source_path: Optional[str] = None,
    ) -> List[MemorySearchResult]:
        """Performs raw ranked similarity search over memory chunks."""
        return self.retrieval_service.search_memory(
            query=query,
            project_id=project_id,
            top_k=top_k,
            min_score=min_score,
            source_types=source_types,
            session_id=session_id,
            source_path=source_path,
        )

    def retrieve_context(
        self,
        task: str,
        project_id: Optional[str] = None,
        top_k: int = 5,
        min_score: float = 0.35,
        context_budget_tokens: int = 2000,
    ) -> ContextPacket:
        """Retrieves and formats memory context into a prompt-bounded ContextPacket."""
        return self.retrieval_service.retrieve_context(
            task=task,
            project_id=project_id,
            top_k=top_k,
            min_score=min_score,
            context_budget_tokens=context_budget_tokens,
        )

    def delete_memory(self, record_id: str) -> bool:
        """Deletes a memory record and its associated chunks."""
        storage = self._get_storage()
        return storage.delete_record(record_id)

    # ── Stable Rules Subsystem APIs ───────────────────────────────────────────

    def create_rule(self, rule: Rule) -> Rule:
        """Creates and stores a new rule."""
        return self.rules_engine.create_rule(rule)

    def get_rule(self, rule_id: str) -> Optional[Rule]:
        """Retrieves a rule by ID."""
        return self.rules_engine.get_rule(rule_id)

    def update_rule(self, rule: Rule) -> Rule:
        """Updates an existing rule."""
        return self.rules_engine.update_rule(rule)

    def delete_rule(self, rule_id: str) -> bool:
        """Deletes a rule by ID."""
        return self.rules_engine.delete_rule(rule_id)

    def list_rules(
        self,
        scope: Optional[RuleScope] = None,
        project_id: Optional[str] = None,
    ) -> List[Rule]:
        """Lists active rules in storage."""
        return self.rules_engine.list_rules(scope=scope, project_id=project_id)

    def get_applicable_rules(
        self,
        task: Union[str, Any],
        project_id: Optional[str] = None,
        cli_name: Optional[str] = None,
        task_metadata: Optional[Dict[str, Any]] = None,
        task_rules: Optional[List[Rule]] = None,
    ) -> List[Rule]:
        """Queries which rules apply to a given task."""
        return self.rules_engine.get_applicable_rules(
            task=task,
            project_id=project_id,
            cli_name=cli_name,
            task_metadata=task_metadata,
            task_rules=task_rules,
        )

    def resolve_rules(
        self,
        task: Union[str, Any],
        project_id: Optional[str] = None,
        cli_name: Optional[str] = None,
        task_metadata: Optional[Dict[str, Any]] = None,
        task_rules: Optional[List[Rule]] = None,
    ) -> RuleResolution:
        """Resolves applicable rules into a deterministic RuleResolution."""
        return self.rules_engine.resolve_rules(
            task=task,
            project_id=project_id,
            cli_name=cli_name,
            task_metadata=task_metadata,
            task_rules=task_rules,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_storage(self) -> MemoryStorage:
        """Returns storage instance from retrieval service or constructor."""
        if self._storage:
            return self._storage
        return self.retrieval_service.storage

    @staticmethod
    def _extract_task_text(task: Union[str, Any]) -> str:
        """Extracts task string from str or StructuredTask object."""
        if isinstance(task, str):
            return task
        if hasattr(task, "task"):
            return str(task.task)
        return str(task)
