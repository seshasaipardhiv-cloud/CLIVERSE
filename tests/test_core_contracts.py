import sys
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from cliverse.contracts import (
    AuthorizationDecision,
    AuthorizationDenied,
    ContextBundle,
    Decision,
    InvalidAuthorizationDecision,
    StructuredTask,
    require_authorized,
)


class ContractTests(unittest.TestCase):
    def test_structured_task_serializes_all_prompt_sections(self):
        task = StructuredTask(
            role="Engineer",
            context="Python CLI",
            task="Add a command",
            requirements=("Use argparse",),
            constraints=("No network calls",),
            output="Code and tests",
        )

        self.assertEqual(
            task.as_dict(),
            {
                "role": "Engineer",
                "context": "Python CLI",
                "task": "Add a command",
                "requirements": ["Use argparse"],
                "constraints": ["No network calls"],
                "output": "Code and tests",
            },
        )

    def test_empty_context_requires_provenance(self):
        empty = ContextBundle.empty("No memory provider is configured.")
        self.assertEqual(empty.items, ())
        self.assertEqual(empty.provenance, ("No memory provider is configured.",))
        with self.assertRaises(ValueError):
            ContextBundle.empty(" ")

    def test_authorization_fails_closed_and_warn_requires_confirmation(self):
        require_authorized(AuthorizationDecision(Decision.ALLOW, "Allowed"))

        warning = AuthorizationDecision(Decision.WARN, "Review required", True)
        with self.assertRaises(AuthorizationDenied):
            require_authorized(warning)
        require_authorized(warning, warning_confirmed=True)

        blocked = AuthorizationDecision(Decision.BLOCK, "Denied")
        with self.assertRaises(AuthorizationDenied):
            require_authorized(blocked, warning_confirmed=True)

    def test_invalid_authorizer_output_is_not_permitted(self):
        invalid = AuthorizationDecision("UNKNOWN", "Bad response")  # type: ignore[arg-type]
        with self.assertRaises(InvalidAuthorizationDecision):
            require_authorized(invalid)


if __name__ == "__main__":
    unittest.main()
