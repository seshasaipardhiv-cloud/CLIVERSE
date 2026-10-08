"""
Comprehensive Unit & Integration Test Suite for Stage 4: Rules Intelligence Engine
===================================================================================
Member 2 (RAG + Rules) — CLIVERSE

Validates:
  - Model validation & boundaries
  - Parser (YAML, JSON, shorthand conditions, malformed rejection, duplicate detection)
  - Applicability & project/CLI isolation
  - Priority & scope precedence matrix
  - Mandatory guardrails (fail-safe protection)
  - Conflict detection & deterministic resolution
  - Explanation trace & constraints prompt assembly
  - Storage CRUD & versioning (.cliverse/rules vs .envcore/rules)
  - Determinism / property repeatability
  - Realistic end-to-end scenarios
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from rules.applicability import RuleApplicabilityChecker
from rules.engine import RulesEngine
from rules.models import (
    ApplicableRule,
    Rule,
    RuleCondition,
    RuleConflict,
    RuleEffect,
    RuleResolution,
    RuleScope,
)
from rules.parser import RuleParseError, RuleParser
from rules.resolver import RuleResolver
from rules.storage import RuleStore
from rules.validator import RuleValidationError, RuleValidator


class TestRulesStage4(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cliverse_rules_test_")
        self.project_rules_dir = Path(self.temp_dir) / ".cliverse" / "rules"
        self.global_rules_dir = Path(self.temp_dir) / ".envcore" / "rules" / "global"
        self.store = RuleStore(
            project_rules_dir=self.project_rules_dir,
            global_rules_dir=self.global_rules_dir,
        )
        self.engine = RulesEngine(storage=self.store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ── 1. MODEL VALIDATION ───────────────────────────────────────────────────

    def test_valid_rule_instantiation(self):
        rule = Rule(
            rule_id="valid-rule-01",
            name="Valid Rule",
            scope=RuleScope.PROJECT,
            description="A valid engineering rule.",
            target="database",
            effect=RuleEffect.ENFORCE,
            priority=75,
            is_mandatory=False,
            project_id="proj-alpha",
        )
        RuleValidator.validate_rule(rule)
        self.assertEqual(rule.effective_priority, 275)  # 200 (PROJECT) + 75
        self.assertEqual(rule.scope.specificity, 2)
        self.assertEqual(rule.version, 1)

    def test_invalid_rule_id_rejected(self):
        rule = Rule(
            rule_id="invalid id with spaces!",
            name="Test Rule",
            scope=RuleScope.GLOBAL,
            description="Testing invalid ID.",
        )
        with self.assertRaises(RuleValidationError):
            RuleValidator.validate_rule(rule)

    def test_invalid_priority_rejected(self):
        # Priority must be between 0 and 99
        with self.assertRaises(Exception):
            Rule(
                rule_id="high-pri",
                name="Test",
                scope=RuleScope.GLOBAL,
                description="Test",
                priority=100,  # exceeds 99
            )

    def test_invalid_condition_operator_rejected(self):
        rule = Rule(
            rule_id="cond-rule",
            name="Condition Rule",
            description="Test",
            conditions=[
                RuleCondition(field_name="task", operator="unsupported_op", value="val")
            ],
        )
        with self.assertRaises(RuleValidationError):
            RuleValidator.validate_rule(rule)

    def test_invalid_condition_regex_rejected(self):
        rule = Rule(
            rule_id="regex-rule",
            name="Regex Rule",
            description="Test",
            conditions=[
                RuleCondition(field_name="task", operator="regex", value="[unclosed")
            ],
        )
        with self.assertRaises(RuleValidationError):
            RuleValidator.validate_rule(rule)

    # ── 2. PARSER ─────────────────────────────────────────────────────────────

    def test_parse_valid_yaml_single_rule(self):
        yaml_content = """
id: protect-prod-env
name: Protect Production Config
scope: project
target: production_config
effect: deny
priority: 90
is_mandatory: true
description: Production configuration must not be modified.
conditions:
  paths:
    - "config/production/**"
"""
        rules = RuleParser.parse_string(yaml_content)
        self.assertEqual(len(rules), 1)
        r = rules[0]
        self.assertEqual(r.rule_id, "protect-prod-env")
        self.assertEqual(r.scope, RuleScope.PROJECT)
        self.assertEqual(r.effect, RuleEffect.DENY)
        self.assertEqual(r.priority, 90)
        self.assertTrue(r.is_mandatory)
        self.assertEqual(len(r.conditions), 1)
        self.assertEqual(r.conditions[0].operator, "glob")
        self.assertEqual(r.conditions[0].value, "config/production/**")

    def test_parse_valid_json_multiple_rules(self):
        json_content = """
{
  "rules": [
    {
      "id": "rule-one",
      "name": "Rule One",
      "scope": "GLOBAL",
      "description": "Global rule one",
      "target": "security",
      "effect": "DENY",
      "priority": 80
    },
    {
      "id": "rule-two",
      "name": "Rule Two",
      "scope": "PROJECT",
      "description": "Project rule two",
      "target": "database",
      "effect": "ENFORCE",
      "priority": 50
    }
  ]
}
"""
        rules = RuleParser.parse_string(json_content)
        self.assertEqual(len(rules), 2)
        self.assertEqual(rules[0].rule_id, "rule-one")
        self.assertEqual(rules[1].rule_id, "rule-two")

    def test_parse_rejects_duplicate_rule_ids(self):
        yaml_content = """
- id: duplicate-id
  name: First
  description: One
- id: duplicate-id
  name: Second
  description: Two
"""
        with self.assertRaises(RuleParseError):
            RuleParser.parse_string(yaml_content)

    def test_parse_rejects_malformed_syntax(self):
        bad_yaml = "id: unclosed quote: 'abc\n  foo: bar"
        with self.assertRaises(RuleParseError):
            RuleParser.parse_string(bad_yaml)

    def test_parse_from_file(self):
        file_path = Path(self.temp_dir) / "test_rules.yaml"
        file_path.write_text(
            """
id: file-rule
name: From File
scope: CLI
cli_filter: claude-cli
description: Ask before running bash
effect: ask
priority: 60
""",
            encoding="utf-8",
        )
        rules = RuleParser.parse_file(file_path)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].rule_id, "file-rule")
        self.assertEqual(rules[0].effect, RuleEffect.ASK)
        self.assertEqual(rules[0].cli_filter, "claude-cli")

    def test_parse_yaml_quoted_scalar_and_escaped_characters(self):
        """Verifies quoted scalars with quotes, slashes, and escaped characters parse accurately."""
        yaml_content = """
id: "escape-rule"
name: "Rule with \\"Quotes\\" and \\n newlines"
scope: "project"
target: "security"
effect: "deny"
description: "Block path: \\"C:\\\\Users\\\\admin\\\\secrets.txt\\""
priority: 75
"""
        rules = RuleParser.parse_string(yaml_content)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].rule_id, "escape-rule")
        self.assertIn("Quotes", rules[0].name)
        self.assertIn("secrets.txt", rules[0].description)

    def test_parse_yaml_nested_mapping_and_list(self):
        """Verifies nested mapping for conditions and list of paths."""
        yaml_content = """
id: nested-cond-rule
name: Nested Conditions
scope: project
target: filesystem
effect: deny
priority: 50
description: Block production writes
conditions:
  - field: path
    op: glob
    value: "prod/**"
  - field: task
    op: contains
    value: "delete"
"""
        rules = RuleParser.parse_string(yaml_content)
        self.assertEqual(len(rules), 1)
        self.assertEqual(len(rules[0].conditions), 2)
        self.assertEqual(rules[0].conditions[0].operator, "glob")
        self.assertEqual(rules[0].conditions[1].operator, "contains")

    def test_parse_yaml_multiline_literal_string(self):
        """Verifies multiline '|' literal string preservation."""
        yaml_content = """
id: multiline-rule
name: Multiline Rule
scope: global
target: audit
effect: warn
priority: 20
description: |
  Line 1 of detailed instruction.
  Line 2 of detailed instruction.
  Line 3 of detailed instruction.
"""
        rules = RuleParser.parse_string(yaml_content)
        self.assertEqual(len(rules), 1)
        self.assertIn("Line 1", rules[0].description)
        self.assertIn("Line 2", rules[0].description)
        self.assertIn("Line 3", rules[0].description)

    def test_parse_yaml_folded_string(self):
        """Verifies folded '>' string formatting."""
        yaml_content = """
id: folded-rule
name: Folded Rule
scope: global
target: documentation
effect: warn
priority: 15
description: >
  This is a very long instruction that is wrapped
  across multiple lines in the YAML source but folds
  into a single coherent line.
"""
        rules = RuleParser.parse_string(yaml_content)
        self.assertEqual(len(rules), 1)
        self.assertIn("This is a very long instruction", rules[0].description)

    def test_parse_yaml_invalid_rule_structure_rejected(self):
        """Verifies invalid rule types (e.g. integer or non-dict list items) are rejected."""
        yaml_content = """
- 12345
- "not a mapping"
"""
        with self.assertRaises(RuleParseError):
            RuleParser.parse_string(yaml_content)

    def test_parse_stdlib_json_without_yaml_dependency(self):
        """Verifies standard library JSON parses cleanly even when PyYAML is unavailable."""
        import json
        import rules.parser as parser_mod
        orig_yaml = parser_mod.yaml
        try:
            parser_mod.yaml = None  # simulate missing pyyaml
            json_text = json.dumps({
                "id": "json-no-pyyaml",
                "name": "JSON Stdlib",
                "scope": "GLOBAL",
                "target": "security",
                "effect": "ALLOW",
                "description": "Standard library JSON works without PyYAML",
            })
            parsed = RuleParser.parse_string(json_text)
            self.assertEqual(len(parsed), 1)
            self.assertEqual(parsed[0].rule_id, "json-no-pyyaml")
        finally:
            parser_mod.yaml = orig_yaml

    def test_pyyaml_unavailable_raises_actionable_import_error(self):
        """Verifies attempting to parse YAML when PyYAML is missing raises a clear actionable error."""
        import rules.parser as parser_mod
        orig_yaml = parser_mod.yaml
        try:
            parser_mod.yaml = None  # simulate missing pyyaml
            yaml_text = "id: needs-pyyaml\nname: Test\nscope: project\neffect: allow\ntarget: gen\ndescription: Test"
            with self.assertRaises(ImportError) as ctx:
                RuleParser.parse_string(yaml_text)
            self.assertIn("pip install pyyaml", str(ctx.exception))
        finally:
            parser_mod.yaml = orig_yaml

    def test_parse_yaml_comments_unicode_type_coercion_and_empty_doc(self):
        """Verifies comments, Unicode, type coercion, and empty documents parse as specified."""
        # 1. Empty document
        self.assertEqual(RuleParser.parse_string(""), [])
        self.assertEqual(RuleParser.parse_string("   \n\t  "), [])
        self.assertEqual(RuleParser.parse_string("---\n# Just comments\n"), [])

        # 2. YAML with comments and Unicode
        yaml_content = """
# Header comment explaining the rule
id: unicode-rule # inline comment
name: "Règle de sécurité et clés API"
scope: project
target: "sécurité"
effect: deny
priority: 85
description: "Vérifier l'accès sécurisé et bloquer les fuites de clés."
"""
        rules = RuleParser.parse_string(yaml_content)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].rule_id, "unicode-rule")
        self.assertIn("Règle", rules[0].name)
        self.assertEqual(rules[0].target, "sécurité")
        self.assertEqual(rules[0].priority, 85)

        # 3. Malformed JSON raises RuleParseError
        with self.assertRaises(RuleParseError):
            RuleParser.parse_string("{ 'bad': json, invalid }")


    # ── 3. APPLICABILITY & ISOLATION ──────────────────────────────────────────

    def test_global_rule_applies_everywhere(self):
        rule = Rule(
            rule_id="global-secrets",
            name="No Secrets",
            scope=RuleScope.GLOBAL,
            description="Never expose secrets",
            target="security",
        )
        is_app, _ = RuleApplicabilityChecker.evaluate(rule, task="Any task", project_id="proj-a")
        self.assertTrue(is_app)
        is_app, _ = RuleApplicabilityChecker.evaluate(rule, task="Any task", project_id="proj-b")
        self.assertTrue(is_app)

    def test_project_isolation_strictly_enforced(self):
        rule = Rule(
            rule_id="proj-rule",
            name="Project Rule",
            scope=RuleScope.PROJECT,
            project_id="project-alpha",
            description="Use PostgreSQL",
            target="database",
        )
        # Should match project-alpha
        is_app, _ = RuleApplicabilityChecker.evaluate(rule, task="Add feature", project_id="project-alpha")
        self.assertTrue(is_app)

        # Must NEVER match project-beta
        is_app, reason = RuleApplicabilityChecker.evaluate(rule, task="Add feature", project_id="project-beta")
        self.assertFalse(is_app)
        self.assertIn("does not match", reason)

        # Must reject if no project specified
        is_app, _ = RuleApplicabilityChecker.evaluate(rule, task="Add feature", project_id=None)
        self.assertFalse(is_app)

    def test_cli_filtering_strictly_enforced(self):
        rule = Rule(
            rule_id="cli-rule",
            name="Aider CLI Rule",
            scope=RuleScope.CLI,
            cli_filter="aider",
            description="Format commits with conventional commits",
            target="git",
        )
        # Matches aider
        is_app, _ = RuleApplicabilityChecker.evaluate(rule, task="Commit changes", cli_name="aider")
        self.assertTrue(is_app)

        # Rejects claude-cli
        is_app, reason = RuleApplicabilityChecker.evaluate(rule, task="Commit changes", cli_name="claude-cli")
        self.assertFalse(is_app)
        self.assertIn("does not match", reason)

    def test_disabled_rule_never_applies(self):
        rule = Rule(
            rule_id="disabled-rule",
            name="Disabled Rule",
            enabled=False,
            description="Disabled",
        )
        is_app, reason = RuleApplicabilityChecker.evaluate(rule, task="Any task")
        self.assertFalse(is_app)
        self.assertIn("disabled", reason)

    def test_condition_matching_path_glob(self):
        rule = Rule(
            rule_id="prod-guard",
            name="Protect Production",
            scope=RuleScope.PROJECT,
            description="Deny edits to production",
            target="production_config",
            effect=RuleEffect.DENY,
            conditions=[RuleCondition(field_name="path", operator="glob", value="config/production/**")],
        )
        # Match when metadata has path in config/production
        is_app, _ = RuleApplicabilityChecker.evaluate(
            rule, task="Edit settings", task_metadata={"path": "config/production/database.yaml"}
        )
        self.assertTrue(is_app)

        # Does not match when path is in dev
        is_app, _ = RuleApplicabilityChecker.evaluate(
            rule, task="Edit settings", task_metadata={"path": "config/development/database.yaml"}
        )
        self.assertFalse(is_app)

    # ── 4. PRIORITY & SCOPE PRECEDENCE ────────────────────────────────────────

    def test_scope_precedence_hierarchy(self):
        # TASK (400) > CLI (300) > PROJECT (200) > GLOBAL (100)
        global_r = Rule(rule_id="g", name="G", scope=RuleScope.GLOBAL, priority=50, description="G")
        proj_r = Rule(rule_id="p", name="P", scope=RuleScope.PROJECT, priority=50, description="P")
        cli_r = Rule(rule_id="c", name="C", scope=RuleScope.CLI, priority=50, description="C")
        task_r = Rule(rule_id="t", name="T", scope=RuleScope.TASK, priority=50, description="T")

        self.assertEqual(global_r.effective_priority, 150)
        self.assertEqual(proj_r.effective_priority, 250)
        self.assertEqual(cli_r.effective_priority, 350)
        self.assertEqual(task_r.effective_priority, 450)

        self.assertGreater(task_r.effective_priority, cli_r.effective_priority)
        self.assertGreater(cli_r.effective_priority, proj_r.effective_priority)
        self.assertGreater(proj_r.effective_priority, global_r.effective_priority)

    def test_numeric_priority_within_same_scope(self):
        r_low = Rule(rule_id="r1", name="Low", scope=RuleScope.PROJECT, priority=10, description="Low")
        r_high = Rule(rule_id="r2", name="High", scope=RuleScope.PROJECT, priority=90, description="High")

        self.assertGreater(r_high.effective_priority, r_low.effective_priority)

    # ── 5. CONFLICT DETECTION & RESOLUTION ─────────────────────────────────────

    def test_same_target_opposing_effects_conflict(self):
        r_allow = Rule(
            rule_id="allow-rule",
            name="Allow Package Install",
            scope=RuleScope.TASK,
            target="packages",
            effect=RuleEffect.ALLOW,
            description="Install packages automatically",
        )
        r_deny = Rule(
            rule_id="deny-rule",
            name="Deny Package Install",
            scope=RuleScope.PROJECT,
            target="packages",
            effect=RuleEffect.DENY,
            description="Never install packages automatically",
        )
        resolution = RuleResolver.resolve(task="Install lodash", applicable_rules=[r_allow, r_deny])
        self.assertEqual(len(resolution.conflicts), 1)
        self.assertEqual(resolution.conflicts[0].target, "packages")
        self.assertEqual(resolution.conflicts[0].winning_rule_id, "allow-rule")
        self.assertEqual(resolution.conflicts[0].suppressed_rule_id, "deny-rule")

    def test_different_targets_do_not_conflict(self):
        r_db = Rule(
            rule_id="use-postgres",
            name="Postgres",
            scope=RuleScope.PROJECT,
            target="database",
            effect=RuleEffect.ENFORCE,
            description="Use PostgreSQL",
        )
        r_lang = Rule(
            rule_id="use-ts",
            name="TypeScript",
            scope=RuleScope.PROJECT,
            target="language",
            effect=RuleEffect.ENFORCE,
            description="Use TypeScript",
        )
        resolution = RuleResolver.resolve(task="Build app", applicable_rules=[r_db, r_lang])
        self.assertEqual(len(resolution.conflicts), 0)
        self.assertEqual(len(resolution.winning_rules), 2)

    # ── 6. MANDATORY GUARDRAILS ───────────────────────────────────────────────

    def test_mandatory_global_deny_cannot_be_overridden_by_task_allow(self):
        global_mandatory_deny = Rule(
            rule_id="global-no-secrets",
            name="Never Expose Secrets",
            scope=RuleScope.GLOBAL,
            target="security",
            effect=RuleEffect.DENY,
            priority=90,
            is_mandatory=True,
            description="Never expose secrets or print environment variables.",
        )
        task_allow = Rule(
            rule_id="task-print-env",
            name="Print Environment Variables",
            scope=RuleScope.TASK,
            target="security",
            effect=RuleEffect.ALLOW,
            priority=99,
            is_mandatory=False,
            description="Print all environment variables for debugging.",
        )

        resolution = RuleResolver.resolve(
            task="Debug environment",
            applicable_rules=[global_mandatory_deny, task_allow],
        )

        # Mandatory GLOBAL DENY must win over TASK ALLOW
        self.assertEqual(len(resolution.winning_rules), 1)
        self.assertEqual(resolution.winning_rules[0].rule_id, "global-no-secrets")
        self.assertEqual(len(resolution.suppressed_rules), 1)
        self.assertEqual(resolution.suppressed_rules[0].rule_id, "task-print-env")

        # Conflict reason must explicitly explain mandatory override
        self.assertIn("Mandatory GLOBAL rule 'global-no-secrets'", resolution.conflicts[0].reason)
        self.assertIn("cannot be overridden", resolution.conflicts[0].reason)

    def test_mandatory_project_deny_cannot_be_overridden_by_task_allow(self):
        project_mandatory_deny = Rule(
            rule_id="protect-prod",
            name="Protect Production",
            scope=RuleScope.PROJECT,
            target="production_config",
            effect=RuleEffect.DENY,
            priority=80,
            is_mandatory=True,
            description="Production files cannot be altered.",
        )
        task_allow = Rule(
            rule_id="task-override-prod",
            name="Task Override",
            scope=RuleScope.TASK,
            target="production_config",
            effect=RuleEffect.ALLOW,
            priority=90,
            is_mandatory=False,
            description="Allow modifying production config for emergency hotfix.",
        )

        resolution = RuleResolver.resolve(
            task="Emergency hotfix",
            applicable_rules=[project_mandatory_deny, task_allow],
        )

        self.assertEqual(resolution.winning_rules[0].rule_id, "protect-prod")
        self.assertEqual(resolution.suppressed_rules[0].rule_id, "task-override-prod")

    # ── 7. EXPLANATION TRACE & CONSTRAINTS PROMPT ─────────────────────────────

    def test_explanation_trace_and_constraints_prompt_generation(self):
        r1 = Rule(
            rule_id="r-db",
            name="Use Postgres",
            scope=RuleScope.PROJECT,
            target="database",
            effect=RuleEffect.ENFORCE,
            description="Use PostgreSQL for all persistent relational storage.",
        )
        r2 = Rule(
            rule_id="r-mand",
            name="No Secrets",
            scope=RuleScope.GLOBAL,
            target="security",
            effect=RuleEffect.DENY,
            is_mandatory=True,
            description="Never commit private API keys.",
        )

        resolution = RuleResolver.resolve(task="Setup database and auth", applicable_rules=[r1, r2])

        # Explanation trace verification
        self.assertIn("# Rule Resolution Trace", resolution.explanation_trace)
        self.assertIn("r-db", resolution.explanation_trace)
        self.assertIn("r-mand", resolution.explanation_trace)
        self.assertIn("Active Winning Rules", resolution.explanation_trace)

        # Constraints prompt text for Laya verification
        self.assertIn("### Applicable Rules", resolution.constraints_prompt_text)
        self.assertIn("[MANDATORY]", resolution.constraints_prompt_text)
        self.assertIn("Never commit private API keys.", resolution.constraints_prompt_text)
        self.assertIn("[PROJECT]", resolution.constraints_prompt_text)
        self.assertIn("Use PostgreSQL for all persistent relational storage.", resolution.constraints_prompt_text)

    # ── 8. STORAGE PERSISTENCE & VERSIONING ───────────────────────────────────

    def test_storage_create_read_update_delete_lifecycle(self):
        rule = Rule(
            rule_id="storage-test-rule",
            name="Storage Test",
            scope=RuleScope.PROJECT,
            description="Rule for testing storage lifecycle.",
            target="testing",
            version=1,
        )

        # 1. Create
        created = self.store.create_rule(rule)
        self.assertEqual(created.rule_id, "storage-test-rule")
        self.assertTrue((self.project_rules_dir / "storage-test-rule.yaml").exists())

        # 2. Read
        fetched = self.store.get_rule("storage-test-rule")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Storage Test")
        self.assertEqual(fetched.version, 1)

        # 3. Update (increments version)
        updated_input = fetched.model_copy(update={"name": "Storage Test Renamed"})
        updated = self.store.update_rule(updated_input)
        self.assertEqual(updated.version, 2)
        self.assertEqual(updated.name, "Storage Test Renamed")
        self.assertIsNotNone(updated.updated_at)

        # 4. List
        listed = self.store.list_rules()
        self.assertEqual(len(listed), 1)

        # 5. Delete
        deleted = self.store.delete_rule("storage-test-rule")
        self.assertTrue(deleted)
        self.assertIsNone(self.store.get_rule("storage-test-rule"))

    def test_global_rules_saved_in_global_directory(self):
        global_rule = Rule(
            rule_id="global-rule-01",
            name="Global Storage Test",
            scope=RuleScope.GLOBAL,
            description="Stored in global rules dir.",
        )
        self.store.create_rule(global_rule)
        self.assertTrue((self.global_rules_dir / "global-rule-01.yaml").exists())

    # ── 9. DETERMINISM & PROPERTY TEST ────────────────────────────────────────

    def test_resolver_determinism_across_multiple_runs(self):
        """Same rules and task must produce identical outputs on repeated runs."""
        r1 = Rule(rule_id="r1", name="Rule One", scope=RuleScope.PROJECT, target="db", description="DB 1")
        r2 = Rule(rule_id="r2", name="Rule Two", scope=RuleScope.PROJECT, target="db", description="DB 2")
        r3 = Rule(rule_id="r3", name="Rule Three", scope=RuleScope.GLOBAL, is_mandatory=True, description="G3")

        first_res = RuleResolver.resolve("Build task", [r1, r2, r3])
        for _ in range(10):
            next_res = RuleResolver.resolve("Build task", [r1, r2, r3])
            self.assertEqual(first_res.winning_rules, next_res.winning_rules)
            self.assertEqual(first_res.conflicts, next_res.conflicts)
            self.assertEqual(first_res.explanation_trace, next_res.explanation_trace)
            self.assertEqual(first_res.constraints_prompt_text, next_res.constraints_prompt_text)

    # ── 10. REALISTIC END-TO-END SCENARIOS ────────────────────────────────────

    def test_scenario_1_all_relevant_rules_returned(self):
        """
        GLOBAL: Never expose secrets.
        PROJECT: Use PostgreSQL.
        CLI: Ask before installing packages.
        TASK: Add JWT authentication.
        Expected: All rules applicable and returned.
        """
        self.engine.create_rule(
            Rule(
                rule_id="s1-secrets",
                name="No Secrets",
                scope=RuleScope.GLOBAL,
                target="security",
                effect=RuleEffect.DENY,
                is_mandatory=True,
                description="Never expose secrets or API keys.",
            )
        )
        self.engine.create_rule(
            Rule(
                rule_id="s1-postgres",
                name="Use Postgres",
                scope=RuleScope.PROJECT,
                project_id="app-service",
                target="database",
                effect=RuleEffect.ENFORCE,
                description="Use PostgreSQL for data persistence.",
            )
        )
        self.engine.create_rule(
            Rule(
                rule_id="s1-packages",
                name="Ask Packages",
                scope=RuleScope.CLI,
                cli_filter="claude-cli",
                target="packages",
                effect=RuleEffect.ASK,
                description="Ask user confirmation before installing packages.",
            )
        )

        applicable = self.engine.get_applicable_rules(
            task="Add JWT authentication",
            project_id="app-service",
            cli_name="claude-cli",
        )
        self.assertEqual(len(applicable), 3)
        rule_ids = {r.rule_id for r in applicable}
        self.assertEqual(rule_ids, {"s1-secrets", "s1-postgres", "s1-packages"})

    def test_scenario_2_mandatory_deny_overrides_task_allow(self):
        """
        GLOBAL: Never modify production config (DENY, mandatory=true)
        TASK: Modify production config for debugging (ALLOW)
        Expected: DENY resolution; task rule suppressed.
        """
        self.engine.create_rule(
            Rule(
                rule_id="s2-prod-guard",
                name="Protect Production",
                scope=RuleScope.GLOBAL,
                target="production_config",
                effect=RuleEffect.DENY,
                is_mandatory=True,
                description="Never alter production configuration files.",
            )
        )
        task_rule = Rule(
            rule_id="s2-task-override",
            name="Debug Production",
            scope=RuleScope.TASK,
            target="production_config",
            effect=RuleEffect.ALLOW,
            priority=99,
            description="Temporarily modify production configuration for debugging.",
        )

        resolution = self.engine.resolve_rules(
            task="Debug production configuration",
            task_rules=[task_rule],
        )

        self.assertEqual(len(resolution.winning_rules), 1)
        self.assertEqual(resolution.winning_rules[0].rule_id, "s2-prod-guard")
        self.assertEqual(resolution.winning_rules[0].effect, RuleEffect.DENY)
        self.assertEqual(len(resolution.conflicts), 1)
        self.assertEqual(resolution.conflicts[0].winning_rule_id, "s2-prod-guard")

    def test_scenario_3_project_postgres_vs_task_mongo_conflict(self):
        """
        PROJECT: Use PostgreSQL.
        TASK: Use MongoDB for this feature.
        Expected: Conflict detected; Task rule wins by scope precedence; explainable trace.
        """
        self.engine.create_rule(
            Rule(
                rule_id="s3-proj-pg",
                name="Use Postgres",
                scope=RuleScope.PROJECT,
                project_id="cliverse-app",
                target="database",
                effect=RuleEffect.ENFORCE,
                description="Use PostgreSQL for application storage.",
            )
        )
        task_mongo = Rule(
            rule_id="s3-task-mongo",
            name="Use MongoDB",
            scope=RuleScope.TASK,
            target="database",
            effect=RuleEffect.ENFORCE,
            description="Use MongoDB for this specific analytics feature.",
        )

        resolution = self.engine.resolve_rules(
            task="Implement analytics storage",
            project_id="cliverse-app",
            task_rules=[task_mongo],
        )

        self.assertEqual(len(resolution.conflicts), 1)
        self.assertEqual(resolution.conflicts[0].target, "database")
        self.assertEqual(resolution.conflicts[0].winning_rule_id, "s3-task-mongo")
        self.assertEqual(resolution.conflicts[0].suppressed_rule_id, "s3-proj-pg")
        self.assertIn("Higher-scope TASK rule", resolution.conflicts[0].reason)

    def test_scenario_4_rewrite_entire_backend(self):
        """
        PROJECT: Follow existing architecture.
        TASK: Rewrite entire backend in Go.
        Expected: Conflict detected; explainable resolution trace generated.
        """
        self.engine.create_rule(
            Rule(
                rule_id="s4-arch-std",
                name="Follow Architecture",
                scope=RuleScope.PROJECT,
                project_id="proj-core",
                target="architecture",
                effect=RuleEffect.ENFORCE,
                description="Maintain existing Python architecture.",
            )
        )
        task_rewrite = Rule(
            rule_id="s4-task-rewrite",
            name="Rewrite in Go",
            scope=RuleScope.TASK,
            target="architecture",
            effect=RuleEffect.ENFORCE,
            description="Rewrite entire backend in Go.",
        )

        resolution = self.engine.resolve_rules(
            task="Rewrite backend",
            project_id="proj-core",
            task_rules=[task_rewrite],
        )

        self.assertEqual(len(resolution.conflicts), 1)
        self.assertEqual(resolution.conflicts[0].target, "architecture")
        self.assertTrue(len(resolution.explanation_trace) > 50)
        self.assertIn("s4-task-rewrite", resolution.constraints_prompt_text)


if __name__ == "__main__":
    unittest.main()
