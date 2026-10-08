"""
Rule Storage Subsystem — Member 2 (RAG + Rules)

Provides persistent, version-controlled rule repository operations.
Stores project rules in .cliverse/rules/ (git-tracked) and global
runtime rules in .envcore/rules/global/.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import yaml

from .models import Rule, RuleScope, current_iso_timestamp
from .parser import RuleParser
from .validator import RuleValidator, RuleValidationError


class RuleStore:
    """
    Persistent file-based repository for rules.
    Version-control friendly: writes human-readable YAML documents.
    """

    def __init__(
        self,
        project_rules_dir: Union[str, Path] = ".cliverse/rules",
        global_rules_dir: Union[str, Path] = ".envcore/rules/global",
    ):
        self.project_rules_dir = Path(project_rules_dir)
        self.global_rules_dir = Path(global_rules_dir)
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Creates rule storage directories if they do not exist."""
        self.project_rules_dir.mkdir(parents=True, exist_ok=True)
        self.global_rules_dir.mkdir(parents=True, exist_ok=True)

    def _get_path_for_rule(self, rule: Rule) -> Path:
        """Determines target filesystem path based on rule scope."""
        base_dir = self.global_rules_dir if rule.scope == RuleScope.GLOBAL else self.project_rules_dir
        return base_dir / f"{rule.rule_id}.yaml"

    def _find_rule_file(self, rule_id: str) -> Optional[Path]:
        """Locates rule file across project and global directories."""
        for base_dir in (self.project_rules_dir, self.global_rules_dir):
            yaml_path = base_dir / f"{rule_id}.yaml"
            if yaml_path.is_file():
                return yaml_path
            yml_path = base_dir / f"{rule_id}.yml"
            if yml_path.is_file():
                return yml_path
            json_path = base_dir / f"{rule_id}.json"
            if json_path.is_file():
                return json_path
        return None

    def create_rule(self, rule: Rule) -> Rule:
        """
        Persists a new rule. Raises ValueError if a rule with rule_id already exists.
        """
        RuleValidator.validate_rule(rule)
        existing = self._find_rule_file(rule.rule_id)
        if existing:
            raise ValueError(f"Rule with id '{rule.rule_id}' already exists at {existing}.")

        target_path = self._get_path_for_rule(rule)
        self._write_rule_file(rule, target_path)
        return rule

    def get_rule(self, rule_id: str) -> Optional[Rule]:
        """Retrieves a rule by its rule_id."""
        path = self._find_rule_file(rule_id)
        if not path:
            return None
        rules = RuleParser.parse_file(path)
        return rules[0] if rules else None

    def update_rule(self, rule: Rule) -> Rule:
        """
        Updates an existing rule, incrementing its version counter and timestamp.
        """
        RuleValidator.validate_rule(rule)
        path = self._find_rule_file(rule.rule_id)
        if not path:
            raise ValueError(f"Rule with id '{rule.rule_id}' does not exist.")

        # Read existing to preserve/increment version
        existing_rules = RuleParser.parse_file(path)
        existing = existing_rules[0] if existing_rules else None
        current_version = existing.version if existing else rule.version

        updated_rule = rule.model_copy(
            update={
                "version": current_version + 1,
                "updated_at": current_iso_timestamp(),
            }
        )
        # If scope changed, path might change
        target_path = self._get_path_for_rule(updated_rule)
        if target_path != path and path.is_file():
            path.unlink(missing_ok=True)

        self._write_rule_file(updated_rule, target_path)
        return updated_rule

    def delete_rule(self, rule_id: str) -> bool:
        """Deletes a rule by its rule_id. Returns True if deleted, False if not found."""
        path = self._find_rule_file(rule_id)
        if not path:
            return False
        try:
            path.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def list_rules(
        self,
        scope: Optional[RuleScope] = None,
        project_id: Optional[str] = None,
    ) -> List[Rule]:
        """
        Lists all rules in storage, optionally filtered by scope or project_id.
        """
        rules_map: Dict[str, Rule] = {}

        # Scan global then project (project can override if duplicate ID)
        for base_dir in (self.global_rules_dir, self.project_rules_dir):
            if not base_dir.is_dir():
                continue
            for item in sorted(base_dir.glob("*")):
                if item.suffix.lower() in (".yaml", ".yml", ".json") and item.is_file():
                    try:
                        parsed = RuleParser.parse_file(item)
                        for r in parsed:
                            rules_map[r.rule_id] = r
                    except Exception:
                        continue

        results = list(rules_map.values())

        if scope is not None:
            results = [r for r in results if r.scope == scope]

        if project_id is not None:
            results = [
                r for r in results
                if r.scope == RuleScope.GLOBAL or r.project_id is None or r.project_id == project_id
            ]

        # Deterministic sort
        results.sort(key=lambda r: (r.scope.weight, r.priority, r.rule_id), reverse=True)
        return results

    def find_candidate_rules(
        self,
        project_id: Optional[str] = None,
        cli_name: Optional[str] = None,
    ) -> List[Rule]:
        """
        Returns all candidate rules that might apply to the given project and CLI context.
        """
        all_rules = self.list_rules()
        candidates: List[Rule] = []

        for r in all_rules:
            if not r.enabled:
                continue

            # Scope / project filtering
            if r.scope == RuleScope.PROJECT:
                expected_proj = r.project_id or r.scope_id
                if expected_proj and project_id and expected_proj != project_id:
                    continue

            # CLI filtering
            expected_cli = r.cli_filter or (r.scope_id if r.scope == RuleScope.CLI else None)
            if expected_cli and cli_name and expected_cli.lower() != cli_name.lower():
                continue

            candidates.append(r)

        return candidates

    @staticmethod
    def _write_rule_file(rule: Rule, path: Path) -> None:
        """Serializes rule to clean YAML format."""
        path.parent.mkdir(parents=True, exist_ok=True)
        raw_dict = rule.model_dump(mode="json")
        # Write clean yaml
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(raw_dict, f, sort_keys=False, default_flow_style=False)
