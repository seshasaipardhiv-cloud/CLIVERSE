"""
Rules Intelligence Engine Facade — Member 2 (RAG + Rules)

Public service facade for developer and project rules intelligence.
Consumed by Member 1 (Laya) for prompt planning and Member 3 for dashboard display.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .applicability import RuleApplicabilityChecker
from .models import ApplicableRule, Rule, RuleResolution, RuleScope
from .parser import RuleParser
from .resolver import RuleResolver
from .storage import RuleStore


class RulesEngine:
    """
    Unified service for rule management, applicability matching,
    deterministic conflict resolution, and constraint prompt generation.
    """

    def __init__(
        self,
        storage: Optional[RuleStore] = None,
        project_rules_dir: Union[str, Path] = ".cliverse/rules",
        global_rules_dir: Union[str, Path] = ".envcore/rules/global",
    ):
        self.storage = storage or RuleStore(
            project_rules_dir=project_rules_dir,
            global_rules_dir=global_rules_dir,
        )

    # ── CRUD Operations ────────────────────────────────────────────────────────

    def create_rule(self, rule: Rule) -> Rule:
        """Persists a new rule definition."""
        return self.storage.create_rule(rule)

    def get_rule(self, rule_id: str) -> Optional[Rule]:
        """Retrieves a rule by ID."""
        return self.storage.get_rule(rule_id)

    def update_rule(self, rule: Rule) -> Rule:
        """Updates an existing rule and increments its version."""
        return self.storage.update_rule(rule)

    def delete_rule(self, rule_id: str) -> bool:
        """Deletes a rule by ID."""
        return self.storage.delete_rule(rule_id)

    def list_rules(
        self,
        scope: Optional[RuleScope] = None,
        project_id: Optional[str] = None,
    ) -> List[Rule]:
        """Lists active stored rules, optionally filtered by scope or project."""
        return self.storage.list_rules(scope=scope, project_id=project_id)

    # ── File / Directory Ingestion ─────────────────────────────────────────────

    def load_rules_from_file(self, file_path: Union[str, Path]) -> List[Rule]:
        """Parses rules from a file and persists them in storage."""
        rules = RuleParser.parse_file(file_path)
        persisted: List[Rule] = []
        for r in rules:
            existing = self.storage.get_rule(r.rule_id)
            if existing:
                persisted.append(self.storage.update_rule(r))
            else:
                persisted.append(self.storage.create_rule(r))
        return persisted

    def load_rules_from_directory(self, dir_path: Union[str, Path]) -> List[Rule]:
        """Parses all rule files in a directory and stores them."""
        path = Path(dir_path)
        if not path.is_dir():
            return []
        all_loaded: List[Rule] = []
        for p in sorted(path.glob("*")):
            if p.suffix.lower() in (".yaml", ".yml", ".json") and p.is_file():
                try:
                    loaded = self.load_rules_from_file(p)
                    all_loaded.extend(loaded)
                except Exception:
                    continue
        return all_loaded

    # ── Evaluation & Resolution (Member 1 / Laya Interface) ───────────────────

    def get_applicable_rules(
        self,
        task: Union[str, Any],
        project_id: Optional[str] = None,
        cli_name: Optional[str] = None,
        task_metadata: Optional[Dict[str, Any]] = None,
        task_rules: Optional[List[Rule]] = None,
    ) -> List[Rule]:
        """
        Determines which stored and task-level rules apply to the given task context.

        Args:
            task: Task string or StructuredTask object.
            project_id: Target project identifier for project isolation.
            cli_name: Active CLI adapter name (e.g. 'claude-cli', 'aider').
            task_metadata: Optional context metadata (files, command, etc.).
            task_rules: Ephemeral rules defined dynamically for this task.

        Returns:
            List of applicable Rule models sorted by effective priority.
        """
        task_str = self._extract_task_text(task)
        meta = dict(task_metadata or {})
        if hasattr(task, "as_dict") and callable(task.as_dict):
            meta.update(task.as_dict())

        # Collect candidate pool from storage
        candidates = self.storage.find_candidate_rules(project_id=project_id, cli_name=cli_name)

        # Merge ephemeral task-level rules
        if task_rules:
            candidates.extend(task_rules)

        # Evaluate applicability
        applicable_entries = RuleApplicabilityChecker.filter_applicable(
            rules=candidates,
            task=task_str,
            project_id=project_id,
            cli_name=cli_name,
            task_metadata=meta,
        )

        # Sort by effective priority descending
        applicable_entries.sort(key=lambda a: a.effective_priority, reverse=True)
        return [entry.rule for entry in applicable_entries]

    def resolve_rules(
        self,
        task: Union[str, Any],
        project_id: Optional[str] = None,
        cli_name: Optional[str] = None,
        task_metadata: Optional[Dict[str, Any]] = None,
        task_rules: Optional[List[Rule]] = None,
        applicable_rules: Optional[List[Rule]] = None,
    ) -> RuleResolution:
        """
        Full resolution pipeline:
          1. Evaluates applicability across stored and task-level rules (if not pre-evaluated)
          2. Detects conflicts across matching target domains
          3. Applies mandatory safety overrides and deterministic precedence
          4. Generates an explainable decision trace and constraints prompt block

        Returns:
            RuleResolution containing winning rules, conflicts, trace, and prompt.
        """
        task_str = self._extract_task_text(task)
        meta = dict(task_metadata or {})
        if hasattr(task, "as_dict") and callable(task.as_dict):
            meta.update(task.as_dict())

        if applicable_rules is not None:
            applicable = applicable_rules
        else:
            applicable = self.get_applicable_rules(
                task=task_str,
                project_id=project_id,
                cli_name=cli_name,
                task_metadata=meta,
                task_rules=task_rules,
            )

        return RuleResolver.resolve(
            task=task_str,
            applicable_rules=applicable,
            metadata={"project_id": project_id, "cli_name": cli_name},
        )

    @staticmethod
    def _extract_task_text(task: Union[str, Any]) -> str:
        """Extracts plain string task from string or StructuredTask object."""
        if isinstance(task, str):
            return task
        if hasattr(task, "task"):
            return str(task.task)
        return str(task)
