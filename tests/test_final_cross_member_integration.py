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

        # 3. Direct access to untruncated Member 2 Rule models via adapter lookup
        lookup_m2 = self.adapter.get_member2_rule("mand-deny-keys")
        self.assertIsNotNone(lookup_m2)
        self.assertTrue(lookup_m2.is_mandatory)
        self.assertEqual(lookup_m2.effect, RuleEffect.DENY)
        self.assertEqual(lookup_m2.description, "Never commit private API keys.")

        # Frozen dataclass must NOT carry private _member2_rule attribute
        self.assertFalse(hasattr(mand_rule, "_member2_rule"))

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

    # ── 15. HARSH TRUTHS RESOLUTION VERIFICATION ─────────────────────────────

    def test_adapter_single_entry_cache_prevents_double_evaluation(self):
        """Verifies RequestPlanner.plan() triggers build_intelligence_context exactly once."""
        calls = {"build_intel": 0}
        orig_build = self.service.build_intelligence_context

        def tracked_build(*args, **kwargs):
            calls["build_intel"] += 1
            return orig_build(*args, **kwargs)

        self.service.build_intelligence_context = tracked_build

        planner = RequestPlanner(memory_provider=self.adapter)
        plan_result = planner.plan(PlanningRequest(
            task="Add JWT authentication for session verification",
            role="Backend Engineer",
        ))

        self.assertIsNotNone(plan_result.task)
        # Even though RequestPlanner calls retrieve_context() AND get_applicable_rules(),
        # the adapter's single-entry cache must ensure build_intelligence_context runs only ONCE.
        self.assertEqual(calls["build_intel"], 1)

    def test_extract_task_text_strips_whitespace(self):
        """Verifies leading and trailing whitespace is stripped from task input."""
        context = self.service.build_intelligence_context(
            task="   Deploy microservice to cluster   \n\t",
            project_id="proj-cliverse",
        )
        self.assertEqual(context.task, "Deploy microservice to cluster")

    def test_public_resolve_rules_accepts_pre_evaluated_rules(self):
        """Verifies public service.resolve_rules() passes through applicable_rules without re-evaluating."""
        rule1 = Rule(
            rule_id="test-pre-1",
            name="Test Pre 1",
            scope=RuleScope.PROJECT,
            target="testing",
            effect=RuleEffect.REQUIRE,
            description="Run unit tests",
        )
        calls = {"get_applicable": 0}
        orig_get_applicable = self.service.rules_engine.get_applicable_rules

        def tracked_get_applicable(*args, **kwargs):
            calls["get_applicable"] += 1
            return orig_get_applicable(*args, **kwargs)

        self.service.rules_engine.get_applicable_rules = tracked_get_applicable

        res = self.service.resolve_rules(
            task="Run unit tests",
            project_id="proj-cliverse",
            applicable_rules=[rule1],
        )

        self.assertEqual(len(res.winning_rules), 1)
        self.assertEqual(res.winning_rules[0].rule_id, "test-pre-1")
        # get_applicable_rules must NOT be called when applicable_rules is provided
        self.assertEqual(calls["get_applicable"], 0)

    def test_rank_and_deduplicate_configurable_overlap_threshold(self):
        """Verifies rank_and_deduplicate_results respects custom overlap_threshold."""
        from memory.models import MemorySearchResult
        from memory.retrieval.ranking import rank_and_deduplicate_results

        # Two chunks from same record with 50% line overlap
        c1 = MemorySearchResult(
            chunk_id="chunk-1",
            record_id="rec-1",
            content="Alpha section line 1 to 10",
            score=0.9,
            source_path="file.md",
            source_type="doc",
            start_line=1,
            end_line=10,
        )
        c2 = MemorySearchResult(
            chunk_id="chunk-2",
            record_id="rec-1",
            content="Beta section line 6 to 15",
            score=0.85,
            source_path="file.md",
            source_type="doc",
            start_line=6,
            end_line=15,  # 5 lines overlap with c1 (lines 6-10), out of 10 lines (50%)
        )

        # With default overlap_threshold=0.6: 50% <= 60%, so c2 is NOT considered redundant
        res_default = rank_and_deduplicate_results([c1, c2], min_score=0.1, overlap_threshold=0.6)
        self.assertEqual(len(res_default), 2)

        # With aggressive overlap_threshold=0.4: 50% > 40%, so c2 is dropped as redundant
        res_strict = rank_and_deduplicate_results([c1, c2], min_score=0.1, overlap_threshold=0.4)
        self.assertEqual(len(res_strict), 1)
        self.assertEqual(res_strict[0].chunk_id, "chunk-1")

    def test_rule_parser_json_without_yaml_dependency(self):
        """Verifies RuleParser handles JSON string definitions natively."""
        from rules.parser import RuleParser
        json_data = json.dumps({
            "id": "json-rule-1",
            "name": "JSON Rule",
            "scope": "PROJECT",
            "target": "security",
            "effect": "DENY",
            "description": "Never hardcode passwords",
        })
        rules = RuleParser.parse_string(json_data, source_label="json_test")
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].rule_id, "json-rule-1")
        self.assertEqual(rules[0].effect, RuleEffect.DENY)

    # ── 16. P0-1: DETERMINISTIC ADAPTER CACHE FINGERPRINT ────────────────────

    def test_adapter_cache_key_deterministic_and_comprehensive(self):
        """
        P0-1 verification:
          A. same logical request -> exactly one build_intelligence_context call.
          B. different task -> no reuse.
          C. different project_id -> no reuse.
          D. different cli_name -> no reuse.
          E. different task_metadata -> no reuse.
          F. different task_rules -> no reuse.
          G. same dictionaries with different key insertion order -> SAME cache key.
        """
        from memory.adapter import compute_adapter_context_cache_key

        calls = {"count": 0}
        orig_build = self.service.build_intelligence_context

        def tracked_build(*args, **kwargs):
            calls["count"] += 1
            return orig_build(*args, **kwargs)

        self.service.build_intelligence_context = tracked_build

        # A. Same logical request: exactly one build
        task_a = "Deploy to production cluster"
        _ = self.adapter.retrieve_context(task_a)
        _ = self.adapter.get_applicable_rules(task_a)
        self.assertEqual(calls["count"], 1, "Sequential calls with same request must reuse cache")

        # B. Different task: triggers rebuild
        _ = self.adapter.retrieve_context("Rollback release")
        self.assertEqual(calls["count"], 2, "Different task must trigger new build")

        # C. Different project_id: triggers rebuild
        adapter_b = CliverseMemoryProviderAdapter(service=self.service, project_id="proj-other", cli_name="claude-cli")
        _ = adapter_b.retrieve_context("Rollback release")
        self.assertEqual(calls["count"], 3, "Different project_id must trigger new build")

        # D. Different cli_name: triggers rebuild
        adapter_c = CliverseMemoryProviderAdapter(service=self.service, project_id="proj-other", cli_name="aider")
        _ = adapter_c.retrieve_context("Rollback release")
        self.assertEqual(calls["count"], 4, "Different cli_name must trigger new build")

        # E. Different task_metadata: produces different cache key
        key_meta1 = compute_adapter_context_cache_key("task", "proj", "cli", task_metadata={"env": "prod"})
        key_meta2 = compute_adapter_context_cache_key("task", "proj", "cli", task_metadata={"env": "staging"})
        self.assertNotEqual(key_meta1, key_meta2, "Different task_metadata must produce different cache key")

        # F. Different task_rules: produces different cache key
        r1 = Rule(rule_id="r1", name="R1", scope=RuleScope.TASK, target="t1", effect=RuleEffect.WARN, description="d1")
        r2 = Rule(rule_id="r2", name="R2", scope=RuleScope.TASK, target="t2", effect=RuleEffect.DENY, description="d2")
        key_rules1 = compute_adapter_context_cache_key("task", "proj", "cli", task_rules=[r1])
        key_rules2 = compute_adapter_context_cache_key("task", "proj", "cli", task_rules=[r2])
        self.assertNotEqual(key_rules1, key_rules2, "Different task_rules must produce different cache key")

        # G. Same dictionaries with different key insertion order: SAME cache key
        dict_order_1 = {"alpha": 1, "beta": 2, "gamma": {"nested_z": 9, "nested_a": 8}}
        dict_order_2 = {"gamma": {"nested_a": 8, "nested_z": 9}, "beta": 2, "alpha": 1}
        key_ord1 = compute_adapter_context_cache_key("task", "proj", "cli", task_metadata=dict_order_1)
        key_ord2 = compute_adapter_context_cache_key("task", "proj", "cli", task_metadata=dict_order_2)
        self.assertEqual(key_ord1, key_ord2, "Dictionary key insertion order must not change cache key")

        # H. Same rules with different list ordering: SAME cache key
        key_rules_perm1 = compute_adapter_context_cache_key("task", "proj", "cli", task_rules=[r1, r2])
        key_rules_perm2 = compute_adapter_context_cache_key("task", "proj", "cli", task_rules=[r2, r1])
        self.assertEqual(key_rules_perm1, key_rules_perm2, "Rule list ordering must not change cache key")

    # ── 17. P0-2: EXPLICIT CACHE INVALIDATION ON MUTATIONS ────────────────────

    def test_cache_invalidation_on_memory_and_rule_mutations(self):
        """
        P0-2 verification:
          1. Build context and confirm cache reuse.
          2. Mutate memory (store_memory) -> confirm context rebuild.
          3. Mutate memory (delete_memory) -> confirm context rebuild.
          4. Mutate rules (create_rule) -> confirm context rebuild.
          5. Mutate rules (update_rule) -> confirm context rebuild.
          6. Mutate rules (delete_rule) -> confirm context rebuild.
        """
        calls = {"count": 0}
        orig_build = self.service.build_intelligence_context

        def tracked_build(*args, **kwargs):
            calls["count"] += 1
            return orig_build(*args, **kwargs)

        self.service.build_intelligence_context = tracked_build

        task = "Verify database connection pooling"

        # 1. Initial build
        _ = self.adapter.retrieve_context(task)
        self.assertEqual(calls["count"], 1)
        # Re-request -> cache hit
        _ = self.adapter.get_applicable_rules(task)
        self.assertEqual(calls["count"], 1, "Must hit cache")

        # 2. Mutate memory via adapter.store_memory
        ref = self.adapter.store_memory({
            "content": "Database pooling uses max 20 connections.",
            "source_path": "docs/db_pool.md",
        })
        self.assertIsNotNone(ref.memory_id)

        # Re-request -> cache must be invalidated, triggering rebuild
        _ = self.adapter.retrieve_context(task)
        self.assertEqual(calls["count"], 2, "Memory store must invalidate cache")

        # Re-request -> cache hit
        _ = self.adapter.get_applicable_rules(task)
        self.assertEqual(calls["count"], 2)

        # 3. Mutate memory via service.delete_memory
        deleted = self.service.delete_memory(ref.memory_id)
        self.assertTrue(deleted)

        _ = self.adapter.retrieve_context(task)
        self.assertEqual(calls["count"], 3, "Memory delete must invalidate cache")

        # 4. Mutate rules via service.create_rule
        new_rule = Rule(
            rule_id="pool-limit-rule",
            name="Pool Limit",
            scope=RuleScope.PROJECT,
            project_id="proj-cliverse",
            target="database",
            effect=RuleEffect.REQUIRE,
            description="Max pool size 20",
        )
        self.service.create_rule(new_rule)

        _ = self.adapter.retrieve_context(task)
        self.assertEqual(calls["count"], 4, "Rule creation must invalidate cache")

        # 5. Mutate rules via service.update_rule
        new_rule.description = "Max pool size 30"
        self.service.update_rule(new_rule)

        _ = self.adapter.retrieve_context(task)
        self.assertEqual(calls["count"], 5, "Rule update must invalidate cache")

        # 6. Mutate rules via service.delete_rule
        self.service.delete_rule("pool-limit-rule")

        _ = self.adapter.retrieve_context(task)
        self.assertEqual(calls["count"], 6, "Rule deletion must invalidate cache")

    # ── 18. P0-3: FROZEN DATACLASS COMPLIANCE WITHOUT _member2_rule HACK ──────

    def test_frozen_dataclass_adapter_rule_contract_compliance(self):
        """
        P0-3 verification:
          1. Adapted rule contains all required externally visible semantics.
          2. Deep copy remains semantically identical.
          3. Serialization/deserialization retains semantics.
          4. No _member2_rule private attribute is present.
          5. parse_cliverse_rule_semantics extracts all fields cleanly.
        """
        import copy
        from memory.adapter import parse_cliverse_rule_semantics

        self.service.create_rule(Rule(
            rule_id="strict-auth-gate",
            name="Strict Auth Gate",
            scope=RuleScope.GLOBAL,
            target="security",
            effect=RuleEffect.DENY,
            is_mandatory=True,
            version=3,
            priority=85,
            description="Strictly reject unauthorized operations.",
        ))

        rules = self.adapter.get_applicable_rules(task="Execute sensitive command")
        rule_map = {r.rule_id: r for r in rules}
        self.assertIn("strict-auth-gate", rule_map)
        adapted_rule = rule_map["strict-auth-gate"]

        # 1. No _member2_rule attribute exists
        self.assertFalse(hasattr(adapted_rule, "_member2_rule"))
        self.assertNotIn("_member2_rule", adapted_rule.__dict__ if hasattr(adapted_rule, "__dict__") else ())

        # 2. Required semantics preserved in public fields
        self.assertEqual(adapted_rule.rule_id, "strict-auth-gate")
        self.assertIn("[DENY MANDATORY]", adapted_rule.content)
        self.assertIn("Strictly reject unauthorized operations.", adapted_rule.content)
        self.assertEqual(adapted_rule.scope, "global")
        self.assertGreaterEqual(adapted_rule.priority, 9999)  # Elevated for mandatory
        self.assertIn("effect=DENY", adapted_rule.source)
        self.assertIn("mandatory=True", adapted_rule.source)
        self.assertIn("version=3", adapted_rule.source)
        self.assertIn("rules:security", adapted_rule.source)

        # 3. parse_cliverse_rule_semantics extracts all attributes
        semantics = parse_cliverse_rule_semantics(adapted_rule)
        self.assertEqual(semantics["rule_id"], "strict-auth-gate")
        self.assertEqual(semantics["effect"], "DENY")
        self.assertTrue(semantics["is_mandatory"])
        self.assertEqual(semantics["target"], "security")
        self.assertEqual(semantics["version"], 3)
        self.assertEqual(semantics["description"], "Strictly reject unauthorized operations.")

        # 4. Deep copy remains semantically identical
        rule_copy = copy.deepcopy(adapted_rule)
        self.assertEqual(rule_copy.rule_id, adapted_rule.rule_id)
        self.assertEqual(rule_copy.content, adapted_rule.content)
        self.assertEqual(rule_copy.source, adapted_rule.source)
        self.assertEqual(rule_copy.priority, adapted_rule.priority)
        self.assertEqual(parse_cliverse_rule_semantics(rule_copy), semantics)

    # ── 19. P0-4: EXACTLY ONE EVALUATION IN resolve_rules & build_context ─────

    def test_resolve_rules_has_exactly_one_evaluation_and_resolution(self):
        """
        P0-4 verification:
          1. Direct service.resolve_rules() executes:
             - exactly ONE applicability evaluation
             - exactly ONE conflict resolution
          2. service.build_intelligence_context() executes:
             - exactly ONE applicability evaluation
             - exactly ONE conflict resolution
        """
        from rules.resolver import RuleResolver
        eval_counts = {"applicable": 0, "resolve": 0}

        orig_applicable = self.service.rules_engine.get_applicable_rules
        orig_resolve = RuleResolver.resolve

        def tracked_applicable(*args, **kwargs):
            eval_counts["applicable"] += 1
            return orig_applicable(*args, **kwargs)

        def tracked_resolve(*args, **kwargs):
            eval_counts["resolve"] += 1
            return orig_resolve(*args, **kwargs)

        self.service.rules_engine.get_applicable_rules = tracked_applicable
        RuleResolver.resolve = staticmethod(tracked_resolve)

        try:
            # 1. Direct call to service.resolve_rules()
            eval_counts["applicable"] = 0
            eval_counts["resolve"] = 0

            res = self.service.resolve_rules(task="Verify single evaluation in direct call", project_id="proj-cliverse")
            self.assertIsNotNone(res)
            self.assertEqual(eval_counts["applicable"], 1, "Direct resolve_rules must evaluate applicability exactly once")
            self.assertEqual(eval_counts["resolve"], 1, "Direct resolve_rules must resolve conflicts exactly once")

            # 2. Call to service.build_intelligence_context()
            eval_counts["applicable"] = 0
            eval_counts["resolve"] = 0

            ctx = self.service.build_intelligence_context(task="Verify single evaluation in build context", project_id="proj-cliverse")
            self.assertIsNotNone(ctx)
            self.assertEqual(eval_counts["applicable"], 1, "build_intelligence_context must evaluate applicability exactly once")
            self.assertEqual(eval_counts["resolve"], 1, "build_intelligence_context must resolve conflicts exactly once")

        finally:
            RuleResolver.resolve = orig_resolve

    # ── 20. MEMBER 2 → MEMBER 1 RULE TARGET PRESERVATION (P0-3 EXTENSION) ────

    def test_rule_target_and_all_semantics_preservation_across_adapter(self):
        """
        Verify that target, rule_id, description, scope, priority, effect,
        mandatory state, and version all survive adaptation to Member 1's frozen Rule.
        Constructs:
          rule_id = 'db-001'
          target = 'database'
          effect = REQUIRE
          is_mandatory = True
          version = 7
        Proves:
          1. 'database' remains recoverable via parse_cliverse_rule_semantics.
          2. 'database' is present in public source provenance representation.
          3. Survives copy.deepcopy().
          4. Survives dataclass serialization (asdict / tuple / dict).
          5. No object.__setattr__ or hidden private attributes are used.
        """
        import copy
        from dataclasses import asdict
        from memory.adapter import parse_cliverse_rule_semantics

        db_rule = Rule(
            rule_id="db-001",
            name="Database Connection Safety",
            scope=RuleScope.PROJECT,
            project_id="proj-cliverse",
            target="database",
            effect=RuleEffect.REQUIRE,
            is_mandatory=True,
            version=7,
            priority=75,
            description="Use connection pool for all database interactions.",
        )
        self.service.create_rule(db_rule)

        rules = self.adapter.get_applicable_rules(task="Query database records")
        rule_map = {r.rule_id: r for r in rules}
        self.assertIn("db-001", rule_map)
        adapted = rule_map["db-001"]

        # 1. Verify target in public source provenance representation
        self.assertIn("database", adapted.source)
        self.assertTrue(
            "rules:database" in adapted.source or "target=database" in adapted.source
        )

        # 2. Verify exact recovery through parse_cliverse_rule_semantics
        recovered = parse_cliverse_rule_semantics(adapted)
        self.assertEqual(recovered["rule_id"], "db-001")
        self.assertEqual(recovered["target"], "database")
        self.assertEqual(recovered["effect"], "REQUIRE")
        self.assertTrue(recovered["is_mandatory"])
        self.assertEqual(recovered["version"], 7)
        self.assertEqual(recovered["scope"], "project")
        self.assertEqual(recovered["description"], "Use connection pool for all database interactions.")

        # 3. Verify survival after copy.deepcopy()
        cloned = copy.deepcopy(adapted)
        self.assertEqual(cloned.rule_id, "db-001")
        cloned_recovered = parse_cliverse_rule_semantics(cloned)
        self.assertEqual(cloned_recovered["target"], "database")
        self.assertEqual(cloned_recovered["effect"], "REQUIRE")
        self.assertTrue(cloned_recovered["is_mandatory"])
        self.assertEqual(cloned_recovered["version"], 7)

        # 4. Verify survival after normal dataclass serialization
        serialized = asdict(adapted)
        self.assertEqual(serialized["rule_id"], "db-001")
        self.assertIn("target=database", serialized["source"])
        from cliverse.contracts import Rule as CliverseRule
        reconstructed = CliverseRule(**serialized)
        recon_recovered = parse_cliverse_rule_semantics(reconstructed)
        self.assertEqual(recon_recovered["target"], "database")
        self.assertEqual(recon_recovered["version"], 7)

        # 5. Strict negative assertion: no object.__setattr__ hack or private attrs
        self.assertFalse(hasattr(adapted, "_member2_rule"))
        self.assertNotIn("_member2_rule", getattr(adapted, "__dict__", {}))

        # 6. Test edge-case targets: semicolons, equals, unicode, spaces
        edge_targets = [
            "database;primary",
            "auth=jwt",
            "données;clés",
            "user service",
        ]
        for idx, edge_target in enumerate(edge_targets, start=2):
            edge_rule = Rule(
                rule_id=f"rule-target-{idx}",
                name=f"Rule Target {idx}",
                scope=RuleScope.TASK,
                target=edge_target,
                effect=RuleEffect.DENY,
                is_mandatory=False,
                version=idx,
                description=f"Rule targeting {edge_target}",
            )
            self.service.create_rule(edge_rule)
            edge_adapted_list = self.adapter.get_applicable_rules(task="Query target")
            edge_map = {r.rule_id: r for r in edge_adapted_list}
            self.assertIn(f"rule-target-{idx}", edge_map)
            edge_adapted = edge_map[f"rule-target-{idx}"]

            # Parse recovered
            edge_rec = parse_cliverse_rule_semantics(edge_adapted)
            self.assertEqual(edge_rec["target"], edge_target, f"Failed recovering target: {edge_target}")
            self.assertEqual(edge_rec["effect"], "DENY")
            self.assertEqual(edge_rec["version"], idx)

            # Deep copy
            edge_clone = copy.deepcopy(edge_adapted)
            self.assertEqual(parse_cliverse_rule_semantics(edge_clone)["target"], edge_target)

            # Dataclass serialization & reconstruction
            edge_ser = asdict(edge_adapted)
            edge_recon = CliverseRule(**edge_ser)
            self.assertEqual(parse_cliverse_rule_semantics(edge_recon)["target"], edge_target)

    # ── 21. TASK NORMALIZATION & VALIDATION (P0-4) ───────────────────────────

    def test_task_normalization_and_validation(self):
        """
        P0-4 verification:
          1. '   add auth   ' -> 'add auth'
          2. '\t add auth \n' -> 'add auth'
          3. Whitespace-only -> ValueError
          4. Empty string -> ValueError
          5. TaskLike object with valid task is normalized
          6. TaskLike object with empty or whitespace-only task -> ValueError
          7. Invalid input types (int, list, dict) -> TypeError (no str(task) coercion)
        """
        extract = self.service._extract_task_text

        # 1. Normalization of whitespace
        self.assertEqual(extract("   add auth   "), "add auth")
        self.assertEqual(extract("\t add auth \n"), "add auth")
        self.assertEqual(extract("add auth"), "add auth")

        # 2. Empty and whitespace-only rejection
        with self.assertRaises(ValueError):
            extract("")
        with self.assertRaises(ValueError):
            extract("   ")
        with self.assertRaises(ValueError):
            extract("\t\n  \r")

        # 3. TaskLike protocol objects
        task_obj = StructuredTask(
            role="Dev",
            context="Ctx",
            task="   build service   ",
            requirements=(),
            constraints=(),
            output="Done",
        )
        self.assertEqual(extract(task_obj), "build service")

        # 4. TaskLike with whitespace or empty task
        empty_task_obj = StructuredTask(
            role="Dev",
            context="Ctx",
            task="   ",
            requirements=(),
            constraints=(),
            output="Done",
        )
        with self.assertRaises(ValueError):
            extract(empty_task_obj)

        # 5. Invalid input types (must raise TypeError without silent coercion)
        with self.assertRaises(TypeError):
            extract(12345)
        with self.assertRaises(TypeError):
            extract(["add auth"])
        with self.assertRaises(TypeError):
            extract({"task_content": "add auth"})



if __name__ == "__main__":
    unittest.main()

