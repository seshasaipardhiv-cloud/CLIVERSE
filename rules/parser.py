"""
Rule Parser — Member 2 (RAG + Rules)

Provides safe, deterministic loading and normalization of rule definitions
from YAML, JSON, strings, dictionaries, and files.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Union
import yaml

from .models import Rule, RuleCondition, RuleEffect, RuleScope
from .validator import RuleValidator, RuleValidationError


class RuleParseError(ValueError):
    """Raised when a rule definition cannot be parsed or normalized."""
    pass


class RuleParser:
    """
    Parses and normalizes rule definitions from YAML/JSON files, strings,
    and Python mappings into validated Rule instances.
    """

    @classmethod
    def parse_file(cls, file_path: Union[str, Path]) -> List[Rule]:
        """
        Parses all rules from a YAML or JSON file.
        """
        path = Path(file_path)
        if not path.is_file():
            raise RuleParseError(f"Rule file does not exist: {file_path}")

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            raise RuleParseError(f"Failed to read rule file '{file_path}': {e}") from e

        return cls.parse_string(content, source_label=str(path))

    @classmethod
    def parse_string(cls, content: str, source_label: str = "<string>") -> List[Rule]:
        """
        Parses YAML or JSON string content into a list of Rule instances.
        """
        if not content or not content.strip():
            return []

        try:
            # YAML 1.2 is a superset of JSON; safe_load handles both YAML and JSON
            data = yaml.safe_load(content)
        except Exception as e:
            raise RuleParseError(f"Malformed YAML/JSON syntax in {source_label}: {e}") from e

        if data is None:
            return []

        return cls.parse_raw_data(data, source_label=source_label)

    @classmethod
    def parse_raw_data(cls, data: Any, source_label: str = "<data>") -> List[Rule]:
        """
        Converts raw deserialized data (list or dict) into a list of validated Rule models.
        """
        raw_rules: List[Dict[str, Any]] = []

        if isinstance(data, list):
            for idx, item in enumerate(data):
                if not isinstance(item, dict):
                    raise RuleParseError(f"{source_label}: Item #{idx} in rules list must be a mapping/dict.")
                raw_rules.append(item)
        elif isinstance(data, dict):
            if "rules" in data and isinstance(data["rules"], list):
                for idx, item in enumerate(data["rules"]):
                    if not isinstance(item, dict):
                        raise RuleParseError(f"{source_label}: 'rules' item #{idx} must be a mapping/dict.")
                    raw_rules.append(item)
            else:
                raw_rules.append(data)
        else:
            raise RuleParseError(f"{source_label}: Root element must be a rule mapping or list of mappings.")

        rules: List[Rule] = []
        seen_rule_ids = set()

        for idx, item in enumerate(raw_rules):
            try:
                rule = cls.normalize_and_build(item)
                RuleValidator.validate_rule(rule)
            except (RuleValidationError, ValueError, TypeError) as e:
                rule_id_hint = item.get("id") or item.get("rule_id") or f"index {idx}"
                raise RuleParseError(f"Error in {source_label} for rule '{rule_id_hint}': {e}") from e

            if rule.rule_id in seen_rule_ids:
                raise RuleParseError(
                    f"{source_label}: Duplicate rule_id '{rule.rule_id}' detected in rule definitions."
                )
            seen_rule_ids.add(rule.rule_id)
            rules.append(rule)

        return rules

    @classmethod
    def normalize_and_build(cls, item: Dict[str, Any]) -> Rule:
        """
        Normalizes aliases, enums, and conditions, then instantiates a Rule.
        """
        data = dict(item)

        # 1. Map 'id' -> 'rule_id'
        if "id" in data and "rule_id" not in data:
            data["rule_id"] = str(data.pop("id"))

        # 2. Normalize scope
        if "scope" in data and isinstance(data["scope"], str):
            scope_str = data["scope"].strip().upper()
            try:
                data["scope"] = RuleScope(scope_str)
            except ValueError:
                valid_scopes = [s.value for s in RuleScope]
                raise RuleParseError(f"Invalid scope '{data['scope']}'. Allowed: {valid_scopes}")

        # 3. Normalize effect
        if "effect" in data and isinstance(data["effect"], str):
            effect_str = data["effect"].strip().upper()
            try:
                data["effect"] = RuleEffect(effect_str)
            except ValueError:
                valid_effects = [e.value for e in RuleEffect]
                raise RuleParseError(f"Invalid effect '{data['effect']}'. Allowed: {valid_effects}")

        # 4. Normalize conditions
        if "conditions" in data and data["conditions"] is not None:
            raw_conds = data["conditions"]
            normalized_conds: List[RuleCondition] = []

            if isinstance(raw_conds, list):
                for c in raw_conds:
                    if isinstance(c, RuleCondition):
                        normalized_conds.append(c)
                    elif isinstance(c, dict):
                        normalized_conds.append(cls._normalize_condition_dict(c))
                    else:
                        raise RuleParseError(f"Condition entry must be a mapping, got {type(c).__name__}")
            elif isinstance(raw_conds, dict):
                # Format like: conditions: { paths: ["config/production/**"] } or { task: "..." }
                normalized_conds.extend(cls._expand_shorthand_conditions(raw_conds))
            else:
                raise RuleParseError(f"Conditions must be a list or mapping, got {type(raw_conds).__name__}")

            data["conditions"] = normalized_conds

        # 5. Clean string fields
        for field in ("name", "description", "target", "cli_filter", "project_id", "scope_id"):
            if field in data and isinstance(data[field], str):
                data[field] = data[field].strip()

        return Rule(**data)

    @staticmethod
    def _normalize_condition_dict(c: Dict[str, Any]) -> RuleCondition:
        """Normalizes a single condition dictionary."""
        field = c.get("field_name") or c.get("field") or "task"
        operator = c.get("operator") or c.get("op") or "contains"
        value = str(c.get("value", ""))
        return RuleCondition(field_name=field, operator=operator, value=value)

    @classmethod
    def _expand_shorthand_conditions(cls, cond_map: Dict[str, Any]) -> List[RuleCondition]:
        """
        Expands shorthand dictionary conditions, such as:
          paths: ["config/production/**"]
          task: "build"
        """
        result: List[RuleCondition] = []
        for key, val in cond_map.items():
            field_name = "path" if key in ("paths", "path", "file", "files") else key
            default_op = "glob" if field_name in ("path", "file") else "contains"

            if isinstance(val, list):
                for subval in val:
                    result.append(RuleCondition(field_name=field_name, operator=default_op, value=str(subval)))
            else:
                result.append(RuleCondition(field_name=field_name, operator=default_op, value=str(val)))
        return result
