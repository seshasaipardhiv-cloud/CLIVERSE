"""
CLIVERSE Rules Intelligence Subsystem — Member 2

Provides hierarchical rule parsing, multi-scope validation, priority matrix
evaluation, mandatory safety guardrails, conflict detection, deterministic
resolution, and prompt constraints assembly for Member 1 (Laya) and Member 3 (Dashboard).
"""

from .applicability import RuleApplicabilityChecker
from .engine import RulesEngine
from .models import (
    ApplicableRule,
    Rule,
    RuleCondition,
    RuleConflict,
    RuleEffect,
    RuleResolution,
    RuleScope,
)
from .parser import RuleParseError, RuleParser
from .resolver import RuleResolver
from .storage import RuleStore
from .validator import RuleValidationError, RuleValidator

__all__ = [
    "Rule",
    "RuleScope",
    "RuleEffect",
    "RuleCondition",
    "ApplicableRule",
    "RuleConflict",
    "RuleResolution",
    "RuleParser",
    "RuleParseError",
    "RuleValidator",
    "RuleValidationError",
    "RuleApplicabilityChecker",
    "RuleResolver",
    "RuleStore",
    "RulesEngine",
]
