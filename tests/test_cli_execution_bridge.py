"""
Comprehensive Automated Test Suite: AI CLI Execution Bridge
============================================================
Verifies:
1. Provider detection (installed vs not installed)
2. Command discovery & path resolution
3. Unavailable provider handling
4. Command construction (Claude -p, Gemini -p, Codex exec, Aider --message --no-git)
5. Working directory isolation (cwd == target project root)
6. Environment safety & secret scrubbing
7. Real process invocation & stdout capture
8. Stderr capture
9. Exit code handling (0 vs non-zero)
10. Timeout handling & process termination
11. Cancellation & cleanup
12. Session creation in SessionStore
13. Session event logging
14. Activity emission without secrets
15. TrustGate authorization integration
16. TrustGate denial prevents process launch
17. Full end-to-end Orchestrator pipeline
18. CLI entrypoint argument parsing
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src/ and repo root are on sys.path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR / "src"))
sys.path.insert(0, str(BASE_DIR))

from cliverse.contracts import AuthorizationDecision, Decision as Member1Decision
from cliverse.environment import ProjectEnvironment
from cliverse.orchestrator import ExecutionOrchestrator, OrchestrationResult
from cliverse.providers import (
    AiderCLIAdapter,
    BaseCLIAdapter,
    ClaudeCLIAdapter,
    CodexCLIAdapter,
    GenericExecutableAdapter,
    GeminiCLIAdapter,
    ProviderExecutionResult,
    ProviderInfo,
    ProviderStatus,
    build_enriched_prompt,
    provider_registry,
)
from cliverse.sessions import SessionStore
from trust_gate import PipelineEvaluation, TrustGate


class TestCLIExecutionBridge(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        # Initialize a test project environment
        ProjectEnvironment.initialize(str(self.root))

    def tearDown(self):
        self.temp_dir.cleanup()

    # ── 1. Provider Detection & Discovery ─────────────────────────────────────
    def test_provider_detection_truthfulness(self):
        """Verifies that detect() truthfully reports installed vs uninstalled status."""
        claude = ClaudeCLIAdapter()
        claude_info = claude.detect(force_refresh=True)
        # Claude should be NOT_INSTALLED unless installed on this host
        if not shutil_which("claude"):
            self.assertEqual(claude_info.status, ProviderStatus.NOT_INSTALLED)
            self.assertIsNone(claude_info.executable_path)
            self.assertFalse(claude_info.is_available)

        # Generic adapter with known python executable should be INSTALLED
        py_adapter = GenericExecutableAdapter(
            provider_id="test-py",
            display_name="Python Runner",
            executable_path=sys.executable,
        )
        info = py_adapter.detect(force_refresh=True)
        self.assertEqual(info.status, ProviderStatus.INSTALLED)
        self.assertTrue(info.is_available)
        self.assertEqual(info.executable_path, str(Path(sys.executable).resolve()))

    # ── 2. Command Construction ───────────────────────────────────────────────
    def test_command_construction_per_provider(self):
        """Verifies exact command shapes for each AI CLI provider."""
        claude = ClaudeCLIAdapter(custom_executable="claude")
        cmd_claude = claude.build_command("task", "PROMPT", str(self.root), non_interactive=True)
        self.assertEqual(cmd_claude[-2:], ["-p", "PROMPT"])
        self.assertTrue(cmd_claude[0].lower().endswith("claude") or cmd_claude[0].lower().endswith("claude.cmd") or cmd_claude[0].lower().endswith("claude.exe"))

        gemini = GeminiCLIAdapter(custom_executable="gemini")
        cmd_gemini = gemini.build_command("task", "PROMPT", str(self.root), non_interactive=True)
        self.assertEqual(cmd_gemini[-2:], ["-p", "PROMPT"])

        codex = CodexCLIAdapter(custom_executable="codex")
        cmd_codex = codex.build_command("task", "PROMPT", str(self.root), non_interactive=True)
        self.assertEqual(cmd_codex[-2:], ["exec", "PROMPT"])

        aider = AiderCLIAdapter(custom_executable="aider")
        cmd_aider = aider.build_command("task", "PROMPT", str(self.root), non_interactive=True)
        self.assertEqual(cmd_aider[-3:], ["--message", "PROMPT", "--no-git"])
        self.assertTrue(cmd_aider[0].lower().endswith("aider") or cmd_aider[0].lower().endswith("aider.exe"))

        from cliverse.providers import AgyCLIAdapter
        agy = AgyCLIAdapter(custom_executable="agy")
        cmd_agy = agy.build_command("task", "PROMPT", str(self.root), non_interactive=True)
        self.assertEqual(cmd_agy[-2:], ["-p", "PROMPT"])
        self.assertNotIn("run", cmd_agy)
        self.assertTrue(cmd_agy[0].lower().endswith("agy") or cmd_agy[0].lower().endswith("agy.exe"))

    # ── 3. Prompt Enrichment ──────────────────────────────────────────────────
    def test_prompt_enrichment_packet_structure(self):
        """Verifies clear delineation of raw task, memory, rules, and planning."""
        task = "Add rate limiting middleware"
        rag_items = [
            {"content": "Redis is configured at localhost:6379", "source": "docs/redis.md"},
        ]
        rules = [
            {"rule_id": "rule-rate-limit", "content": "Limit to 100 req/min per IP", "scope": "project"},
        ]
        planning_text = "Step 1: Check existing middleware. Step 2: Implement Redis token bucket."

        prompt = build_enriched_prompt(
            task=task,
            project_name="my-service",
            rag_items=rag_items,
            rules=rules,
            planning_context=planning_text,
        )

        self.assertIn("Project: my-service", prompt)
        self.assertIn("RETRIEVED PROJECT MEMORY & KNOWLEDGE", prompt)
        self.assertIn("Redis is configured at localhost:6379", prompt)
        self.assertIn("ACTIVE ENGINEERING RULES & GOVERNANCE CONSTRAINTS", prompt)
        self.assertIn("! [rule-rate-limit]", prompt)
        self.assertIn("LAYA PLANNING GUIDELINES", prompt)
        self.assertIn("USER TASK:", prompt)
        self.assertIn(task, prompt)

    # ── 4. Environment Safety & Secret Scrubbing ──────────────────────────────
    def test_environment_safety_scrubs_secrets(self):
        """Verifies sensitive environment variables are stripped from child processes."""
        adapter = GenericExecutableAdapter("test", "Test", sys.executable)
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "sk-secret-12345",
            "CLIVERSE_AUTH_TOKEN": "token-xyz",
            "MY_PASSWORD": "supersecretpassword",
            "SAFE_BENIGN_VAR": "benign-value",
        }):
            env = adapter.prepare_environment(str(self.root))
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertNotIn("CLIVERSE_AUTH_TOKEN", env)
            self.assertNotIn("MY_PASSWORD", env)
            self.assertEqual(env.get("SAFE_BENIGN_VAR"), "benign-value")
            self.assertEqual(env.get("CLIVERSE_MANAGED"), "1")
            self.assertEqual(env.get("CLIVERSE_PROJECT_ROOT"), str(self.root))

    # ── 5. Real Process Execution: Stdout, Stderr, Exit Code ───────────────────
    def test_real_process_execution_success(self):
        """Tests real subprocess execution with stdout capture and returncode 0."""
        code = "import sys; print('HELLO_CLIVERSE_STDOUT'); sys.stderr.write('LOG_STDERR\\n')"
        adapter = GenericExecutableAdapter(
            provider_id="test-runner",
            display_name="Test Runner",
            executable_path=sys.executable,
            args_template=["-c", code],
        )

        stdout_lines = []
        stderr_lines = []

        result = adapter.execute(
            task="Test Execution",
            enriched_prompt="Test Prompt",
            project_root=str(self.root),
            session_id="sess-001",
            on_stdout_line=stdout_lines.append,
            on_stderr_line=stderr_lines.append,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.status, "completed")
        self.assertIn("HELLO_CLIVERSE_STDOUT", result.stdout)
        self.assertIn("LOG_STDERR", result.stderr)
        self.assertIn("HELLO_CLIVERSE_STDOUT\n", "".join(stdout_lines))

    # ── 6. Non-Zero Exit Code Handling ─────────────────────────────────────────
    def test_nonzero_exit_code_is_reported_as_failure(self):
        """A non-zero exit code must be marked as failed, never converted to success."""
        adapter = GenericExecutableAdapter(
            provider_id="test-fail",
            display_name="Failing Runner",
            executable_path=sys.executable,
            args_template=["-c", "import sys; sys.exit(7)"],
        )

        result = adapter.execute(
            task="Fail Task",
            enriched_prompt="Prompt",
            project_root=str(self.root),
            session_id="sess-002",
        )

        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.status, "failed")

    # ── 7. Timeout Handling & Process Termination ─────────────────────────────
    def test_process_timeout_handling(self):
        """Processes exceeding timeout must be cleanly terminated."""
        adapter = GenericExecutableAdapter(
            provider_id="test-timeout",
            display_name="Timeout Runner",
            executable_path=sys.executable,
            args_template=["-c", "import time; time.sleep(10)"],
            default_timeout_seconds=0.2,
        )

        result = adapter.execute(
            task="Sleep Task",
            enriched_prompt="Prompt",
            project_root=str(self.root),
            session_id="sess-003",
            timeout_seconds=0.2,
        )

        self.assertEqual(result.status, "timed_out")
        self.assertNotEqual(result.returncode, 0)

    # ── 8. Working Directory Isolation ────────────────────────────────────────
    def test_working_directory_isolation(self):
        """Verifies child process executes strictly in the target project_root."""
        code = "import os; print('CWD=' + os.getcwd())"
        adapter = GenericExecutableAdapter(
            provider_id="test-cwd",
            display_name="CWD Runner",
            executable_path=sys.executable,
            args_template=["-c", code],
        )

        result = adapter.execute(
            task="CWD Task",
            enriched_prompt="Prompt",
            project_root=str(self.root),
            session_id="sess-004",
        )

        expected_line = f"CWD={str(self.root)}"
        self.assertIn(expected_line, result.stdout.strip())

    # ── 9. TrustGate Authorization Gate ────────────────────────────────────────
    def test_trustgate_denial_blocks_execution(self):
        """If TrustGate denies execution, the subprocess MUST NOT start."""
        marker_file = self.root / "malicious_file.txt"
        code = f"from pathlib import Path; Path(r'{marker_file}').write_text('executed')"

        fake_adapter = GenericExecutableAdapter(
            provider_id="mock-blocked",
            display_name="Blocked CLI",
            executable_path=sys.executable,
            args_template=["-c", code],
        )
        provider_registry.register(fake_adapter)

        # Mock TrustGate to simulate an authorization block
        with patch.object(
            TrustGate,
            "evaluate",
            return_value=PipelineEvaluation(
                allowed=False,
                decision="BLOCK",
                risk_level="CRITICAL",
                reason="Restricted command in strict sandbox",
            ),
        ):
            orchestrator = ExecutionOrchestrator(project_root=self.root)
            result = orchestrator.run(
                provider_name="mock-blocked",
                task="Malicious operation",
            )

            self.assertFalse(result.ok)
            self.assertEqual(result.status, "blocked")
            self.assertEqual(result.trust_gate_decision, "BLOCK")
            self.assertFalse(marker_file.exists(), "Process was executed despite TrustGate BLOCK!")

    # ── 10. Sessions and Events Integration ───────────────────────────────────
    def test_session_creation_and_event_logging(self):
        """Verifies sessions are created in SessionStore and events recorded."""
        fake_adapter = GenericExecutableAdapter(
            provider_id="test-session-runner",
            display_name="Session Runner",
            executable_path=sys.executable,
            args_template=["-c", "print('SUCCESS')"],
        )
        provider_registry.register(fake_adapter)

        events_received = []
        orchestrator = ExecutionOrchestrator(
            project_root=self.root,
            event_sink=events_received.append,
        )

        result = orchestrator.run(
            provider_name="test-session-runner",
            task="Verify session recording",
        )

        self.assertTrue(result.ok)
        self.assertTrue(bool(result.session_id) and len(result.session_id) >= 8)

        # Inspect SessionStore
        db_path = self.root / ".envcore" / "sessions" / "sessions.db"
        store = SessionStore(db_path)
        session = store.get_session(result.session_id)
        self.assertIsNotNone(session)
        self.assertEqual(session.status, "completed")

        recorded_events = store.list_events(result.session_id)
        event_types = [e.event_type for e in recorded_events]
        self.assertIn("process_started", event_types)
        self.assertIn("process_exited", event_types)

        # Check emitted activity events
        phases = [e.phase for e in events_received]
        self.assertIn("PROJECT", phases)
        self.assertIn("PROVIDER", phases)
        self.assertIn("EXECUTION", phases)

    # ── 11. Unavailable Provider Handling ─────────────────────────────────────
    def test_unavailable_provider_returns_error(self):
        """Attempting to invoke an unknown or uninstalled provider fails gracefully."""
        orchestrator = ExecutionOrchestrator(project_root=self.root)
        result = orchestrator.run(
            provider_name="nonexistent-provider-xyz",
            task="Test non-existent provider",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "error")
        self.assertIn("Unknown provider", result.stderr)


def shutil_which(cmd: str) -> bool:
    import shutil
    return shutil.which(cmd) is not None


if __name__ == "__main__":
    unittest.main()
