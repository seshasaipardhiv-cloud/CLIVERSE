"""
Rules Data Models — Member 2 (RAG + Rules)

Defines Pydantic v2 schemas for hierarchical rules, scopes, effects,
conflicts, and deterministic resolution outputs consumed by Member 1 (Laya).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


def current_iso_timestamp() -> str:
    """Returns current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


class RuleScope(str, Enum):
    """
    Hierarchical scope tiers.
    Precedence: TASK (400) > CLI (300) > PROJECT (200) > GLOBAL (100)
    """
    GLOBAL = "GLOBAL"
    PROJECT = "PROJECT"
    CLI = "CLI"
    TASK = "TASK"

    @property
    def weight(self) -> int:
        weights = {
            RuleScope.GLOBAL: 100,
            RuleScope.PROJECT: 200,
            RuleScope.CLI: 300,
            RuleScope.TASK: 400,
        }
        return weights[self]

    @property
    def specificity(self) -> int:
        """Ordinal specificity score: GLOBAL=1, PROJECT=2, CLI=3, TASK=4."""
        ranks = {
            RuleScope.GLOBAL: 1,
            RuleScope.PROJECT: 2,
            RuleScope.CLI: 3,
            RuleScope.TASK: 4,
        }
        return ranks[self]


class RuleEffect(str, Enum):
    """
    Action or restriction enforced by a rule.

    Canonical Semantics:
      - ALLOW: Explicitly permits a matching action/condition.
      - DENY: Hard prohibition; matching action/condition is forbidden.
      - WARN: Allows continuation but produces an advisory warning.
      - ENFORCE: Mandatory positive requirement (e.g. 'Use TypeScript').
      - REQUIRE: Synonym/equivalent to ENFORCE (prerequisite required).
      - ASK: Requires interactive human confirmation before continuation.
    """
    ALLOW = "ALLOW"
    DENY = "DENY"
    WARN = "WARN"
    ENFORCE = "ENFORCE"
    REQUIRE = "REQUIRE"
    ASK = "ASK"

    @property
    def severity_rank(self) -> int:
        """
        Safety ordering for conflict tie-breaking (more restrictive wins):
        DENY (6) > ASK (5) > REQUIRE (4) / ENFORCE (4) > WARN (2) > ALLOW (1)
        """
        ranks = {
            RuleEffect.DENY: 6,
            RuleEffect.ASK: 5,
            RuleEffect.REQUIRE: 4,
            RuleEffect.ENFORCE: 4,
            RuleEffect.WARN: 2,
            RuleEffect.ALLOW: 1,
        }
        return ranks.get(self, 0)


class RuleCondition(BaseModel):
    """
    Granular criteria matching for conditional rule activation.
    """
    field_name: str = "task"  # "task" | "file" | "path" | "command" | "cli"
    operator: str = "contains"  # "contains" | "regex" | "equals" | "starts_with" | "glob" | "in"
    value: str


class Rule(BaseModel):
    """
    Individual engineering constraint or preference rule.
    Fully serializable, deterministic, and persistent.
    """
    rule_id: str = Field(default_factory=lambda: f"rule-{uuid4().hex[:8]}")
    name: str
    scope: RuleScope = RuleScope.PROJECT
    scope_id: Optional[str] = None  # e.g. project_id, cli_name, task_id, or 'global'
    description: str
    target: str = "general"  # Domain/target e.g., "language", "database", "security", "git"
    effect: RuleEffect = RuleEffect.ENFORCE
    priority: int = Field(default=50, ge=0, le=99)
    is_mandatory: bool = False  # If True, cannot be overridden by higher-scope rules
    cli_filter: Optional[str] = None  # Applies only to this CLI if set (e.g. 'claude-cli')
    project_id: Optional[str] = None  # Isolates rule to a specific project
    enabled: bool = True
    version: int = 1
    conditions: List[RuleCondition] = Field(default_factory=list)
    created_at: str = Field(default_factory=current_iso_timestamp)
    updated_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def effective_priority(self) -> int:
        """
        Calculates effective priority score combining scope weight and rule priority.
        Scope weight dominates (100-400), with priority (0-99) providing fine-tuning.
        """
        return self.scope.weight + self.priority


class ApplicableRule(BaseModel):
    """
    A rule evaluated as applicable to a given task or CLI context.
    """
    rule: Rule
    effective_priority: int
    matched_reason: str


class RuleConflict(BaseModel):
    """
    Details of a detected contradiction between two rules and the winning resolution.
    """
    winning_rule_id: str
    suppressed_rule_id: str
    target: str = "general"
    reason: str


class RuleResolution(BaseModel):
    """
    The deterministic resolution result containing winning active rules
    and an explainable decision trace for Laya and the Dashboard.
    """
    task: str
    applicable_rules: List[Rule] = Field(default_factory=list)
    conflicts: List[RuleConflict] = Field(default_factory=list)
    winning_rules: List[Rule] = Field(default_factory=list)
    suppressed_rules: List[Rule] = Field(default_factory=list)
    explanation_trace: str = ""
    constraints_prompt_text: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
