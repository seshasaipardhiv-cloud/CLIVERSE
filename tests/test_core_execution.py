import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from cliverse.contracts import (
    AuthorizationDecision,
    AuthorizationDenied,
    AuthorizationRequest,
    Decision,
)
from cliverse.execution import (
    AuthorizationUnavailable,
    CliExecutionFailed,
    CliTimeout,
    CliUnavailable,
    InvalidProcessRequest,
    ProcessRequest,
    execute_guarded,
)


class FakeAuthorizer:
    def __init__(self, decision):
        self.decision = decision
        self.requests = []

    def authorize(self, request: AuthorizationRequest):
        self.requests.append(request)
        return self.decision


class GuardedExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def request(self, *arguments, **overrides):
        values = {
            "executable": sys.executable,
            "arguments": tuple(arguments),
            "project_root": str(self.root),
            "identity": "test-agent",
        }
        values.update(overrides)
        return ProcessRequest(**values)

    def test_missing_authorizer_blocks_execution(self):
        with self.assertRaises(AuthorizationUnavailable):
            execute_guarded(self.request("-c", "print('must not run')"), None)

    def test_blocked_authorization_prevents_process_start(self):
        marker = self.root / "executed"
        authorizer = FakeAuthorizer(AuthorizationDecision(Decision.BLOCK, "Not permitted"))
        with self.assertRaises(AuthorizationDenied):
            execute_guarded(
                self.request("-c", "from pathlib import Path; Path('executed').touch()"),
                authorizer,
            )
        self.assertFalse(marker.exists())
        self.assertEqual(authorizer.requests[0].operation, "execute")
        self.assertEqual(
            authorizer.requests[0].executable,
            str(Path(sys.executable).resolve()),
        )

    def test_warn_requires_separate_confirmation(self):
        marker = self.root / "executed"
        authorizer = FakeAuthorizer(AuthorizationDecision(Decision.WARN, "Review command", True))
        with self.assertRaises(AuthorizationDenied):
            execute_guarded(
                self.request(
                    "-c",
                    "from pathlib import Path; Path('executed').touch()",
                ),
                authorizer,
            )
        self.assertFalse(marker.exists())

        confirmed = execute_guarded(
            self.request(
                "-c",
                "from pathlib import Path; Path('executed').touch()",
                warning_confirmed=True,
            ),
            authorizer,
        )
        self.assertTrue(marker.exists())
        self.assertEqual(confirmed.authorization_decision, "WARN")

    def test_arguments_are_not_shell_interpreted_and_environment_is_scoped(self):
        authorizer = FakeAuthorizer(AuthorizationDecision(Decision.ALLOW, "Allowed"))
        argument = "one; touch should-not-exist"
        with patch.dict(os.environ, {"CLIVERSE_PARENT_SECRET": "do-not-forward"}):
            result = execute_guarded(
                self.request(
                    "-c",
                    "import os, sys; print(sys.argv[1]); print(os.getenv('CLIVERSE_PARENT_SECRET'))",
                    argument,
                    environment={"CLIVERSE_ALLOWED": "yes"},
                ),
                authorizer,
            )

        self.assertEqual(result.stdout.splitlines(), [argument, "None"])
        self.assertFalse((self.root / "should-not-exist").exists())

    def test_cli_timeout_and_nonzero_exit_are_explicit_failures(self):
        authorizer = FakeAuthorizer(AuthorizationDecision(Decision.ALLOW, "Allowed"))
        with self.assertRaises(CliTimeout):
            execute_guarded(
                self.request(
                    "-c",
                    "import time; time.sleep(1)",
                    timeout_seconds=0.1,
                ),
                authorizer,
            )

        with self.assertRaises(CliExecutionFailed) as raised:
            execute_guarded(
                self.request("-c", "raise SystemExit(7)"),
                authorizer,
            )
        self.assertEqual(raised.exception.result.returncode, 7)

    def test_bad_executable_and_reserved_environment_are_rejected(self):
        authorizer = FakeAuthorizer(AuthorizationDecision(Decision.ALLOW, "Allowed"))
        with self.assertRaises(CliUnavailable):
            execute_guarded(
                self.request("-c", "pass", executable="cliverse-command-not-installed"),
                authorizer,
            )
        with self.assertRaises(InvalidProcessRequest):
            execute_guarded(
                self.request("-c", "pass", environment={"PATH": "/tmp"}),
                authorizer,
            )


if __name__ == "__main__":
    unittest.main()
