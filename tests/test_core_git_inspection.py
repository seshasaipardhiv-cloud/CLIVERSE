import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from cliverse.git_inspection import GitInspector, InvalidGitRequest, NotGitRepository


class GitInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        (self.root / "tracked.txt").write_text("before\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "tracked.txt"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.name=CLIVERSE Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "Baseline",
                "-m",
                "CLIVERSE-Session: session-test",
            ],
            check=True,
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_status_and_diff_include_tracked_and_untracked_files(self):
        (self.root / "tracked.txt").write_text("after\n", encoding="utf-8")
        (self.root / "new file.txt").write_text("new content\n", encoding="utf-8")
        inspector = GitInspector(self.root)

        status = inspector.status()
        diff = inspector.diff()

        self.assertFalse(status.is_clean)
        self.assertIn("tracked.txt", status.changed_paths)
        self.assertIn("new file.txt", status.changed_paths)
        self.assertIn("+after", diff)
        self.assertIn("+new content", diff)

    def test_history_extracts_session_trailer(self):
        history = GitInspector(self.root).history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].subject, "Baseline")
        self.assertEqual(history[0].session_id, "session-test")

    def test_unborn_repository_has_empty_history_and_clean_status(self):
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory)
            subprocess.run(["git", "init", "--quiet", str(empty)], check=True)
            inspector = GitInspector(empty)
            self.assertEqual(inspector.history(), ())
            self.assertTrue(inspector.status().is_clean)

    def test_rejects_non_repository_and_nested_subdirectory(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(NotGitRepository):
                GitInspector(directory)
        nested = self.root / "nested"
        nested.mkdir()
        with self.assertRaises(NotGitRepository):
            GitInspector(nested)

    def test_history_limit_is_bounded(self):
        inspector = GitInspector(self.root)
        with self.assertRaises(InvalidGitRequest):
            inspector.history(0)
        with self.assertRaises(InvalidGitRequest):
            inspector.history(True)


if __name__ == "__main__":
    unittest.main()
