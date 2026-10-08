"""
Rule Validator — Member 2 (RAG + Rules)

Provides deterministic structural and semantic validation for Rule models
before they are stored, evaluated, or resolved.
"""

import re
from typing import List, Optional
from .models import Rule, RuleCondition, RuleEffect, RuleScope


class RuleValidationError(ValueError):
    """Raised when a rule definition fails structural or semantic validation."""
    pass


class RuleValidator:
    """
    Validates Rule instances for schema compliance, value boundaries,
    and valid regex/glob patterns.
    """

    ALLOWED_OPERATORS = {"contains", "equals", "starts_with", "regex", "glob", "in"}
    RULE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")

    @classmethod
    def validate_rule(cls, rule: Rule) -> None:
        """
        Validates all fields of a Rule. Raises RuleValidationError on failure.
        """
        if not isinstance(rule, Rule):
            raise RuleValidationError(f"Expected Rule instance, got {type(rule).__name__}")

        # 1. rule_id
        if not rule.rule_id or not isinstance(rule.rule_id, str):
            raise RuleValidationError("Rule must have a non-empty string 'rule_id'.")
        rule_id_clean = rule.rule_id.strip()
        if not cls.RULE_ID_PATTERN.match(rule_id_clean):
            raise RuleValidationError(
                f"Invalid rule_id '{rule.rule_id}'. Must contain only alphanumeric, hyphens, underscores, dots."
            )

        # 2. name
        if not rule.name or not isinstance(rule.name, str) or not rule.name.strip():
            raise RuleValidationError("Rule must have a non-empty string 'name'.")

        # 3. description
        if not isinstance(rule.description, str):
            raise RuleValidationError("Rule 'description' must be a string.")

        # 4. scope
        if not isinstance(rule.scope, RuleScope):
            raise RuleValidationError(f"Invalid scope '{rule.scope}'. Must be a RuleScope enum.")

        # 5. effect
        if not isinstance(rule.effect, RuleEffect):
            raise RuleValidationError(f"Invalid effect '{rule.effect}'. Must be a RuleEffect enum.")

        # 6. priority: 0 to 99
        if not isinstance(rule.priority, int) or rule.priority < 0 or rule.priority > 99:
            raise RuleValidationError(
                f"Invalid priority {rule.priority} for rule '{rule.rule_id}'. Must be an integer between 0 and 99."
            )

        # 7. target
        if not rule.target or not isinstance(rule.target, str) or not rule.target.strip():
            raise RuleValidationError(f"Rule '{rule.rule_id}' must have a non-empty 'target'.")

        # 8. version
        if not isinstance(rule.version, int) or rule.version < 1:
            raise RuleValidationError(
                f"Rule '{rule.rule_id}' version must be an integer >= 1 (got {rule.version})."
            )

        # 9. cli_filter
        if rule.cli_filter is not None:
            if not isinstance(rule.cli_filter, str) or not rule.cli_filter.strip():
                raise RuleValidationError(f"Rule '{rule.rule_id}' cli_filter must be a non-empty string or None.")

        # 10. project_id
        if rule.project_id is not None:
            if not isinstance(rule.project_id, str) or not rule.project_id.strip():
                raise RuleValidationError(f"Rule '{rule.rule_id}' project_id must be a non-empty string or None.")

        # 11. conditions
        if not isinstance(rule.conditions, list):
            raise RuleValidationError(f"Rule '{rule.rule_id}' conditions must be a list.")
        for idx, cond in enumerate(rule.conditions):
            cls.validate_condition(cond, rule.rule_id, idx)

    @classmethod
    def validate_condition(cls, condition: RuleCondition, rule_id: str, index: int) -> None:
        """Validates a single RuleCondition."""
        if not isinstance(condition, RuleCondition):
            raise RuleValidationError(
                f"Rule '{rule_id}' condition #{index} must be a RuleCondition instance."
            )
        if not condition.field_name or not condition.field_name.strip():
            raise RuleValidationError(
                f"Rule '{rule_id}' condition #{index} missing valid 'field_name'."
            )
        op = condition.operator.strip().lower()
        if op not in cls.ALLOWED_OPERATORS:
            raise RuleValidationError(
                f"Rule '{rule_id}' condition #{index} has unsupported operator '{condition.operator}'. "
                f"Allowed: {sorted(list(cls.ALLOWED_OPERATORS))}"
            )
        if condition.value is None or not isinstance(condition.value, str):
            raise RuleValidationError(
                f"Rule '{rule_id}' condition #{index} 'value' must be a string."
            )

        # Check regex validity
        if op == "regex":
            try:
                re.compile(condition.value)
            except re.error as e:
                raise RuleValidationError(
                    f"Rule '{rule_id}' condition #{index} invalid regex '{condition.value}': {e}"
                )
