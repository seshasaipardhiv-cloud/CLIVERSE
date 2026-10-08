import json
import subprocess
import sys
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from cliverse.contracts import ContextBundle, ContextItem, Rule
from cliverse.planning import (
    MemoryProviderUnavailable,
    PlanningError,
    PlanningRequest,
    RequestPlanner,
)


class FakeMemoryProvider:
    def __init__(self):
        self.context_calls = 0
        self.rule_calls = 0

    def retrieve_context(self, task):
        self.context_calls += 1
        return ContextBundle(
            items=(ContextItem("arch-1", "Use the existing service layer.", "docs/architecture.md"),),
            provenance=("Local project index",),
            retrieved_at="2026-10-08T00:00:00+00:00",
        )

    def get_applicable_rules(self, task):
        self.rule_calls += 1
        return [Rule("rule-1", "Use SQLite.", "project", 10, "rules/project.md")]

    def store_memory(self, data):
        raise NotImplementedError

    def search_memory(self, query):
        raise NotImplementedError


class BrokenMemoryProvider(FakeMemoryProvider):
    def retrieve_context(self, task):
        raise RuntimeError("retrieval failed")


class PlanningTests(unittest.TestCase):
    def test_planner_returns_structured_task_with_context_and_rules(self):
        provider = FakeMemoryProvider()
        result = RequestPlanner(provider).plan(
            PlanningRequest(
                task="Add a user session command",
                context="The project uses Python.",
                requirements=("Persist sessions",),
                constraints=("Do not call hosted services",),
            )
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.task.role, "AI coding assistant")
        self.assertIn("existing service layer", result.task.context)
        self.assertEqual(result.task.requirements, ("Persist sessions",))
        self.assertIn("Use SQLite.", result.task.constraints[-1])
        self.assertEqual(result.applicable_rule_ids, ("rule-1",))
        self.assertEqual(provider.context_calls, 1)
        self.assertEqual(provider.rule_calls, 1)

    def test_missing_provider_is_not_silently_treated_as_empty(self):
        with self.assertRaises(MemoryProviderUnavailable):
            RequestPlanner().plan(PlanningRequest(task="Add a feature"))

    def test_context_free_mode_is_explicit_and_reported(self):
        result = RequestPlanner(allow_context_free=True).plan(
            PlanningRequest(task="Add a feature")
        )
        self.assertTrue(result.ready)
        self.assertTrue(any("Context-free mode explicitly selected" in item for item in result.context_provenance))

    def test_missing_task_and_unresolved_questions_block_planning(self):
        missing = RequestPlanner(allow_context_free=True).plan(PlanningRequest(task=" "))
        self.assertFalse(missing.ready)
        self.assertIsNone(missing.task)
        self.assertIn("What task should CLIVERSE plan?", missing.clarification_questions)

        unresolved = RequestPlanner(allow_context_free=True).plan(
            PlanningRequest(
                task="Add authentication",
                clarification_questions=("Which identity provider is required?",),
            )
        )
        self.assertFalse(unresolved.ready)
        self.assertIsNone(unresolved.task)
        self.assertEqual(
            unresolved.clarification_questions,
            ("Which identity provider is required?",),
        )

    def test_provider_failure_and_invalid_provenance_are_visible(self):
        with self.assertRaisesRegex(RuntimeError, "retrieval failed"):
            RequestPlanner(BrokenMemoryProvider()).plan(
                PlanningRequest(task="Add a feature")
            )

        class InvalidProvider(FakeMemoryProvider):
            def retrieve_context(self, task):
                return ContextBundle((), (), "2026-10-08T00:00:00+00:00")

        with self.assertRaisesRegex(PlanningError, "provenance"):
            RequestPlanner(InvalidProvider()).plan(PlanningRequest(task="Add a feature"))

    def test_cli_requires_and_reports_explicit_context_free_mode(self):
        repository = Path(__file__).resolve().parents[1]
        missing_mode = subprocess.run(
            [
                sys.executable,
                str(repository / "env.py"),
                "plan",
                "Add a CLI feature",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(missing_mode.returncode, 2)
        self.assertEqual(json.loads(missing_mode.stderr)["code"], "MEMORY_PROVIDER_UNAVAILABLE")

        planned = subprocess.run(
            [
                sys.executable,
                str(repository / "env.py"),
                "plan",
                "Add a CLI feature",
                "--context",
                "Python 3.11 project",
                "--requirement",
                "Use standard library",
                "--without-memory",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(planned.returncode, 0, planned.stderr)
        payload = json.loads(planned.stdout)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["task"]["task"], "Add a CLI feature")
        self.assertEqual(payload["task"]["requirements"], ["Use standard library"])
        self.assertTrue(any("Context-free mode" in item for item in payload["context_provenance"]))

        clarification = subprocess.run(
            [
                sys.executable,
                str(repository / "env.py"),
                "plan",
                "Add authentication",
                "--clarification",
                "Which identity provider?",
                "--without-memory",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(clarification.returncode, 0, clarification.stderr)
        self.assertEqual(
            json.loads(clarification.stdout)["status"],
            "needs_clarification",
        )


if __name__ == "__main__":
    unittest.main()
