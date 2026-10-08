import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from cliverse.contracts import AuthorizationDecision, AuthorizationDenied, Decision
from cliverse.git_inspection import GitInspector
from cliverse.recovery import (
    GitRecovery,
    UndoConfirmationRequired,
    UndoNotSafe,
)


class FakeAuthorizer:
    def __init__(self, decision):
        self.decision = decision
        self.requests = []

    def authorize(self, request):
        self.requests.append(request)
        return self.decision


class GitRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.git("init", "--quiet")
        self.git("config", "user.name", "CLIVERSE Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.root / "tracked.txt").write_text("original\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("commit", "--quiet", "-m", "Baseline")
        (self.root / "tracked.txt").write_text("changed by session\n", encoding="utf-8")
        (self.root / "session-file.txt").write_text("new session file\n", encoding="utf-8")
        self.git("add", "tracked.txt", "session-file.txt")
        self.git(
            "commit",
            "--quiet",
            "-m",
            "Implement task",
            "-m",
            "CLIVERSE-Session: session-123",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def git(self, *arguments):
        return subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_preview_is_read_only_and_session_scoped(self):
        recovery = GitRecovery(self.root)
        preview = recovery.preview("session-123")

        self.assertEqual(preview.session_id, "session-123")
        self.assertIn("tracked.txt", preview.changed_paths)
        self.assertIn("session-file.txt", preview.changed_paths)
        self.assertEqual((self.root / "tracked.txt").read_text(), "changed by session\n")
        self.assertTrue((self.root / "session-file.txt").exists())

    def test_cli_exposes_preview_but_not_undo_execution(self):
        repository = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                str(repository / "env.py"),
                "git",
                "undo-preview",
                "--root",
                str(self.root),
                "--session-id",
                "session-123",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "preview_only")
        self.assertTrue(payload["requires_confirmation"])
        self.assertTrue(payload["requires_authorization"])

    def test_undo_requires_confirmation_and_authorization(self):
        recovery = GitRecovery(self.root)
        authorizer = FakeAuthorizer(AuthorizationDecision(Decision.ALLOW, "Allowed"))

        with self.assertRaises(UndoConfirmationRequired):
            recovery.undo("session-123", "agent-1", authorizer)
        with self.assertRaises(AuthorizationDenied):
            recovery.undo(
                "session-123",
                "agent-1",
                FakeAuthorizer(AuthorizationDecision(Decision.BLOCK, "Denied")),
                confirmed=True,
            )
        self.assertEqual((self.root / "tracked.txt").read_text(), "changed by session\n")
        self.assertTrue((self.root / "session-file.txt").exists())

    def test_successful_undo_reverts_only_tagged_clean_head(self):
        authorizer = FakeAuthorizer(AuthorizationDecision(Decision.ALLOW, "Allowed"))
        result = GitRecovery(self.root).undo(
            "session-123",
            "agent-1",
            authorizer,
            confirmed=True,
        )

        self.assertEqual(result.session_id, "session-123")
        self.assertEqual(result.authorization_decision, "ALLOW")
        self.assertEqual((self.root / "tracked.txt").read_text(), "original\n")
        self.assertFalse((self.root / "session-file.txt").exists())
        self.assertTrue(GitInspector(self.root).status().is_clean)
        self.assertEqual(authorizer.requests[0].operation, "git_revert")
        self.assertEqual(set(authorizer.requests[0].paths), {"tracked.txt", "session-file.txt"})

    def test_dirty_tree_and_non_latest_session_are_refused(self):
        (self.root / "unrelated.txt").write_text("keep me\n", encoding="utf-8")
        with self.assertRaises(UndoNotSafe):
            GitRecovery(self.root).preview("session-123")
        self.assertTrue((self.root / "unrelated.txt").exists())

        (self.root / "unrelated.txt").unlink()
        (self.root / "later.txt").write_text("later commit\n", encoding="utf-8")
        self.git("add", "later.txt")
        self.git("commit", "--quiet", "-m", "Unrelated later work")
        with self.assertRaises(UndoNotSafe):
            GitRecovery(self.root).preview("session-123")


if __name__ == "__main__":
    unittest.main()
