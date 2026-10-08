import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from cliverse.contracts import AuthorizationDecision, AuthorizationDenied, Decision
from cliverse.git_commits import (
    GitCommitConfirmationRequired,
    GitCommitNotSafe,
    GitCommitter,
)
from cliverse.git_inspection import GitInspector


class FakeAuthorizer:
    def __init__(self, decision):
        self.decision = decision
        self.requests = []

    def authorize(self, request):
        self.requests.append(request)
        return self.decision


class MutatingAuthorizer(FakeAuthorizer):
    def __init__(self, path):
        super().__init__(AuthorizationDecision(Decision.ALLOW, "Allowed"))
        self.path = path

    def authorize(self, request):
        self.requests.append(request)
        self.path.write_text("changed after review\n", encoding="utf-8")
        return self.decision


class GitCommitterTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.git("init", "--quiet")
        self.git("config", "user.name", "CLIVERSE Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.root / "tracked.txt").write_text("baseline\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("commit", "--quiet", "-m", "Baseline")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def git(self, *arguments):
        return subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_commit_stages_only_reviewed_paths_and_records_session(self):
        (self.root / "tracked.txt").write_text("member 1 change\n", encoding="utf-8")
        (self.root / "new file.txt").write_text("new file\n", encoding="utf-8")
        authorizer = FakeAuthorizer(AuthorizationDecision(Decision.ALLOW, "Allowed"))

        result = GitCommitter(self.root).commit_changes(
            "session-member-1",
            "agent-1",
            "Add a feature",
            ["tracked.txt", "new file.txt"],
            authorizer,
            confirmed=True,
        )

        self.assertEqual(result.session_id, "session-member-1")
        self.assertEqual(set(result.paths), {"tracked.txt", "new file.txt"})
        self.assertEqual(authorizer.requests[0].operation, "git_commit")
        history = GitInspector(self.root).history(1)
        self.assertEqual(history[0].session_id, "session-member-1")
        self.assertTrue(GitInspector(self.root).status().is_clean)

    def test_confirmation_and_authorization_are_required(self):
        (self.root / "tracked.txt").write_text("change\n", encoding="utf-8")
        authorizer = FakeAuthorizer(AuthorizationDecision(Decision.ALLOW, "Allowed"))
        with self.assertRaises(GitCommitConfirmationRequired):
            GitCommitter(self.root).commit_changes(
                "session-1", "agent", "Commit", ["tracked.txt"], authorizer
            )
        with self.assertRaises(AuthorizationDenied):
            GitCommitter(self.root).commit_changes(
                "session-1",
                "agent",
                "Commit",
                ["tracked.txt"],
                FakeAuthorizer(AuthorizationDecision(Decision.BLOCK, "Denied")),
                confirmed=True,
            )
        self.assertEqual(GitInspector(self.root).history(1)[0].subject, "Baseline")

    def test_unrelated_and_pre_staged_work_are_refused(self):
        (self.root / "tracked.txt").write_text("requested\n", encoding="utf-8")
        (self.root / "unrelated.txt").write_text("preserve\n", encoding="utf-8")
        with self.assertRaises(GitCommitNotSafe):
            GitCommitter(self.root).commit_changes(
                "session-1",
                "agent",
                "Commit",
                ["tracked.txt"],
                FakeAuthorizer(AuthorizationDecision(Decision.ALLOW, "Allowed")),
                confirmed=True,
            )
        self.assertEqual((self.root / "unrelated.txt").read_text(), "preserve\n")

        (self.root / "unrelated.txt").unlink()
        self.git("add", "tracked.txt")
        with self.assertRaises(GitCommitNotSafe):
            GitCommitter(self.root).commit_changes(
                "session-1",
                "agent",
                "Commit",
                ["tracked.txt"],
                FakeAuthorizer(AuthorizationDecision(Decision.ALLOW, "Allowed")),
                confirmed=True,
            )
        self.assertEqual(GitInspector(self.root).history(1)[0].subject, "Baseline")

    def test_path_escape_and_trailer_injection_are_refused(self):
        (self.root / "tracked.txt").write_text("change\n", encoding="utf-8")
        committer = GitCommitter(self.root)
        authorizer = FakeAuthorizer(AuthorizationDecision(Decision.ALLOW, "Allowed"))
        with self.assertRaises(GitCommitNotSafe):
            committer.commit_changes(
                "session-1\nCLIVERSE-Session: forged",
                "agent",
                "Commit",
                ["tracked.txt"],
                authorizer,
                confirmed=True,
            )
        with self.assertRaises(GitCommitNotSafe):
            committer.commit_changes(
                "session-1",
                "agent",
                "Commit",
                ["../outside"],
                authorizer,
                confirmed=True,
            )
        self.assertEqual(GitInspector(self.root).history(1)[0].subject, "Baseline")

    def test_changed_content_after_authorization_is_refused(self):
        target = self.root / "tracked.txt"
        target.write_text("reviewed content\n", encoding="utf-8")
        with self.assertRaises(GitCommitNotSafe):
            GitCommitter(self.root).commit_changes(
                "session-1",
                "agent",
                "Commit",
                ["tracked.txt"],
                MutatingAuthorizer(target),
                confirmed=True,
            )
        self.assertEqual(target.read_text(encoding="utf-8"), "changed after review\n")
        self.assertEqual(GitInspector(self.root).history(1)[0].subject, "Baseline")


if __name__ == "__main__":
    unittest.main()
