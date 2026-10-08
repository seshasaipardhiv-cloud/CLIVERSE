import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from cliverse.contracts import AuthorizationDecision, AuthorizationRequest, Decision
from cliverse.environment import ProjectEnvironment
from cliverse.execution import ProcessRequest, execute_guarded
from cliverse.git_commits import GitCommitter
from cliverse.git_inspection import GitInspector
from cliverse.planning import PlanningRequest, RequestPlanner
from cliverse.recovery import GitRecovery
from cliverse.sessions import SessionStore


class AllowAuthorizer:
    def __init__(self):
        self.requests = []

    def authorize(self, request: AuthorizationRequest):
        self.requests.append(request)
        return AuthorizationDecision(Decision.ALLOW, "Deterministic test authorization")


class CoreEndToEndTests(unittest.TestCase):
    def test_init_plan_guarded_fake_execution_session_git_and_undo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".gitignore").write_text(".envcore/\n", encoding="utf-8")
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "CLIVERSE Test"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.email", "test@example.invalid"],
                check=True,
            )
            subprocess.run(["git", "-C", str(root), "add", ".gitignore"], check=True)
            subprocess.run(
                ["git", "-C", str(root), "commit", "--quiet", "-m", "Initialize test project"],
                check=True,
            )

            environment = ProjectEnvironment.initialize(root)
            store = SessionStore(environment.metadata_dir / "cliverse.sqlite3")
            session = store.create_session(root, "Create a small Python entry point")

            plan = RequestPlanner(allow_context_free=True).plan(
                PlanningRequest(
                    task="Create a small Python entry point",
                    context="Temporary project used only by this integration test.",
                    requirements=("Create main.py",),
                    constraints=("Use no hosted service",),
                )
            )
            self.assertTrue(plan.ready)
            store.add_event(
                session.session_id,
                "LAYA",
                "PROMPT_GENERATED",
                "Structured task created",
                details={"task": plan.task.task, "provenance": list(plan.context_provenance)},
            )

            execution_authorizer = AllowAuthorizer()
            result = execute_guarded(
                ProcessRequest(
                    executable=sys.executable,
                    arguments=(
                        "-c",
                        "from pathlib import Path; Path('main.py').write_text('print(42)\\n')",
                    ),
                    project_root=str(root),
                    identity="test-agent",
                ),
                execution_authorizer,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.authorization_decision, "ALLOW")
            store.add_event(
                session.session_id,
                "CLI",
                "CLI_COMPLETED",
                "Controlled local process completed",
                details={"returncode": result.returncode},
            )

            commit_authorizer = AllowAuthorizer()
            commit = GitCommitter(root).commit_changes(
                session.session_id,
                "test-agent",
                "Create Python entry point",
                ["main.py"],
                commit_authorizer,
                confirmed=True,
            )
            store.add_event(
                session.session_id,
                "GIT",
                "GIT_COMMIT",
                "Session changes committed",
                details={"commit_id": commit.commit_id},
            )
            store.finish_session(session.session_id, "completed")

            history = GitInspector(root).history(1)
            self.assertEqual(history[0].session_id, session.session_id)
            self.assertTrue(GitInspector(root).status().is_clean)
            self.assertEqual(len(store.list_events(session.session_id)), 5)

            undo = GitRecovery(root).undo(
                session.session_id,
                "test-agent",
                AllowAuthorizer(),
                confirmed=True,
            )
            self.assertEqual(undo.reverted_commit, commit.commit_id)
            self.assertFalse((root / "main.py").exists())
            self.assertTrue(GitInspector(root).status().is_clean)


if __name__ == "__main__":
    unittest.main()
