"""
Stage 5: Unified Laya Intelligence Integration Test Suite
==========================================================
Member 2 (RAG + Rules) — CLIVERSE

Validates the complete intelligence contract provided to Member 1 (Laya):
  - Unified LayaIntelligenceContext generation
  - Coordinated Memory + Rules assembly without merging internals
  - Scenario 1: FastAPI + PostgreSQL + Auth full integration
  - Scenario 2: Scope conflict resolution propagation
  - Scenario 3: Mandatory safety guardrail enforcement in unified context
  - Scenario 4: Empty memory state safety
  - Scenario 5: Empty rules state safety
  - Scenario 6: Strict multi-project isolation
  - Scenario 7: CLI adapter targeting
  - Scenario 8: Absolute determinism across repeated executions
  - Scenario 9: Full Pydantic v2 JSON serialization for Member 3 Dashboard
  - Scenario 10: Subsystem error resilience and metadata reporting
  - Scenario 11: Architectural layering adherence
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from memory.embeddings.local_engine import LocalBaselineEmbeddingProvider
from memory.ingestion.pipeline import IngestionPipeline
from memory.intelligence import (
    LayaIntelligenceContext,
    LayaIntelligenceService,
    format_combined_laya_context,
)
from memory.models import ContextPacket
from memory.retrieval.search import RetrievalService
from memory.storage.sqlite_store import SQLiteMemoryStorage
from rules.engine import RulesEngine
from rules.models import (
    Rule,
    RuleEffect,
    RuleResolution,
    RuleScope,
)
from rules.storage import RuleStore


class TestLayaIntelligenceIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cliverse_stage5_")
        self.db_path = Path(self.temp_dir) / "test_stage5.db"
        self.storage = SQLiteMemoryStorage(db_path=str(self.db_path))
        self.embedding_provider = LocalBaselineEmbeddingProvider(dimension=64)
        self.ingestion = IngestionPipeline(
            storage=self.storage,
            embedding_provider=self.embedding_provider,
        )
        self.retrieval = RetrievalService(
            storage=self.storage,
            embedding_provider=self.embedding_provider,
        )
        self.project_rules_dir = Path(self.temp_dir) / ".cliverse" / "rules"
        self.global_rules_dir = Path(self.temp_dir) / ".envcore" / "rules" / "global"
        self.rule_store = RuleStore(
            project_rules_dir=self.project_rules_dir,
            global_rules_dir=self.global_rules_dir,
        )
        self.rules_engine = RulesEngine(storage=self.rule_store)

        self.service = LayaIntelligenceService(
            retrieval_service=self.retrieval,
            rules_engine=self.rules_engine,
            storage=self.storage,
            ingestion_pipeline=self.ingestion,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ── SCENARIO 1: FULL UNIFIED INTEGRATION ──────────────────────────────────

    def test_scenario_1_fastapi_postgres_auth_full_integration(self):
        # 1. Ingest project knowledge
        self.service.store_memory(
            content="FastAPI backend architecture with PostgreSQL for persistent relational data.",
            project_id="proj-fastapi",
            source_type="doc",
            source_path="docs/architecture.md",
        )
        self.service.store_memory(
            content="Authentication uses JWT tokens signed with RS256 algorithm.",
            project_id="proj-fastapi",
            source_type="decision",
            source_path="decisions/auth.md",
        )

        # 2. Store project and CLI rules
        self.service.create_rule(
            Rule(
                rule_id="r-use-postgres",
                name="Use PostgreSQL",
                scope=RuleScope.PROJECT,
                project_id="proj-fastapi",
                target="database",
                effect=RuleEffect.ENFORCE,
                description="Use PostgreSQL for all database operations.",
            )
        )
        self.service.create_rule(
            Rule(
                rule_id="r-ask-packages",
                name="Ask Before Packages",
                scope=RuleScope.CLI,
                cli_filter="claude-cli",
                target="packages",
                effect=RuleEffect.ASK,
                description="Ask confirmation before installing new packages.",
            )
        )

        # 3. Build unified context for Laya
        intel = self.service.build_intelligence_context(
            task="Add JWT authentication and update database schema",
            project_id="proj-fastapi",
            cli_name="claude-cli",
            min_score=0.1,
        )

        # Verify unified context fields
        self.assertIsInstance(intel, LayaIntelligenceContext)
        self.assertEqual(intel.task, "Add JWT authentication and update database schema")
        self.assertEqual(intel.project_id, "proj-fastapi")
        self.assertEqual(intel.cli_name, "claude-cli")

        # Memory verification
        self.assertTrue(len(intel.memory_context.items) >= 1)
        self.assertTrue(any("docs/architecture.md" in s or "decisions/auth.md" in s for s in intel.context_sources))

        # Rules verification
        self.assertEqual(len(intel.applicable_rules), 2)
        self.assertEqual(len(intel.rule_resolution.winning_rules), 2)
        self.assertEqual(intel.decision, "ASK")  # ASK effect takes priority over ENFORCE

        # Combined prompt text verification
        self.assertIn("### PROJECT CONTEXT", intel.combined_laya_context)
        self.assertIn("[MEMORY 1]", intel.combined_laya_context)
        self.assertIn("### APPLICABLE RULES", intel.combined_laya_context)
        self.assertIn("[PROJECT]", intel.combined_laya_context)
        self.assertIn("[CLI]", intel.combined_laya_context)
        self.assertIn("### RULE RESOLUTION", intel.combined_laya_context)
        self.assertIn("Decision: ASK", intel.combined_laya_context)

    # ── SCENARIO 2: CONFLICT DETECTION & RESOLUTION ───────────────────────────

    def test_scenario_2_conflict_detection_and_task_override(self):
        # Project rule: Use PostgreSQL
        self.service.create_rule(
            Rule(
                rule_id="rule-proj-pg",
                name="Use Postgres",
                scope=RuleScope.PROJECT,
                project_id="proj-conflict",
                target="database",
                effect=RuleEffect.ENFORCE,
                description="Use PostgreSQL for all services.",
            )
        )

        # Ephemeral task rule: Use MongoDB for this task
        task_mongo = Rule(
            rule_id="rule-task-mongo",
            name="Use MongoDB",
            scope=RuleScope.TASK,
            target="database",
            effect=RuleEffect.ENFORCE,
            description="Use MongoDB for this analytics task.",
        )

        intel = self.service.build_intelligence_context(
            task="Build analytics module",
            project_id="proj-conflict",
            task_rules=[task_mongo],
        )

        # Conflict must be detected and documented
        self.assertEqual(len(intel.rule_resolution.conflicts), 1)
        conflict = intel.rule_resolution.conflicts[0]
        self.assertEqual(conflict.winning_rule_id, "rule-task-mongo")
        self.assertEqual(conflict.suppressed_rule_id, "rule-proj-pg")
        self.assertEqual(conflict.target, "database")

        # Task rule wins by scope precedence
        self.assertEqual(len(intel.rule_resolution.winning_rules), 1)
        self.assertEqual(intel.rule_resolution.winning_rules[0].rule_id, "rule-task-mongo")

        # Explanations present
        self.assertTrue(len(intel.rule_explanations) >= 1)
        self.assertIn("Higher-scope TASK rule", intel.rule_explanations[0])
        self.assertIn("Resolved Conflicts:", intel.combined_laya_context)

    # ── SCENARIO 3: MANDATORY PROTECTION GUARDRAIL ────────────────────────────

    def test_scenario_3_mandatory_protection_cannot_be_overridden(self):
        # Global mandatory rule: Never expose secrets
        self.service.create_rule(
            Rule(
                rule_id="mand-no-secrets",
                name="Never Expose Secrets",
                scope=RuleScope.GLOBAL,
                target="security",
                effect=RuleEffect.DENY,
                is_mandatory=True,
                description="Never expose secrets or print environment variables.",
            )
        )

        # Task rule attempts to ALLOW printing environment variables
        task_allow = Rule(
            rule_id="task-debug-env",
            name="Debug Env",
            scope=RuleScope.TASK,
            target="security",
            effect=RuleEffect.ALLOW,
            priority=99,
            description="Print all environment variables.",
        )

        intel = self.service.build_intelligence_context(
            task="Print environment variables for debugging",
            project_id="any-project",
            task_rules=[task_allow],
        )

        # Mandatory rule must win; task rule suppressed
        self.assertEqual(intel.decision, "DENY")
        self.assertEqual(intel.rule_resolution.winning_rules[0].rule_id, "mand-no-secrets")
        self.assertEqual(intel.rule_resolution.suppressed_rules[0].rule_id, "task-debug-env")
        self.assertIn("Mandatory GLOBAL rule", intel.rule_resolution.conflicts[0].reason)
        self.assertIn("cannot be overridden", intel.rule_resolution.conflicts[0].reason)
        self.assertIn("Decision: DENY", intel.combined_laya_context)

    # ── SCENARIO 4: EMPTY MEMORY STATE ────────────────────────────────────────

    def test_scenario_4_empty_memory_state_safe(self):
        # Rules exist, but zero memories indexed
        self.service.create_rule(
            Rule(
                rule_id="r-std",
                name="Standard Rule",
                scope=RuleScope.GLOBAL,
                description="Follow standard conventions.",
            )
        )

        intel = self.service.build_intelligence_context(
            task="Build feature in empty project",
            project_id="proj-empty-memory",
        )

        self.assertEqual(len(intel.memory_context.items), 0)
        self.assertEqual(len(intel.context_sources), 0)
        self.assertEqual(len(intel.applicable_rules), 1)
        self.assertIn("*(No relevant project memory found)*", intel.combined_laya_context)
        self.assertIn("Follow standard conventions.", intel.combined_laya_context)

    # ── SCENARIO 5: EMPTY RULES STATE ─────────────────────────────────────────

    def test_scenario_5_empty_rules_state_safe(self):
        # Memory exists, but zero rules apply
        self.service.store_memory(
            content="Documentation about microservices architecture.",
            project_id="proj-no-rules",
            source_type="doc",
            source_path="arch.md",
        )

        intel = self.service.build_intelligence_context(
            task="microservices architecture",
            project_id="proj-no-rules",
            min_score=0.1,
        )

        self.assertTrue(len(intel.memory_context.items) >= 1)
        self.assertEqual(len(intel.applicable_rules), 0)
        self.assertEqual(len(intel.rule_resolution.winning_rules), 0)
        self.assertEqual(intel.decision, "ALLOW")
        self.assertIn("*(No applicable engineering rules)*", intel.combined_laya_context)

    # ── SCENARIO 6: STRICT PROJECT ISOLATION ───────────────────────────────────

    def test_scenario_6_strict_project_isolation(self):
        # Project Alpha: PostgreSQL
        self.service.store_memory(
            content="Alpha uses PostgreSQL database.",
            project_id="project-alpha",
            source_type="doc",
            source_path="alpha.md",
        )
        self.service.create_rule(
            Rule(
                rule_id="alpha-rule",
                name="Alpha Postgres Rule",
                scope=RuleScope.PROJECT,
                project_id="project-alpha",
                description="Alpha database rule.",
            )
        )

        # Project Beta: MongoDB
        self.service.store_memory(
            content="Beta uses MongoDB database.",
            project_id="project-beta",
            source_type="doc",
            source_path="beta.md",
        )
        self.service.create_rule(
            Rule(
                rule_id="beta-rule",
                name="Beta Mongo Rule",
                scope=RuleScope.PROJECT,
                project_id="project-beta",
                description="Beta database rule.",
            )
        )

        # Alpha search must never see Beta
        intel_alpha = self.service.build_intelligence_context(
            task="database configuration",
            project_id="project-alpha",
            min_score=0.0,
        )
        self.assertNotIn("MongoDB", intel_alpha.combined_laya_context)
        self.assertNotIn("Beta", intel_alpha.combined_laya_context)
        self.assertTrue(all(r.project_id != "project-beta" for r in intel_alpha.applicable_rules))

        # Beta search must never see Alpha
        intel_beta = self.service.build_intelligence_context(
            task="database configuration",
            project_id="project-beta",
            min_score=0.0,
        )
        self.assertNotIn("PostgreSQL", intel_beta.combined_laya_context)
        self.assertNotIn("Alpha", intel_beta.combined_laya_context)
        self.assertTrue(all(r.project_id != "project-alpha" for r in intel_beta.applicable_rules))

    # ── SCENARIO 7: CLI-SPECIFIC FILTERING ────────────────────────────────────

    def test_scenario_7_cli_adapter_specific_rules(self):
        self.service.create_rule(
            Rule(
                rule_id="claude-only",
                name="Claude Only",
                scope=RuleScope.CLI,
                cli_filter="claude-cli",
                description="Claude CLI specific rule.",
            )
        )
        self.service.create_rule(
            Rule(
                rule_id="aider-only",
                name="Aider Only",
                scope=RuleScope.CLI,
                cli_filter="aider",
                description="Aider CLI specific rule.",
            )
        )

        intel_claude = self.service.build_intelligence_context(
            task="Build feature",
            cli_name="claude-cli",
        )
        claude_rule_ids = {r.rule_id for r in intel_claude.applicable_rules}
        self.assertIn("claude-only", claude_rule_ids)
        self.assertNotIn("aider-only", claude_rule_ids)

        intel_aider = self.service.build_intelligence_context(
            task="Build feature",
            cli_name="aider",
        )
        aider_rule_ids = {r.rule_id for r in intel_aider.applicable_rules}
        self.assertIn("aider-only", aider_rule_ids)
        self.assertNotIn("claude-only", aider_rule_ids)

    # ── SCENARIO 8: DETERMINISM ACROSS REPEATED RUNS ──────────────────────────

    def test_scenario_8_determinism_property(self):
        self.service.store_memory(
            content="Persistent system configuration note.",
            project_id="proj-determ",
            source_type="doc",
            source_path="config.md",
        )
        self.service.create_rule(
            Rule(
                rule_id="r-det",
                name="Deterministic Rule",
                scope=RuleScope.PROJECT,
                project_id="proj-determ",
                description="Deterministic behavior rule.",
            )
        )

        first = self.service.build_intelligence_context(
            task="System configuration",
            project_id="proj-determ",
            min_score=0.0,
        )

        for _ in range(10):
            nxt = self.service.build_intelligence_context(
                task="System configuration",
                project_id="proj-determ",
                min_score=0.0,
            )
            self.assertEqual(first.decision, nxt.decision)
            self.assertEqual(len(first.memory_context.items), len(nxt.memory_context.items))
            self.assertEqual(
                [r.rule_id for r in first.applicable_rules],
                [r.rule_id for r in nxt.applicable_rules],
            )
            self.assertEqual(first.combined_laya_context, nxt.combined_laya_context)

    # ── SCENARIO 9: SERIALIZATION & DASHBOARD COMPATIBILITY ───────────────────

    def test_scenario_9_serialization_for_member3_dashboard(self):
        self.service.store_memory(
            content="Dashboard inspectable knowledge snippet.",
            project_id="proj-dash",
            source_type="doc",
            source_path="dash.md",
        )
        self.service.create_rule(
            Rule(
                rule_id="r-dash",
                name="Dashboard Rule",
                scope=RuleScope.GLOBAL,
                description="Inspectable by Member 3 frontend.",
            )
        )

        intel = self.service.build_intelligence_context(
            task="Inspect dashboard state",
            project_id="proj-dash",
            min_score=0.0,
        )

        # model_dump() dictionary validation
        dumped_dict = intel.model_dump()
        self.assertIsInstance(dumped_dict, dict)
        self.assertIn("memory_context", dumped_dict)
        self.assertIn("applicable_rules", dumped_dict)
        self.assertIn("rule_resolution", dumped_dict)
        self.assertIn("combined_laya_context", dumped_dict)
        self.assertIn("decision", dumped_dict)

        # model_dump_json() serialization validation
        json_str = intel.model_dump_json()
        self.assertIsInstance(json_str, str)
        reparsed = json.loads(json_str)
        self.assertEqual(reparsed["decision"], "REQUIRE")  # r-dash effect=ENFORCE → RuleDecision.REQUIRE
        self.assertEqual(reparsed["task"], "Inspect dashboard state")

    # ── SCENARIO 10: SUB-SYSTEM ERROR RESILIENCE ──────────────────────────────

    def test_scenario_10_resilience_to_subsystem_errors(self):
        # Patch retrieval to raise an unexpected error
        broken_retrieval = RetrievalService(storage=self.storage)
        broken_retrieval.retrieve_context = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Storage failure"))

        service = LayaIntelligenceService(
            retrieval_service=broken_retrieval,
            rules_engine=self.rules_engine,
            storage=self.storage,
        )

        # Must NOT crash the caller; returns safe fallback with error metadata
        intel = service.build_intelligence_context(task="Test error resilience")
        self.assertIsInstance(intel, LayaIntelligenceContext)
        self.assertEqual(intel.metadata.get("memory_status"), "ERROR")
        self.assertIn("Storage failure", intel.metadata.get("memory_error", ""))
        self.assertEqual(len(intel.memory_context.items), 0)

    # ── SCENARIO 11: ARCHITECTURAL LAYERING CHECK ─────────────────────────────

    def test_scenario_11_layering_composition(self):
        # Facade must compose RetrievalService and RulesEngine, not raw DB
        self.assertIs(self.service.retrieval_service, self.retrieval)
        self.assertIs(self.service.rules_engine, self.rules_engine)
        # Calling retrieve_context delegates cleanly
        res = self.service.retrieve_context(task="test", top_k=2)
        self.assertIsInstance(res, ContextPacket)


if __name__ == "__main__":
    unittest.main()
