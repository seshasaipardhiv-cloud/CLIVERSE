"""
Public Facade for Member 2 (Memory/RAG + Rules Intelligence) — CLIVERSE

Primary integration entry point consumed directly by Member 1 (Laya Engine)
and Member 3 (Dashboard). Exposes LayaIntelligenceService and LayaIntelligenceContext.
"""

from memory.intelligence import (
    LayaIntelligenceContext,
    LayaIntelligenceService,
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
    "format_combined_laya_context",
]
