"""
Automated Test Suite for CLIVERSE Agy (Antigravity) Provider
============================================================
Verifies:
1. Command construction (['agy', '-p', '<prompt>'], 'run' is strictly absent)
2. Prompt forwarding (enriched prompt passed without corruption)
3. Working directory isolation (cwd == target project_root, NOT CLIVERSE root)
4. Executable discovery (PATH resolution, CLIVERSE_AGY_PATH override)
5. Stdout streaming & capture
6. Stderr streaming & capture
7. Exit code reporting (0 = completed, non-zero = failed)
8. Timeout enforcement & process termination
9. Session creation in SessionStore
10. Activity generation & event broadcasting
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR / "src"))
sys.path.insert(0, str(BASE_DIR))

from cliverse.environment import ProjectEnvironment
from cliverse.orchestrator import ExecutionOrchestrator, OrchestrationResult
from cliverse.providers import (
    AgyCLIAdapter,
    GenericExecutableAdapter,
    ProviderExecutionResult,
    ProviderInfo,
    ProviderStatus,
    build_enriched_prompt,
    provider_registry,
)
from cliverse.sessions import SessionStore


class TestAgyExecution(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp_dir.name).resolve()
        ProjectEnvironment.initialize(str(self.root))

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # ── 1. Command Construction ───────────────────────────────────────────────
    def test_agy_command_construction_exact_arguments(self):
        """
        Asserts that Agy command construction is exactly ['agy', '-p', '<prompt>']
        or the resolved executable path.
        EXPLICITLY asserts that 'run' is NOT present anywhere in the arguments.
        """
        adapter = AgyCLIAdapter(custom_executable="agy")
        prompt = "Explain the system architecture"
        cmd = adapter.build_command(
            task="Explain architecture",
            enriched_prompt=prompt,
            project_root=str(self.root),
            non_interactive=True,
        )

        # Must have exactly 3 parts: [executable, "-p", prompt]
        self.assertEqual(len(cmd), 3)
        self.assertTrue(
            cmd[0].lower().endswith("agy")
            or cmd[0].lower().endswith("agy.exe")
            or cmd[0].lower().endswith("agy.cmd")
        )
        self.assertEqual(cmd[1], "-p")
        self.assertEqual(cmd[2], prompt)

        # STRICT NEGATIVE ASSERTION: 'run' must NEVER appear
        self.assertNotIn("run", cmd)
        for arg in cmd:
            self.assertNotEqual(arg.lower().strip(), "run")

    # ── 2. Prompt Forwarding ──────────────────────────────────────────────────
    def test_agy_prompt_forwarding_integrity(self):
        """Verifies that the enriched prompt is preserved verbatim without corruption."""
        adapter = AgyCLIAdapter(custom_executable="agy")
        complex_prompt = (
            "============================================================\n"
            "CLIVERSE AI INTELLIGENCE CONTEXT\n"
            "Project: target-service\n"
            "============================================================\n"
            "USER TASK:\n"
            "Read the README and explain the architecture. Do not modify any files.\n"
            "============================================================"
        )
        cmd = adapter.build_command(
            task="Read the README",
            enriched_prompt=complex_prompt,
            project_root=str(self.root),
            non_interactive=True,
        )
        self.assertEqual(cmd[2], complex_prompt)
        self.assertIn("USER TASK:", cmd[2])
        self.assertIn("Read the README and explain the architecture", cmd[2])

    # ── 3. Working Directory Isolation ────────────────────────────────────────
    def test_agy_working_directory_isolation(self):
        """
        Verifies that when target project is A:\\project (or a test project directory),
        the child process executes with cwd == project_root, NOT CLIVERSE directory.
        """
        # Create a mock target project directory distinct from CLIVERSE
        target_project = self.root / "mock_external_project"
        target_project.mkdir(parents=True, exist_ok=True)
        (target_project / "README.md").write_text("# Mock Project Readme\nArchitecture: Microservices")

        # Use python script acting as fake agy executable
        script = "import os; print('CWD=' + os.getcwd())"
        adapter = GenericExecutableAdapter(
            provider_id="agy-cwd-test",
            display_name="Agy CWD Test",
            executable_path=sys.executable,
            args_template=["-c", script],
        )

        res = adapter.execute(
            task="Inspect cwd",
            enriched_prompt="Prompt",
            project_root=str(target_project),
            session_id="sess-cwd-001",
        )

        self.assertEqual(res.returncode, 0)
        self.assertIn(f"CWD={str(target_project)}", res.stdout)
        self.assertNotIn(str(BASE_DIR), res.stdout)

    # ── 4. Executable Discovery ───────────────────────────────────────────────
    def test_agy_executable_discovery(self):
        """Verifies discovery on PATH and respect for CLIVERSE_AGY_PATH override."""
        adapter = AgyCLIAdapter()
        info = adapter.detect(force_refresh=True)

        # On the user's host machine, agy is installed
        if info.status == ProviderStatus.INSTALLED:
            self.assertTrue(info.is_available)
            self.assertIsNotNone(info.executable_path)
            self.assertTrue(Path(info.executable_path).exists())

        # Test custom environment override
        with patch.dict(os.environ, {"CLIVERSE_AGY_PATH": sys.executable}):
            custom_adapter = AgyCLIAdapter()
            custom_info = custom_adapter.detect(force_refresh=True)
            self.assertEqual(custom_info.status, ProviderStatus.INSTALLED)
            self.assertEqual(custom_info.executable_path, str(Path(sys.executable).resolve()))

    # ── 5. Stdout Streaming & Capture ─────────────────────────────────────────
    def test_agy_stdout_capture_and_streaming(self):
        """Tests that stdout lines are captured in real-time via the streaming callback."""
        script = "import sys; print('LINE1: Architecture Overview'); print('LINE2: Subsystems OK')"
        adapter = GenericExecutableAdapter(
            provider_id="agy-stdout-test",
            display_name="Agy Stdout Test",
            executable_path=sys.executable,
            args_template=["-c", script],
        )

        captured_lines = []
        res = adapter.execute(
            task="Stream task",
            enriched_prompt="Prompt",
            project_root=str(self.root),
            session_id="sess-stdout-001",
            on_stdout_line=captured_lines.append,
        )

        self.assertEqual(res.returncode, 0)
        self.assertIn("LINE1: Architecture Overview", res.stdout)
        self.assertIn("LINE2: Subsystems OK", res.stdout)
        self.assertTrue(any("LINE1" in line for line in captured_lines))
        self.assertTrue(any("LINE2" in line for line in captured_lines))

    # ── 6. Stderr Capture ─────────────────────────────────────────────────────
    def test_agy_stderr_capture(self):
        """Tests that stderr output is captured and properly recorded."""
        script = "import sys; sys.stderr.write('WARN: Rate limit approaching\\n')"
        adapter = GenericExecutableAdapter(
            provider_id="agy-stderr-test",
            display_name="Agy Stderr Test",
            executable_path=sys.executable,
            args_template=["-c", script],
        )

        captured_err = []
        res = adapter.execute(
            task="Stderr task",
            enriched_prompt="Prompt",
            project_root=str(self.root),
            session_id="sess-stderr-001",
            on_stderr_line=captured_err.append,
        )

        self.assertIn("WARN: Rate limit approaching", res.stderr)
        self.assertTrue(any("WARN" in line for line in captured_err))

    # ── 7. Exit Code Handling ─────────────────────────────────────────────────
    def test_agy_exit_code_reporting(self):
        """Verifies that exit code 0 is completed, and non-zero exit code is failed."""
        adapter_success = GenericExecutableAdapter(
            provider_id="agy-exit-0",
            display_name="Agy Exit 0",
            executable_path=sys.executable,
            args_template=["-c", "import sys; sys.exit(0)"],
        )
        res_0 = adapter_success.execute(
            task="Success",
            enriched_prompt="Prompt",
            project_root=str(self.root),
            session_id="sess-exit-0",
        )
        self.assertEqual(res_0.returncode, 0)
        self.assertEqual(res_0.status, "completed")

        adapter_fail = GenericExecutableAdapter(
            provider_id="agy-exit-1",
            display_name="Agy Exit 1",
            executable_path=sys.executable,
            args_template=["-c", "import sys; sys.exit(2)"],
        )
        res_fail = adapter_fail.execute(
            task="Failure",
            enriched_prompt="Prompt",
            project_root=str(self.root),
            session_id="sess-exit-2",
        )
        self.assertEqual(res_fail.returncode, 2)
        self.assertEqual(res_fail.status, "failed")

    # ── 8. Timeout Enforcement ────────────────────────────────────────────────
    def test_agy_timeout_enforcement(self):
        """Verifies that an unresponsive child process is terminated and marked timed_out."""
        script = "import time; time.sleep(5)"
        adapter = GenericExecutableAdapter(
            provider_id="agy-timeout",
            display_name="Agy Timeout",
            executable_path=sys.executable,
            args_template=["-c", script],
            default_timeout_seconds=0.3,
        )

        res = adapter.execute(
            task="Timeout task",
            enriched_prompt="Prompt",
            project_root=str(self.root),
            session_id="sess-timeout-001",
            timeout_seconds=0.3,
        )

        self.assertEqual(res.status, "timed_out")
        self.assertNotEqual(res.returncode, 0)

    # ── 9. Session Creation in SessionStore ────────────────────────────────────
    def test_agy_session_creation(self):
        """Verifies that invoking agy via ExecutionOrchestrator records a valid session."""
        fake_agy = GenericExecutableAdapter(
            provider_id="agy",
            display_name="Antigravity CLI (agy)",
            executable_path=sys.executable,
            args_template=["-c", "print('AGY_SESSION_OK')"],
        )
        provider_registry.register(fake_agy)

        orchestrator = ExecutionOrchestrator(project_root=self.root)
        result = orchestrator.run(
            provider_name="agy",
            task="Read the README and explain the architecture. Do not modify any files.",
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.provider_id, "agy")
        self.assertEqual(result.status, "completed")

        # Verify session in DB
        db_path = self.root / ".envcore" / "sessions" / "sessions.db"
        store = SessionStore(db_path)
        sess = store.get_session(result.session_id)
        self.assertIsNotNone(sess)
        self.assertEqual(sess.status, "completed")
        self.assertEqual(sess.user_request, "Read the README and explain the architecture. Do not modify any files.")

        # Re-register real adapter
        provider_registry.register(AgyCLIAdapter())

    # ── 10. Activity Generation ───────────────────────────────────────────────
    def test_agy_activity_generation_across_phases(self):
        """Verifies that activity events are generated across all pipeline phases."""
        fake_agy = GenericExecutableAdapter(
            provider_id="agy",
            display_name="Antigravity CLI (agy)",
            executable_path=sys.executable,
            args_template=["-c", "print('AGY_ACTIVITY_OK')"],
        )
        provider_registry.register(fake_agy)

        emitted_events = []
        orchestrator = ExecutionOrchestrator(
            project_root=self.root,
            event_sink=emitted_events.append,
        )

        result = orchestrator.run(
            provider_name="agy",
            task="Verify telemetry events",
        )

        self.assertTrue(result.ok)
        phases = [evt.phase for evt in emitted_events]

        self.assertIn("PROJECT", phases)
        self.assertIn("SESSION", phases)
        self.assertIn("PROVIDER", phases)
        self.assertIn("PLANNING", phases)
        self.assertIn("TRUSTGATE", phases)
        self.assertIn("EXECUTION", phases)

        # Re-register real adapter
        provider_registry.register(AgyCLIAdapter())

    # ── 11. Dangerously Skip Permissions Flag ─────────────────────────────────
    def test_agy_dangerously_skip_permissions_flag(self):
        """Verifies that skip_permissions passes --dangerously-skip-permissions when requested."""
        adapter = AgyCLIAdapter(custom_executable="agy")
        cmd_default = adapter.build_command(
            task="task",
            enriched_prompt="prompt",
            project_root=str(self.root),
            non_interactive=True,
            skip_permissions=False,
        )
        self.assertNotIn("--dangerously-skip-permissions", cmd_default)
        self.assertNotIn("run", cmd_default)
        self.assertEqual(cmd_default[-2:], ["-p", "prompt"])

        # When skip_permissions=True
        cmd_skip = adapter.build_command(
            task="task",
            enriched_prompt="prompt",
            project_root=str(self.root),
            non_interactive=True,
            skip_permissions=True,
        )
        self.assertIn("--dangerously-skip-permissions", cmd_skip)
        self.assertNotIn("run", cmd_skip)
        self.assertEqual(cmd_skip[-2:], ["-p", "prompt"])

        # Via environment variable
        with patch.dict(os.environ, {"CLIVERSE_AGY_SKIP_PERMISSIONS": "1"}):
            cmd_env = adapter.build_command(
                task="task",
                enriched_prompt="prompt",
                project_root=str(self.root),
                non_interactive=True,
            )
            self.assertIn("--dangerously-skip-permissions", cmd_env)
            self.assertNotIn("run", cmd_env)


if __name__ == "__main__":
    unittest.main()
