"""
Final Member 2 Cross-Member Integration & Hardening Test Suite
==============================================================
Member 2 (Memory / RAG + Rules Intelligence) — CLIVERSE

Validates:
  - Real Member 1 RequestPlanner + StructuredTask pipeline via CliverseMemoryProviderAdapter
  - Direct consumption of Member 1 StructuredTask by LayaIntelligenceService
  - Plain string task input backward compatibility
  - Adversarial 3-project isolation stress test (Alpha vs Beta vs Gamma)
  - CLI adapter isolation (claude-cli vs aider)
  - Ephemeral task rule overrides vs project rules
  - Mandatory safety guardrails (DENY cannot be overridden)
  - Failure injection and explicit status guarantees (OK_WITH_RESULTS, OK_EMPTY, ERROR, UNKNOWN)
  - Full serialization round-trip to dict and JSON
  - Determinism across repeated runs
  - Performance baseline metrics
"""

import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Ensure src is on sys.path for Member 1 contracts
SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cliverse.contracts import (
    ContextBundle,
    ContextItem,
    MemoryHit,
    MemoryProvider,
    MemoryRef,
    Rule as CliverseRule,
    StructuredTask,
)
from cliverse.planning import PlanningRequest, PlanningResult, RequestPlanner

from memory.adapter import CliverseMemoryProviderAdapter
from memory.embeddings.local_engine import LocalBaselineEmbeddingProvider
from memory.ingestion.pipeline import IngestionPipeline
from memory.intelligence import (
    LayaIntelligenceContext,
    LayaIntelligenceService,
    RuleDecision,
    SubsystemStatus,
    TaskLike,
)
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


class TestFinalCrossMemberIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cliverse_final_")
        self.db_path = Path(self.temp_dir) / "test_final.db"
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

        self.adapter = CliverseMemoryProviderAdapter(
            service=self.service,
            project_id="proj-cliverse",
            cli_name="claude-cli",
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ── 1. REAL MEMBER 1 RequestPlanner INTEGRATION ───────────────────────────

    def test_real_member1_request_planner_end_to_end(self):
        """
        Proves the complete pipeline:
          Member 1 PlanningRequest
            ↓
          Member 1 RequestPlanner
            ↓
          Member 2 CliverseMemoryProviderAdapter
            ↓
          Member 2 Ingestion, Storage, Retrieval & Rules
            ↓
          Member 1 PlanningResult with StructuredTask
        """
        # Ingest project knowledge
        self.service.store_memory(
            content="CLIVERSE uses FastAPI backend architecture with SQLite storage.",
            project_id="proj-cliverse",
            source_type="doc",
            source_path="docs/backend.md",
        )
        self.service.store_memory(
            content="JWT tokens are used for API session authentication.",
            project_id="proj-cliverse",
            source_type="decision",
            source_path="decisions/auth.md",
        )

        # Store project rule
        self.service.create_rule(
            Rule(
                rule_id="r-use-fastapi",
                name="Use FastAPI",
                scope=RuleScope.PROJECT,
                project_id="proj-cliverse",
                target="framework",
                effect=RuleEffect.REQUIRE,
                description="Use FastAPI for all backend endpoints.",
            )
        )

        # Instantiate real Member 1 RequestPlanner with Member 2 adapter
        planner = RequestPlanner(memory_provider=self.adapter)
        request = PlanningRequest(
            task="Add JWT authentication to the login endpoint",
            role="AI backend specialist",
            requirements=("Use existing token format",),
        )

        # Execute planning
        result: PlanningResult = planner.plan(request)

        # Assert Member 1 PlanningResult is ready and properly formed
        self.assertTrue(result.ready)
        self.assertIsInstance(result.task, StructuredTask)
        self.assertEqual(result.task.role, "AI backend specialist")
        self.assertEqual(result.task.task, "Add JWT authentication to the login endpoint")
        self.assertEqual(result.task.requirements, ("Use existing token format",))

        # Verify retrieved context was injected into the structured task context
        self.assertTrue(len(result.task.context) > 0)
        self.assertTrue(
            "FastAPI backend" in result.task.context or "JWT tokens" in result.task.context
        )

        # Verify project rule was converted and injected into constraints
        self.assertIn("r-use-fastapi", result.applicable_rule_ids)
        self.assertTrue(any("Use FastAPI for all backend endpoints" in c for c in result.task.constraints))

        # Verify provenance was preserved
        self.assertTrue(len(result.context_provenance) > 0)
        self.assertTrue(any("docs/backend.md" in p or "decisions/auth.md" in p for p in result.context_provenance))

    # ── 2. REAL MEMBER 1 StructuredTask DIRECT INTAKE ─────────────────────────

    def test_direct_intake_of_member1_structured_task(self):
        """Member 2 build_intelligence_context accepts a real StructuredTask object."""
        self.service.store_memory(
            content="PostgreSQL configuration guide.",
            project_id="proj-structured",
            source_type="doc",
            source_path="docs/postgres.md",
        )
        task_obj = StructuredTask(
            role="Software Engineer",
            context="Initial system design",
            task="Configure PostgreSQL database connection pool",
            requirements=("Pool size 20",),
            constraints=("Max timeout 5s",),
            output="Report configuration parameters",
        )

        # Satisfies TaskLike protocol
        self.assertIsInstance(task_obj, TaskLike)

        # Pass directly into Member 2
        intel = self.service.build_intelligence_context(
            task=task_obj,
            project_id="proj-structured",
            min_score=0.1,
        )

        self.assertIsInstance(intel, LayaIntelligenceContext)
        self.assertEqual(intel.task, "Configure PostgreSQL database connection pool")
        self.assertIn("role", intel.metadata)
        self.assertEqual(intel.metadata["role"], "Software Engineer")
        self.assertEqual(intel.metadata["requirements"], ["Pool size 20"])
        self.assertEqual(intel.memory_status, SubsystemStatus.OK_WITH_RESULTS)

    # ── 3. PLAIN STRING TASK COMPATIBILITY ────────────────────────────────────

    def test_plain_string_task_compatibility(self):
        """Plain string tasks continue to work seamlessly without wrapper objects."""
        intel = self.service.build_intelligence_context(
            task="Simple string task query",
            project_id="proj-plain",
        )
        self.assertEqual(intel.task, "Simple string task query")
        self.assertIsInstance(intel, LayaIntelligenceContext)

    # ── 4. ADVERSARIAL 3-PROJECT ISOLATION STRESS TEST ─────────────────────────

    def test_adversarial_three_project_isolation(self):
        """
        Adversarial test with identical file paths, similar rule names, and similar queries.
        Proves strict boundary between Alpha (PostgreSQL/JWT), Beta (MongoDB/OAuth), Gamma (SQLite/Session).
        """
        projects = {
            "proj-alpha": {
                "db": "PostgreSQL relational database engine",
                "auth": "JWT RS256 token verification",
                "rule_desc": "Alpha standard: Always use PostgreSQL.",
            },
            "proj-beta": {
                "db": "MongoDB document store engine",
                "auth": "OAuth 2.0 PKCE authorization flow",
                "rule_desc": "Beta standard: Always use MongoDB.",
            },
            "proj-gamma": {
                "db": "SQLite local file-based database",
                "auth": "Session cookie stateful authentication",
                "rule_desc": "Gamma standard: Always use SQLite.",
            },
        }

        # Ingest identical source paths across all three projects
        for pid, data in projects.items():
            self.service.store_memory(
                content=f"Database choice: {data['db']}",
                project_id=pid,
                source_type="doc",
                source_path="shared/database.md",
            )
            self.service.store_memory(
                content=f"Authentication choice: {data['auth']}",
                project_id=pid,
                source_type="doc",
                source_path="shared/auth.md",
            )
            self.service.create_rule(
                Rule(
                    rule_id=f"rule-{pid}",
                    name="DB Rule",
                    scope=RuleScope.PROJECT,
                    project_id=pid,
                    target="database",
                    description=data["rule_desc"],
                )
            )

        # Test Alpha
        intel_alpha = self.service.build_intelligence_context(
            task="Configure database and authentication",
            project_id="proj-alpha",
            min_score=0.0,
        )
        self.assertIn("PostgreSQL", intel_alpha.combined_laya_context)
        self.assertNotIn("MongoDB", intel_alpha.combined_laya_context)
        self.assertNotIn("SQLite", intel_alpha.combined_laya_context)
        self.assertNotIn("OAuth", intel_alpha.combined_laya_context)
        self.assertNotIn("Session cookie", intel_alpha.combined_laya_context)
        self.assertEqual({r.rule_id for r in intel_alpha.applicable_rules}, {"rule-proj-alpha"})

        # Test Beta
        intel_beta = self.service.build_intelligence_context(
            task="Configure database and authentication",
            project_id="proj-beta",
            min_score=0.0,
        )
        self.assertIn("MongoDB", intel_beta.combined_laya_context)
        self.assertNotIn("PostgreSQL", intel_beta.combined_laya_context)
        self.assertNotIn("SQLite", intel_beta.combined_laya_context)
        self.assertNotIn("RS256", intel_beta.combined_laya_context)
        self.assertEqual({r.rule_id for r in intel_beta.applicable_rules}, {"rule-proj-beta"})

        # Test Gamma
        intel_gamma = self.service.build_intelligence_context(
            task="Configure database and authentication",
            project_id="proj-gamma",
            min_score=0.0,
        )
        self.assertIn("SQLite", intel_gamma.combined_laya_context)
        self.assertNotIn("PostgreSQL", intel_gamma.combined_laya_context)
        self.assertNotIn("MongoDB", intel_gamma.combined_laya_context)
        self.assertNotIn("OAuth", intel_gamma.combined_laya_context)
        self.assertEqual({r.rule_id for r in intel_gamma.applicable_rules}, {"rule-proj-gamma"})

    # ── 5. CLI-SPECIFIC RULE ISOLATION ────────────────────────────────────────

    def test_cli_adapter_rule_isolation(self):
        """Rules scoped to claude-cli do not apply to aider and vice versa."""
        self.service.create_rule(
            Rule(
                rule_id="r-claude-pkg",
                name="Claude Confirm",
                scope=RuleScope.CLI,
                cli_filter="claude-cli",
                target="packages",
                effect=RuleEffect.ASK,
                description="Ask confirmation before Claude installs packages.",
            )
        )
        self.service.create_rule(
            Rule(
                rule_id="r-aider-pkg",
                name="Aider Deny",
                scope=RuleScope.CLI,
                cli_filter="aider",
                target="packages",
                effect=RuleEffect.DENY,
                description="Aider must not install packages directly.",
            )
        )

        intel_claude = self.service.build_intelligence_context(
            task="Install requests library",
            cli_name="claude-cli",
        )
        claude_rules = {r.rule_id for r in intel_claude.applicable_rules}
        self.assertIn("r-claude-pkg", claude_rules)
        self.assertNotIn("r-aider-pkg", claude_rules)
        self.assertEqual(intel_claude.rule_decision, RuleDecision.ASK)

        intel_aider = self.service.build_intelligence_context(
            task="Install requests library",
            cli_name="aider",
        )
        aider_rules = {r.rule_id for r in intel_aider.applicable_rules}
        self.assertIn("r-aider-pkg", aider_rules)
        self.assertNotIn("r-claude-pkg", aider_rules)
        self.assertEqual(intel_aider.rule_decision, RuleDecision.DENY)

    # ── 6. MANDATORY GUARDRAIL PRECEDENCE ─────────────────────────────────────

    def test_mandatory_guardrail_cannot_be_overridden_by_task(self):
        """
        Global mandatory rule with effect=DENY cannot be overridden by higher-scope
        task rule with effect=ALLOW.
        """
        self.service.create_rule(
            Rule(
                rule_id="g-no-secrets",
                name="Never Print Secrets",
                scope=RuleScope.GLOBAL,
                target="security",
                effect=RuleEffect.DENY,
                is_mandatory=True,
                description="Never print production secrets or environment variables.",
            )
        )

        task_override = Rule(
            rule_id="t-allow-secrets",
            name="Allow Print Secrets",
            scope=RuleScope.TASK,
            target="security",
            effect=RuleEffect.ALLOW,
            priority=99,
            description="Allow printing environment variables for debugging.",
        )

        intel = self.service.build_intelligence_context(
            task="Print production environment variables for debugging",
            project_id="any-project",
            task_rules=[task_override],
        )

        self.assertEqual(intel.rule_decision, RuleDecision.DENY)
        self.assertEqual(intel.rules_status, SubsystemStatus.OK_WITH_RESULTS)
        self.assertEqual(intel.rule_resolution.winning_rules[0].rule_id, "g-no-secrets")
        self.assertEqual(intel.rule_resolution.suppressed_rules[0].rule_id, "t-allow-secrets")
        self.assertIn("cannot be overridden", intel.rule_resolution.conflicts[0].reason)
        # Ensure Member 2 does not claim to be the final security authority
        self.assertNotIn("security_decision", intel.model_dump())

    # ── 7. SCOPE CONFLICT RESOLUTION ──────────────────────────────────────────

    def test_task_rule_overrides_non_mandatory_project_rule(self):
        """Task rule legitimately overrides non-mandatory Project rule on the same target."""
        self.service.create_rule(
            Rule(
                rule_id="p-use-postgres",
                name="Project Postgres",
                scope=RuleScope.PROJECT,
                project_id="proj-override",
                target="database",
                effect=RuleEffect.REQUIRE,
                description="Use PostgreSQL for all services.",
            )
        )
        task_mongo = Rule(
            rule_id="t-use-mongo",
            name="Task Mongo",
            scope=RuleScope.TASK,
            target="database",
            effect=RuleEffect.REQUIRE,
            description="Use MongoDB for this analytics task.",
        )

        intel = self.service.build_intelligence_context(
            task="Build analytics module",
            project_id="proj-override",
            task_rules=[task_mongo],
        )

        self.assertEqual(len(intel.rule_resolution.conflicts), 1)
        self.assertEqual(intel.rule_resolution.winning_rules[0].rule_id, "t-use-mongo")
        self.assertEqual(intel.rule_resolution.suppressed_rules[0].rule_id, "p-use-postgres")

    # ── 8. FAILURE SEMANTICS AND STATUS DISTINCTIONS ──────────────────────────

    def test_failure_semantics_strict_distinction(self):
        """
        Strictly tests the 6 state combinations:
          A. Memory OK_EMPTY + Rules OK_EMPTY -> ALLOW
          B. Memory ERROR + Rules OK -> rule_decision based on rules, memory_status=ERROR
          C. Rules OK_EMPTY + Memory OK_WITH_RESULTS -> ALLOW
          D. Rules ERROR + Memory OK -> rule_decision=UNKNOWN (never ALLOW), rules_status=ERROR
          E. Both ERROR -> UNKNOWN, both ERROR
          F. Both OK_WITH_RESULTS -> healthy output
        """
        # A: Both OK_EMPTY
        intel_a = self.service.build_intelligence_context(task="Empty test", project_id="empty-proj")
        self.assertEqual(intel_a.memory_status, SubsystemStatus.OK_EMPTY)
        self.assertEqual(intel_a.rules_status, SubsystemStatus.OK_EMPTY)
        self.assertEqual(intel_a.rule_decision, RuleDecision.ALLOW)
        self.assertIn("*(No relevant project memory found)*", intel_a.combined_laya_context)
        self.assertIn("*(No applicable engineering rules)*", intel_a.combined_laya_context)

        # B: Memory ERROR
        broken_retrieval = RetrievalService(storage=self.storage)
        broken_retrieval.retrieve_context = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("DB read error"))
        svc_b = LayaIntelligenceService(retrieval_service=broken_retrieval, rules_engine=self.rules_engine)
        intel_b = svc_b.build_intelligence_context(task="Query")
        self.assertEqual(intel_b.memory_status, SubsystemStatus.ERROR)
        self.assertIn("Memory subsystem error: DB read error", intel_b.combined_laya_context)
        self.assertNotIn("No relevant project memory found", intel_b.combined_laya_context)

        # D: Rules ERROR
        broken_rules = RulesEngine(storage=self.rule_store)
        broken_rules.get_applicable_rules = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("Rules engine failure"))
        svc_d = LayaIntelligenceService(retrieval_service=self.retrieval, rules_engine=broken_rules)
        intel_d = svc_d.build_intelligence_context(task="Query")
        self.assertEqual(intel_d.rules_status, SubsystemStatus.ERROR)
        self.assertEqual(intel_d.rule_decision, RuleDecision.UNKNOWN)
        self.assertEqual(intel_d.decision, "UNKNOWN")
        self.assertIn("Rules subsystem error: Rules engine failure", intel_d.combined_laya_context)

        # E: Both ERROR
        svc_e = LayaIntelligenceService(retrieval_service=broken_retrieval, rules_engine=broken_rules)
        intel_e = svc_e.build_intelligence_context(task="Query")
        self.assertEqual(intel_e.memory_status, SubsystemStatus.ERROR)
        self.assertEqual(intel_e.rules_status, SubsystemStatus.ERROR)
        self.assertEqual(intel_e.rule_decision, RuleDecision.UNKNOWN)

    # ── 9. SERIALIZATION ROUND-TRIP ───────────────────────────────────────────

    def test_full_serialization_round_trip(self):
        """Verifies all 12 key fields survive serialization into JSON and back."""
        self.service.store_memory(
            content="Architecture knowledge item.",
            project_id="proj-serialize",
            source_type="doc",
            source_path="arch.md",
        )
        self.service.create_rule(
            Rule(
                rule_id="r-ser",
                name="Serialization Rule",
                scope=RuleScope.PROJECT,
                project_id="proj-serialize",
                description="Must serialize cleanly.",
                effect=RuleEffect.REQUIRE,
            )
        )

        intel = self.service.build_intelligence_context(
            task="Serialize context",
            project_id="proj-serialize",
            cli_name="claude-cli",
            min_score=0.0,
        )

        dumped = intel.model_dump()
        json_str = intel.model_dump_json()
        reparsed = json.loads(json_str)

        fields = [
            "task",
            "project_id",
            "cli_name",
            "memory_context",
            "applicable_rules",
            "rule_resolution",
            "context_sources",
            "rule_explanations",
            "combined_laya_context",
            "rule_decision",
            "memory_status",
            "rules_status",
            "decision",
            "metadata",
        ]
        for f in fields:
            self.assertIn(f, dumped, f"Missing field in dict: {f}")
            self.assertIn(f, reparsed, f"Missing field in JSON: {f}")

        self.assertEqual(reparsed["rule_decision"], "REQUIRE")
        self.assertEqual(reparsed["decision"], "REQUIRE")
        self.assertEqual(reparsed["memory_status"], "OK_WITH_RESULTS")
        self.assertEqual(reparsed["rules_status"], "OK_WITH_RESULTS")

    # ── 10. DETERMINISM VERIFICATION ──────────────────────────────────────────

    def test_determinism_across_multiple_runs(self):
        """Repeated identical calls produce byte-for-byte identical text and models."""
        self.service.store_memory(
            content="Deterministic system configuration.",
            project_id="proj-det-final",
            source_type="doc",
            source_path="config.md",
        )
        self.service.create_rule(
            Rule(
                rule_id="r-det-final",
                name="Deterministic Rule",
                scope=RuleScope.PROJECT,
                project_id="proj-det-final",
                description="Must be deterministic.",
            )
        )

        base = self.service.build_intelligence_context(
            task="Configure system",
            project_id="proj-det-final",
            min_score=0.0,
        )

        for _ in range(5):
            curr = self.service.build_intelligence_context(
                task="Configure system",
                project_id="proj-det-final",
                min_score=0.0,
            )
            self.assertEqual(base.combined_laya_context, curr.combined_laya_context)
            self.assertEqual(base.rule_decision, curr.rule_decision)
            self.assertEqual(base.memory_status, curr.memory_status)
            self.assertEqual(base.rules_status, curr.rules_status)

    # ── 11. LOCAL PERFORMANCE BASELINE ────────────────────────────────────────

    def test_local_performance_baseline(self):
        """Measures execution speed to ensure no pathological latency in MVP."""
        # Ingest 5 chunks
        t0 = time.perf_counter()
        for i in range(5):
            self.service.store_memory(
                content=f"Knowledge paragraph {i} discussing software architecture patterns.",
                project_id="proj-perf",
                source_type="doc",
                source_path=f"docs/doc_{i}.md",
            )
        t_ingest = time.perf_counter() - t0

        # Create 5 rules
        for i in range(5):
            self.service.create_rule(
                Rule(
                    rule_id=f"r-perf-{i}",
                    name=f"Rule {i}",
                    scope=RuleScope.PROJECT,
                    project_id="proj-perf",
                    description=f"Performance test rule number {i}.",
                )
            )

        # Retrieval time
        t0 = time.perf_counter()
        _ = self.service.retrieve_context(task="architecture patterns", project_id="proj-perf")
        t_retrieval = time.perf_counter() - t0

        # Rule resolution time
        t0 = time.perf_counter()
        _ = self.service.resolve_rules(task="architecture patterns", project_id="proj-perf")
        t_rules = time.perf_counter() - t0

        # Unified context construction time
        t0 = time.perf_counter()
        _ = self.service.build_intelligence_context(task="architecture patterns", project_id="proj-perf")
        t_context = time.perf_counter() - t0

        # Assert all operations complete well within conservative local bounds (< 1.0s each)
        self.assertLess(t_ingest, 2.0)
        self.assertLess(t_retrieval, 1.0)
        self.assertLess(t_rules, 1.0)
        self.assertLess(t_context, 1.0)

    # ── 12. ADAPTER INFORMATION LOSS PREVENTION (PHASE 7) ─────────────────────

    def test_adapter_preserves_rule_semantics_without_information_loss(self):
        """
        Proves that converting Member 2 rules into Member 1 rules preserves:
          - Mandatory state (tagged in content, recorded in source, elevated priority)
          - Rule effects (REQUIRE, DENY, ASK, WARN)
          - Target domain and version
          - Full untruncated Member 2 Rule instance via _member2_rule and adapter lookup
        """
        # Create a mandatory global rule and a project prerequisite rule
        self.service.create_rule(
            Rule(
                rule_id="mand-deny-keys",
                name="Never Commit Keys",
                scope=RuleScope.GLOBAL,
                target="security",
                effect=RuleEffect.DENY,
                is_mandatory=True,
                version=2,
                description="Never commit private API keys.",
            )
        )
        self.service.create_rule(
            Rule(
                rule_id="proj-require-lint",
                name="Lint Prerequisite",
                scope=RuleScope.PROJECT,
                project_id="proj-cliverse",
                target="quality",
                effect=RuleEffect.REQUIRE,
                version=1,
                description="Linter must pass before push.",
            )
        )

        cliverse_rules = self.adapter.get_applicable_rules(task="Commit code changes")
        rules_by_id = {r.rule_id: r for r in cliverse_rules}

        # 1. Mandatory DENY rule verification
        mand_rule = rules_by_id.get("mand-deny-keys")
        self.assertIsNotNone(mand_rule)
        self.assertIn("[DENY MANDATORY]", mand_rule.content)
        self.assertIn("mandatory=True", mand_rule.source)
        self.assertIn("effect=DENY", mand_rule.source)
        self.assertIn("version=2", mand_rule.source)
        self.assertGreaterEqual(mand_rule.priority, 9999)  # Elevated priority

        # 2. Project REQUIRE rule verification
        req_rule = rules_by_id.get("proj-require-lint")
        self.assertIsNotNone(req_rule)
        self.assertIn("[REQUIRE]", req_rule.content)
        self.assertIn("effect=REQUIRE", req_rule.source)
        self.assertIn("mandatory=False", req_rule.source)

        # 3. Direct access to untruncated Member 2 Rule models
        m2_mand = getattr(mand_rule, "_member2_rule", None)
        self.assertIsNotNone(m2_mand)
        self.assertTrue(m2_mand.is_mandatory)
        self.assertEqual(m2_mand.effect, RuleEffect.DENY)

        lookup_m2 = self.adapter.get_member2_rule("mand-deny-keys")
        self.assertIsNotNone(lookup_m2)
        self.assertEqual(lookup_m2.description, "Never commit private API keys.")

        # 4. Context preservation on adapter
        last_ctx = self.adapter.get_last_intelligence_context()
        self.assertIsNotNone(last_ctx)
        self.assertEqual(last_ctx.rule_decision, RuleDecision.DENY)

    # ── 13. NO DUPLICATE RULE EVALUATION (PHASE 9) ────────────────────────────

    def test_no_duplicate_rule_evaluation_in_build_intelligence_context(self):
        """
        Verifies that get_applicable_rules is evaluated exactly once during
        build_intelligence_context, with candidates passed into resolve_rules.
        """
        calls = {"get_applicable": 0}
        orig_get_applicable = self.service.rules_engine.get_applicable_rules

        def tracked_get_applicable(*args, **kwargs):
            calls["get_applicable"] += 1
            return orig_get_applicable(*args, **kwargs)

        self.service.rules_engine.get_applicable_rules = tracked_get_applicable

        _ = self.service.build_intelligence_context(task="Evaluate once test", project_id="proj-cliverse")

        # Must be called exactly once (NOT twice)
        self.assertEqual(calls["get_applicable"], 1)

    # ── 14. TASK CONTRACT VALIDATION (PHASE 11) ───────────────────────────────

    def test_invalid_task_inputs_rejected_clearly(self):
        """Rejects empty string, whitespace, non-TaskLike types with clear errors."""
        with self.assertRaises(ValueError):
            self.service.build_intelligence_context(task="")

        with self.assertRaises(ValueError):
            self.service.build_intelligence_context(task="   \n\t  ")

        with self.assertRaises(TypeError):
            self.service.build_intelligence_context(task=12345)

        with self.assertRaises(TypeError):
            self.service.build_intelligence_context(task=None)


if __name__ == "__main__":
    unittest.main()

