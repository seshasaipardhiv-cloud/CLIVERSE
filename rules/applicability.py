"""
Rule Applicability Engine — Member 2 (RAG + Rules)

Evaluates whether individual rules match a given task, project, CLI adapter,
and task context metadata.
"""

import fnmatch
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from .models import ApplicableRule, Rule, RuleCondition, RuleScope


class RuleApplicabilityChecker:
    """
    Evaluates applicability of rules against an execution context.
    Ensures strict project isolation and CLI targeting.
    """

    @classmethod
    def evaluate(
        cls,
        rule: Rule,
        task: str,
        project_id: Optional[str] = None,
        cli_name: Optional[str] = None,
        task_metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """
        Determines whether a Rule applies to the given execution context.

        Returns:
            Tuple of (is_applicable: bool, reason: str)
        """
        # 1. Enabled check
        if not rule.enabled:
            return False, "Rule is disabled."

        meta = task_metadata or {}

        # 2. Project isolation & Scope check
        if rule.scope == RuleScope.PROJECT:
            expected_proj = rule.project_id or rule.scope_id
            if expected_proj:
                if project_id is None:
                    return False, f"Project rule '{rule.rule_id}' requires project '{expected_proj}', but none was specified."
                if expected_proj != project_id:
                    return False, f"Project rule '{rule.rule_id}' for project '{expected_proj}' does not match '{project_id}'."

        if rule.project_id is not None and rule.scope != RuleScope.PROJECT:
            if project_id is None or rule.project_id != project_id:
                return False, f"Rule '{rule.rule_id}' isolated to project '{rule.project_id}' does not match '{project_id}'."

        # 3. CLI targeting
        if rule.scope == RuleScope.CLI:
            expected_cli = rule.cli_filter or rule.scope_id
            if expected_cli:
                if cli_name is None:
                    return False, f"CLI rule '{rule.rule_id}' requires CLI '{expected_cli}', but none was specified."
                if expected_cli.lower() != cli_name.lower():
                    return False, f"CLI rule '{rule.rule_id}' for '{expected_cli}' does not match active CLI '{cli_name}'."

        if rule.cli_filter is not None and rule.scope != RuleScope.CLI:
            if cli_name is None or rule.cli_filter.lower() != cli_name.lower():
                return False, f"Rule '{rule.rule_id}' cli_filter '{rule.cli_filter}' does not match '{cli_name}'."

        # 4. Conditions evaluation
        if not rule.conditions:
            return True, f"Applicable by {rule.scope.value} scope."

        for idx, cond in enumerate(rule.conditions):
            matched, cond_reason = cls._evaluate_condition(cond, task, meta)
            if not matched:
                return False, f"Condition #{idx} ({cond.field_name} {cond.operator} {cond.value}) failed: {cond_reason}"

        return True, "All scope criteria and conditions satisfied."

    @classmethod
    def _evaluate_condition(
        cls,
        cond: RuleCondition,
        task: str,
        metadata: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Evaluates a single condition against task string or metadata."""
        field = cond.field_name.strip().lower()

        # Extract values to test against
        target_values: List[str] = []
        if field == "task":
            target_values.append(task)
        elif field in ("file", "path", "paths", "files"):
            if "path" in metadata:
                target_values.append(str(metadata["path"]))
            if "file" in metadata:
                target_values.append(str(metadata["file"]))
            if "paths" in metadata and isinstance(metadata["paths"], (list, tuple)):
                target_values.extend(str(p) for p in metadata["paths"])
            if "files" in metadata and isinstance(metadata["files"], (list, tuple)):
                target_values.extend(str(f) for f in metadata["files"])
            # Fallback: inspect task string if no path in metadata
            if not target_values:
                target_values.append(task)
        elif field in ("command", "cmd"):
            if "command" in metadata:
                target_values.append(str(metadata["command"]))
            elif "cmd" in metadata:
                target_values.append(str(metadata["cmd"]))
            else:
                target_values.append(task)
        elif field in metadata:
            val = metadata[field]
            if isinstance(val, (list, tuple)):
                target_values.extend(str(v) for v in val)
            else:
                target_values.append(str(val))
        else:
            # Fallback to searching in task string
            target_values.append(task)

        op = cond.operator.strip().lower()
        pattern = cond.value

        for t_val in target_values:
            if cls._match_operator(op, pattern, t_val):
                return True, "Matched"

        return False, f"Value '{target_values}' did not match pattern '{pattern}' with operator '{op}'"

    @staticmethod
    def _match_operator(op: str, pattern: str, target: str) -> bool:
        """Executes operator comparison between pattern and target string."""
        p_lower = pattern.lower()
        t_lower = target.lower()

        if op == "contains":
            return p_lower in t_lower
        elif op == "equals":
            return p_lower == t_lower
        elif op == "starts_with":
            return t_lower.startswith(p_lower)
        elif op == "regex":
            try:
                return bool(re.search(pattern, target, re.IGNORECASE))
            except re.error:
                return False
        elif op == "glob":
            # Match glob pattern (e.g. config/production/** or *.ts)
            # Standard fnmatch handles * and ?, also check lowercased
            return fnmatch.fnmatch(target, pattern) or fnmatch.fnmatch(t_lower, p_lower)
        elif op == "in":
            return p_lower in t_lower
        return False

    @classmethod
    def filter_applicable(
        cls,
        rules: List[Rule],
        task: str,
        project_id: Optional[str] = None,
        cli_name: Optional[str] = None,
        task_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[ApplicableRule]:
        """
        Filters a list of rules down to those that apply, returning ApplicableRule objects.
        """
        applicable: List[ApplicableRule] = []
        for rule in rules:
            is_app, reason = cls.evaluate(
                rule=rule,
                task=task,
                project_id=project_id,
                cli_name=cli_name,
                task_metadata=task_metadata,
            )
            if is_app:
                applicable.append(
                    ApplicableRule(
                        rule=rule,
                        effective_priority=rule.effective_priority,
                        matched_reason=reason,
                    )
                )
        return applicable
