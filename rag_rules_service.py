"""
Public Facade for Member 2 (Memory/RAG + Rules Intelligence) — CLIVERSE

Canonical Member 2 integration entry point consumed directly by Member 1 (Laya Engine)
and Member 3 (Dashboard). Exposes LayaIntelligenceService, LayaIntelligenceContext,
SubsystemStatus, RuleDecision, and TaskLike.

Architecture note:
  rule_decision represents developer/project rule resolution only.
  It is NOT the final security or execution authorization (which is governed by Member 4).
"""

from memory.adapter import CliverseMemoryProviderAdapter
from memory.intelligence import (
    LayaIntelligenceContext,
    LayaIntelligenceService,
    RuleDecision,
    SubsystemStatus,
    TaskLike,
    format_combined_laya_context,
)

# Canonical aliases for backward compatibility and architectural alignment
RAGRulesService = LayaIntelligenceService
IntelligenceService = LayaIntelligenceService

__all__ = [
    "LayaIntelligenceContext",
    "LayaIntelligenceService",
    "RAGRulesService",
    "IntelligenceService",
    "CliverseMemoryProviderAdapter",
    "SubsystemStatus",
    "RuleDecision",
    "TaskLike",
    "format_combined_laya_context",
]
