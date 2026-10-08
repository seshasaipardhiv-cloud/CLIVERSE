"""
Stage 5.1: Safety + Contract Hardening Test Suite
===================================================
Member 2 (RAG + Rules) — CLIVERSE

Validates the strict semantic contract introduced in Stage 5.1:

  FIX 1/3/4 — ERROR must never look like SUCCESS
    - Memory OK_WITH_RESULTS vs OK_EMPTY vs ERROR are strictly distinct.
    - Rules OK_WITH_RESULTS vs OK_EMPTY vs ERROR are strictly distinct.

  FIX 5 — REQUIRE semantics
    - REQUIRE represents a positive prerequisite constraint (not just DENY).

  FIX 7 — TaskLike protocol
    - StructuredTask-compatible objects flow through the facade cleanly.

  FIX 9 — Failure injection
    - Memory failure → memory_status=ERROR (never "no relevant memory").
    - Rules failure → rules_status=ERROR, rule_decision=UNKNOWN (never ALLOW).

  FIX 10 — Integration contract
    - Full StructuredTask-like object → LayaIntelligenceContext.

  FIX 11 — Determinism
    - Repeated calls produce identical memory_status, rules_status,
      rule_decision, decision, explanations, and combined context.

Tests:
  - test_memory_ok_empty_not_error
  - test_memory_error_not_described_as_empty
  - test_rules_ok_empty_not_error
  - test_rules_error_not_described_as_allow
  - test_failed_memory_healthy_rules
  - test_healthy_memory_failed_rules
  - test_both_failed
  - test_both_healthy_with_results
  - test_healthy_memory_no_matching_rules
  - test_require_effect_maps_to_require_decision
  - test_require_vs_deny_semantics
  - test_structured_task_contract
  - test_task_like_protocol_check
  - test_determinism_with_all_status_fields
  - test_error_states_produce_different_serialized_output_from_empty
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
    RuleDecision,
    SubsystemStatus,
    TaskLike,
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


# ---------------------------------------------------------------------------
# Minimal StructuredTask-compatible test double (mirrors Member 1 contract)
# ---------------------------------------------------------------------------

class _MinimalStructuredTask:
    """
    Minimal test double compatible with Member 1's StructuredTask.
    Satisfies the TaskLike protocol (has .task and .as_dict()).
    """

    def __init__(
        self,
        task: str,
        role: str = "developer",
        context: str = "",
        requirements: str = "",
        constraints: str = "",
        output: str = "",
    ):
        self.task = task
        self.role = role
        self.context = context
        self.requirements = requirements
        self.constraints = constraints
        self.output = output

    def as_dict(self):
        return {
            "role": self.role,
            "context": self.context,
            "task": self.task,
            "requirements": self.requirements,
            "constraints": self.constraints,
            "output": self.output,
        }


# ---------------------------------------------------------------------------
# Base test setup
# ---------------------------------------------------------------------------

class Stage51HardeningBase(unittest.TestCase):
    """Shared setUp / tearDown for Stage 5.1 hardening tests."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cliverse_51_")
        db_path = Path(self.temp_dir) / "hardening.db"
        self.storage = SQLiteMemoryStorage(db_path=str(db_path))
        self.embedding_provider = LocalBaselineEmbeddingProvider(dimension=64)
        self.ingestion = IngestionPipeline(
            storage=self.storage,
            embedding_provider=self.embedding_provider,
        )
        self.retrieval = RetrievalService(
            storage=self.storage,
            embedding_provider=self.embedding_provider,
        )
        project_rules_dir = Path(self.temp_dir) / ".cliverse" / "rules"
        global_rules_dir = Path(self.temp_dir) / ".envcore" / "rules" / "global"
        self.rule_store = RuleStore(
            project_rules_dir=project_rules_dir,
            global_rules_dir=global_rules_dir,
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

    # helpers
    def _make_broken_retrieval_service(self):
        """Returns a RetrievalService whose retrieve_context always raises."""
        broken = RetrievalService(storage=self.storage)
        broken.retrieve_context = lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("Simulated storage failure")
        )
        return broken

    def _make_broken_rules_engine(self):
        """Returns a RulesEngine whose get_applicable_rules always raises."""
        broken = RulesEngine(storage=self.rule_store)
        broken.get_applicable_rules = lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("Simulated rules DB failure")
        )
        return broken


# ---------------------------------------------------------------------------
# FIX 4 — Memory OK_EMPTY vs ERROR
# ---------------------------------------------------------------------------

class TestMemoryStatusSemantics(Stage51HardeningBase):

    def test_memory_ok_empty_not_error(self):
        """CASE A: Memory works, no matching chunks → OK_EMPTY (not ERROR)."""
        intel = self.service.build_intelligence_context(
            task="Totally unindexed topic",
            project_id="proj-empty",
        )
        self.assertEqual(intel.memory_status, SubsystemStatus.OK_EMPTY)
        self.assertEqual(intel.metadata.get("memory_status"), "OK_EMPTY")
        self.assertEqual(len(intel.memory_context.items), 0)
        # Must NOT surface an error message in the prompt
        self.assertNotIn("subsystem error", intel.combined_laya_context.lower())
        # Must surface the canonical "no relevant memory" phrasing
        self.assertIn("No relevant project memory found", intel.combined_laya_context)

    def test_memory_error_not_described_as_empty(self):
        """CASE B: Memory retrieval raises → ERROR status, explicit error text."""
        svc = LayaIntelligenceService(
            retrieval_service=self._make_broken_retrieval_service(),
            rules_engine=self.rules_engine,
        )
        intel = svc.build_intelligence_context(task="Any task")

        self.assertEqual(intel.memory_status, SubsystemStatus.ERROR)
        self.assertEqual(intel.metadata.get("memory_status"), "ERROR")
        self.assertIn("memory_error", intel.metadata)
        self.assertIn("Simulated storage failure", intel.metadata["memory_error"])
        self.assertEqual(len(intel.memory_context.items), 0)

        # Must NOT say "no relevant memory" — that would be a lie
        combined = intel.combined_laya_context
        self.assertNotIn("No relevant project memory found", combined)
        # Must surface the explicit error
        self.assertIn("Memory subsystem error", combined)

    def test_memory_ok_empty_vs_error_produce_different_outputs(self):
        """OK_EMPTY and ERROR must produce detectably different serialized outputs."""
        # OK_EMPTY
        intel_empty = self.service.build_intelligence_context(
            task="Unindexed", project_id="proj-e"
        )
        # ERROR
        svc = LayaIntelligenceService(
            retrieval_service=self._make_broken_retrieval_service(),
            rules_engine=self.rules_engine,
        )
        intel_error = svc.build_intelligence_context(task="Any task")

        empty_dict = intel_empty.model_dump()
        error_dict = intel_error.model_dump()

        self.assertNotEqual(
            empty_dict["memory_status"], error_dict["memory_status"],
            "OK_EMPTY and ERROR must produce different memory_status values.",
        )
        self.assertNotEqual(
            empty_dict["combined_laya_context"],
            error_dict["combined_laya_context"],
            "OK_EMPTY and ERROR must produce different combined_laya_context.",
        )


# ---------------------------------------------------------------------------
# FIX 3 — Rules OK_EMPTY vs ERROR
# ---------------------------------------------------------------------------

class TestRulesStatusSemantics(Stage51HardeningBase):

    def test_rules_ok_empty_allows(self):
        """CASE A: Rules engine works, no applicable rule → OK_EMPTY + ALLOW."""
        intel = self.service.build_intelligence_context(
            task="Build feature with no rules",
            project_id="proj-norules",
        )
        self.assertEqual(intel.rules_status, SubsystemStatus.OK_EMPTY)
        self.assertEqual(intel.metadata.get("rules_status"), "OK_EMPTY")
        self.assertEqual(intel.rule_decision, RuleDecision.ALLOW)
        self.assertEqual(intel.decision, "ALLOW")
        # Combined output must say no applicable rules
        self.assertIn("No applicable engineering rules", intel.combined_laya_context)
        # Must NOT say rules engine error
        self.assertNotIn("Rules subsystem error", intel.combined_laya_context)

    def test_rules_error_produces_unknown_not_allow(self):
        """CASE B: Rules engine raises → ERROR status + UNKNOWN decision (never ALLOW)."""
        svc = LayaIntelligenceService(
            retrieval_service=self.retrieval,
            rules_engine=self._make_broken_rules_engine(),
        )
        intel = svc.build_intelligence_context(task="Build feature")

        self.assertEqual(intel.rules_status, SubsystemStatus.ERROR)
        self.assertEqual(intel.metadata.get("rules_status"), "ERROR")
        self.assertEqual(intel.rule_decision, RuleDecision.UNKNOWN)
        self.assertEqual(intel.decision, "UNKNOWN")
        self.assertIn("rules_error", intel.metadata)
        # Combined output must surface the explicit error, not silently allow
        self.assertIn("Rules subsystem error", intel.combined_laya_context)
        self.assertNotIn("No applicable engineering rules", intel.combined_laya_context)

    def test_rules_ok_empty_vs_error_produce_different_outputs(self):
        """OK_EMPTY and ERROR must produce detectably different serialized outputs."""
        intel_empty = self.service.build_intelligence_context(
            task="No rules", project_id="proj-ne"
        )
        svc = LayaIntelligenceService(
            retrieval_service=self.retrieval,
            rules_engine=self._make_broken_rules_engine(),
        )
        intel_error = svc.build_intelligence_context(task="No rules")

        empty_json = json.loads(intel_empty.model_dump_json())
        error_json = json.loads(intel_error.model_dump_json())

        self.assertNotEqual(empty_json["rules_status"], error_json["rules_status"])
        self.assertNotEqual(empty_json["rule_decision"], error_json["rule_decision"])
        self.assertNotEqual(empty_json["decision"], error_json["decision"])


# ---------------------------------------------------------------------------
# FIX 9 — Failure injection combinations
# ---------------------------------------------------------------------------

class TestFailureInjectionCombinations(Stage51HardeningBase):

    def test_failed_memory_healthy_rules(self):
        """Memory fails, rules succeed → memory ERROR, rules OK."""
        self.service.create_rule(
            Rule(
                rule_id="r-fi-1",
                name="Test Rule",
                scope=RuleScope.GLOBAL,
                description="A working rule.",
            )
        )
        svc = LayaIntelligenceService(
            retrieval_service=self._make_broken_retrieval_service(),
            rules_engine=self.rules_engine,
        )
        intel = svc.build_intelligence_context(task="Build feature")

        self.assertEqual(intel.memory_status, SubsystemStatus.ERROR)
        # Rules succeeded (one global rule applies with ENFORCE → REQUIRE)
        self.assertIn(intel.rules_status, (SubsystemStatus.OK_WITH_RESULTS, SubsystemStatus.OK_EMPTY))
        self.assertNotEqual(intel.rule_decision, RuleDecision.UNKNOWN)
        # Combined text must reflect both states
        self.assertIn("Memory subsystem error", intel.combined_laya_context)

    def test_healthy_memory_failed_rules(self):
        """Rules fail, memory succeeds → rules ERROR + UNKNOWN, memory OK."""
        self.service.store_memory(
            content="Architecture documentation for the project.",
            project_id="proj-fi",
            source_type="doc",
            source_path="arch.md",
        )
        svc = LayaIntelligenceService(
            retrieval_service=self.retrieval,
            rules_engine=self._make_broken_rules_engine(),
        )
        intel = svc.build_intelligence_context(
            task="Architecture documentation", project_id="proj-fi", min_score=0.1
        )

        self.assertEqual(intel.rules_status, SubsystemStatus.ERROR)
        self.assertEqual(intel.rule_decision, RuleDecision.UNKNOWN)
        self.assertEqual(intel.decision, "UNKNOWN")
        self.assertNotEqual(intel.memory_status, SubsystemStatus.ERROR)
        self.assertIn("Rules subsystem error", intel.combined_laya_context)

    def test_both_failed(self):
        """Both memory and rules fail → both ERROR, rule_decision=UNKNOWN."""
        svc = LayaIntelligenceService(
            retrieval_service=self._make_broken_retrieval_service(),
            rules_engine=self._make_broken_rules_engine(),
        )
        intel = svc.build_intelligence_context(task="Double failure scenario")

        self.assertEqual(intel.memory_status, SubsystemStatus.ERROR)
        self.assertEqual(intel.rules_status, SubsystemStatus.ERROR)
        self.assertEqual(intel.rule_decision, RuleDecision.UNKNOWN)
        self.assertEqual(intel.decision, "UNKNOWN")
        self.assertIn("Memory subsystem error", intel.combined_laya_context)
        self.assertIn("Rules subsystem error", intel.combined_laya_context)
        # Must not describe it as successful empty states
        self.assertNotIn("No relevant project memory found", intel.combined_laya_context)
        self.assertNotIn("No applicable engineering rules", intel.combined_laya_context)

    def test_both_healthy_with_results(self):
        """Both subsystems healthy with actual data → OK_WITH_RESULTS for both."""
        self.service.store_memory(
            content="Core architecture and database configuration notes.",
            project_id="proj-healthy",
            source_type="doc",
            source_path="core.md",
        )
        self.service.create_rule(
            Rule(
                rule_id="r-healthy",
                name="Standard Rule",
                scope=RuleScope.PROJECT,
                project_id="proj-healthy",
                description="Follow team standards.",
                effect=RuleEffect.WARN,
            )
        )
        intel = self.service.build_intelligence_context(
            task="Database architecture", project_id="proj-healthy", min_score=0.1
        )

        self.assertEqual(intel.memory_status, SubsystemStatus.OK_WITH_RESULTS)
        self.assertEqual(intel.rules_status, SubsystemStatus.OK_WITH_RESULTS)
        self.assertIn(intel.rule_decision, (RuleDecision.ALLOW, RuleDecision.WARN))
        self.assertGreater(len(intel.memory_context.items), 0)
        self.assertGreater(len(intel.applicable_rules), 0)

    def test_healthy_memory_no_matching_rules(self):
        """Memory has data, no applicable rules → OK_WITH_RESULTS + OK_EMPTY + ALLOW."""
        self.service.store_memory(
            content="Event-driven microservices design patterns.",
            project_id="proj-nomatch",
            source_type="doc",
            source_path="patterns.md",
        )
        # No rules stored
        intel = self.service.build_intelligence_context(
            task="Event-driven microservices", project_id="proj-nomatch", min_score=0.1
        )

        self.assertEqual(intel.memory_status, SubsystemStatus.OK_WITH_RESULTS)
        self.assertEqual(intel.rules_status, SubsystemStatus.OK_EMPTY)
        self.assertEqual(intel.rule_decision, RuleDecision.ALLOW)
        self.assertEqual(intel.decision, "ALLOW")


# ---------------------------------------------------------------------------
# FIX 5 — REQUIRE semantics
# ---------------------------------------------------------------------------

class TestRequireSemantics(Stage51HardeningBase):

    def test_require_effect_maps_to_require_decision(self):
        """A rule with effect=REQUIRE produces rule_decision=REQUIRE (not DENY, not ALLOW)."""
        self.service.create_rule(
            Rule(
                rule_id="r-require",
                name="Tests Must Pass",
                scope=RuleScope.PROJECT,
                project_id="proj-req",
                description="Tests must pass before completion.",
                effect=RuleEffect.REQUIRE,
            )
        )
        intel = self.service.build_intelligence_context(
            task="Complete implementation", project_id="proj-req"
        )

        self.assertEqual(intel.rule_decision, RuleDecision.REQUIRE)
        self.assertEqual(intel.decision, "REQUIRE")
        # Combined text should surface it as a prerequisite constraint
        self.assertIn("Decision: REQUIRE", intel.combined_laya_context)
        self.assertIn("Prerequisite Constraint", intel.combined_laya_context)
        # Must NOT say DENY
        self.assertNotIn("Decision: DENY", intel.combined_laya_context)

    def test_enforce_effect_maps_to_require_decision(self):
        """ENFORCE is a canonical synonym of REQUIRE → must map to RuleDecision.REQUIRE."""
        self.service.create_rule(
            Rule(
                rule_id="r-enforce",
                name="Use TypeScript",
                scope=RuleScope.PROJECT,
                project_id="proj-ts",
                description="All new files must use TypeScript.",
                effect=RuleEffect.ENFORCE,
            )
        )
        intel = self.service.build_intelligence_context(
            task="Create new module", project_id="proj-ts"
        )

        self.assertEqual(intel.rule_decision, RuleDecision.REQUIRE)
        self.assertEqual(intel.decision, "REQUIRE")

    def test_require_vs_deny_semantics(self):
        """REQUIRE and DENY must produce different decisions and different prompt text."""
        # REQUIRE rule
        self.service.create_rule(
            Rule(
                rule_id="r-req-2",
                name="Tests must pass",
                scope=RuleScope.PROJECT,
                project_id="proj-req2",
                description="Run tests before merging.",
                effect=RuleEffect.REQUIRE,
            )
        )
        intel_req = self.service.build_intelligence_context(
            task="Merge pull request", project_id="proj-req2"
        )

        # DENY rule (separate project)
        self.service.create_rule(
            Rule(
                rule_id="r-deny-2",
                name="No rm -rf",
                scope=RuleScope.PROJECT,
                project_id="proj-deny2",
                description="Never run rm -rf /.",
                effect=RuleEffect.DENY,
            )
        )
        intel_deny = self.service.build_intelligence_context(
            task="Clean system", project_id="proj-deny2"
        )

        self.assertEqual(intel_req.rule_decision, RuleDecision.REQUIRE)
        self.assertEqual(intel_deny.rule_decision, RuleDecision.DENY)
        self.assertNotEqual(intel_req.decision, intel_deny.decision)
        self.assertIn("Prerequisite Constraint", intel_req.combined_laya_context)
        self.assertIn("Decision: DENY", intel_deny.combined_laya_context)
        self.assertNotIn("Decision: DENY", intel_req.combined_laya_context)


# ---------------------------------------------------------------------------
# FIX 10 — Integration contract with StructuredTask-like object
# ---------------------------------------------------------------------------

class TestStructuredTaskContract(Stage51HardeningBase):

    def test_structured_task_contract(self):
        """
        A StructuredTask-compatible object flows through the Member 2 facade
        and produces a fully populated, serializable LayaIntelligenceContext.
        """
        # Store relevant project knowledge
        self.service.store_memory(
            content="PostgreSQL is the canonical database for all production services.",
            project_id="proj-contract",
            source_type="decision",
            source_path="decisions/db.md",
        )
        self.service.store_memory(
            content="JWT RS256 tokens are required for API authentication.",
            project_id="proj-contract",
            source_type="doc",
            source_path="docs/auth.md",
        )

        # Create applicable rules
        self.service.create_rule(
            Rule(
                rule_id="r-contract-db",
                name="Use PostgreSQL",
                scope=RuleScope.PROJECT,
                project_id="proj-contract",
                description="Use PostgreSQL for all database operations.",
                effect=RuleEffect.ENFORCE,
            )
        )
        self.service.create_rule(
            Rule(
                rule_id="r-contract-cli",
                name="Ask Before Installing",
                scope=RuleScope.CLI,
                cli_filter="claude-cli",
                description="Ask before installing new packages.",
                effect=RuleEffect.ASK,
            )
        )

        # Build context with a StructuredTask-like object
        task_obj = _MinimalStructuredTask(
            task="Set up JWT authentication with PostgreSQL backend",
            role="backend-developer",
            context="Initial project scaffolding",
            requirements="Must use RS256 tokens",
            constraints="No SQLite in production",
        )

        intel = self.service.build_intelligence_context(
            task=task_obj,
            project_id="proj-contract",
            cli_name="claude-cli",
            min_score=0.1,
        )

        # ── task extraction ──────────────────────────────────────────────────
        self.assertEqual(
            intel.task,
            "Set up JWT authentication with PostgreSQL backend",
        )
        self.assertEqual(intel.project_id, "proj-contract")
        self.assertEqual(intel.cli_name, "claude-cli")

        # ── memory results ───────────────────────────────────────────────────
        self.assertGreater(len(intel.memory_context.items), 0)
        self.assertEqual(intel.memory_status, SubsystemStatus.OK_WITH_RESULTS)

        # ── provenance ───────────────────────────────────────────────────────
        self.assertTrue(len(intel.context_sources) > 0)

        # ── applicable rules ─────────────────────────────────────────────────
        rule_ids = {r.rule_id for r in intel.applicable_rules}
        self.assertIn("r-contract-db", rule_ids)
        self.assertIn("r-contract-cli", rule_ids)
        self.assertEqual(intel.rules_status, SubsystemStatus.OK_WITH_RESULTS)

        # ── rule_decision: ASK wins over ENFORCE (severity ASK > REQUIRE) ───
        self.assertEqual(intel.rule_decision, RuleDecision.ASK)
        self.assertEqual(intel.decision, "ASK")

        # ── rule_decision is NOT security/execution authorization ─────────────
        # (checked by ensuring the field name is rule_decision, not security_decision)
        dumped = intel.model_dump()
        self.assertIn("rule_decision", dumped)
        self.assertNotIn("security_decision", dumped)
        self.assertNotIn("execution_authorized", dumped)

        # ── full serialization round-trip ─────────────────────────────────────
        json_str = intel.model_dump_json()
        reparsed = json.loads(json_str)
        self.assertEqual(reparsed["task"], intel.task)
        self.assertEqual(reparsed["project_id"], "proj-contract")
        self.assertEqual(reparsed["cli_name"], "claude-cli")
        self.assertEqual(reparsed["memory_status"], "OK_WITH_RESULTS")
        self.assertEqual(reparsed["rules_status"], "OK_WITH_RESULTS")
        self.assertEqual(reparsed["rule_decision"], "ASK")
        self.assertEqual(reparsed["decision"], "ASK")

        # ── metadata carries task structure from as_dict() ────────────────────
        self.assertIn("role", intel.metadata)
        self.assertEqual(intel.metadata["role"], "backend-developer")

        # ── combined text is populated ────────────────────────────────────────
        self.assertIn("### PROJECT CONTEXT", intel.combined_laya_context)
        self.assertIn("### APPLICABLE RULES", intel.combined_laya_context)
        self.assertIn("### RULE RESOLUTION", intel.combined_laya_context)
        self.assertIn("Decision: ASK", intel.combined_laya_context)

    def test_task_like_protocol_recognized(self):
        """_MinimalStructuredTask satisfies the TaskLike protocol (runtime check)."""
        task_obj = _MinimalStructuredTask(task="Protocol compliance check")
        self.assertIsInstance(task_obj, TaskLike)

    def test_plain_string_task_still_works(self):
        """Plain str must continue to work as a task input (backward compat)."""
        intel = self.service.build_intelligence_context(
            task="Plain string task input", project_id="proj-str"
        )
        self.assertIsInstance(intel, LayaIntelligenceContext)
        self.assertEqual(intel.task, "Plain string task input")


# ---------------------------------------------------------------------------
# FIX 11 — Determinism across repeated calls
# ---------------------------------------------------------------------------

class TestDeterminism(Stage51HardeningBase):

    def test_determinism_with_all_status_fields(self):
        """
        Repeated identical calls produce identical values for every status field,
        rule_decision, decision, combined context, and explanations.
        """
        self.service.store_memory(
            content="Persistent system configuration and deployment policies.",
            project_id="proj-det",
            source_type="doc",
            source_path="config.md",
        )
        self.service.create_rule(
            Rule(
                rule_id="r-det",
                name="Configuration Rule",
                scope=RuleScope.PROJECT,
                project_id="proj-det",
                description="Follow deployment standards.",
                effect=RuleEffect.WARN,
            )
        )

        first = self.service.build_intelligence_context(
            task="System configuration review",
            project_id="proj-det",
            min_score=0.0,
        )

        for i in range(10):
            nxt = self.service.build_intelligence_context(
                task="System configuration review",
                project_id="proj-det",
                min_score=0.0,
            )
            self.assertEqual(first.memory_status, nxt.memory_status, f"Run {i}: memory_status differs")
            self.assertEqual(first.rules_status, nxt.rules_status, f"Run {i}: rules_status differs")
            self.assertEqual(first.rule_decision, nxt.rule_decision, f"Run {i}: rule_decision differs")
            self.assertEqual(first.decision, nxt.decision, f"Run {i}: decision differs")
            self.assertEqual(
                len(first.memory_context.items),
                len(nxt.memory_context.items),
                f"Run {i}: memory item count differs",
            )
            self.assertEqual(
                [r.rule_id for r in first.applicable_rules],
                [r.rule_id for r in nxt.applicable_rules],
                f"Run {i}: applicable_rules order differs",
            )
            self.assertEqual(
                first.combined_laya_context,
                nxt.combined_laya_context,
                f"Run {i}: combined_laya_context differs",
            )
            self.assertEqual(
                first.rule_explanations,
                nxt.rule_explanations,
                f"Run {i}: rule_explanations differ",
            )

    def test_error_state_determinism(self):
        """Error state is also deterministic — repeated failure calls produce same ERROR output."""
        svc = LayaIntelligenceService(
            retrieval_service=self._make_broken_retrieval_service(),
            rules_engine=self.rules_engine,
        )
        first = svc.build_intelligence_context(task="Error determinism check")

        for i in range(5):
            nxt = svc.build_intelligence_context(task="Error determinism check")
            self.assertEqual(first.memory_status, nxt.memory_status, f"Run {i}: memory_status differs")
            self.assertEqual(first.decision, nxt.decision, f"Run {i}: decision differs")


if __name__ == "__main__":
    unittest.main()
