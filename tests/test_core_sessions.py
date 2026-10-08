import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from cliverse.sessions import InvalidSession, SessionNotFound, SessionStore


class SessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.store = SessionStore(self.root / ".envcore" / "cliverse.sqlite3")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_session_and_events_persist_between_store_instances(self):
        session = self.store.create_session(self.root, "Build a local CLI")
        event = self.store.add_event(
            session.session_id,
            "LAYA",
            "PLAN_CREATED",
            "Structured task created",
            details={"fields": ["role", "task"]},
        )

        reloaded = SessionStore(self.root / ".envcore" / "cliverse.sqlite3")
        self.assertEqual(reloaded.get_session(session.session_id), session)
        events = reloaded.list_events(session.session_id)
        self.assertEqual([item.event_type for item in events], ["SESSION_STARTED", "PLAN_CREATED"])
        self.assertEqual(events[1].event_id, event.event_id)
        self.assertEqual(events[1].details, {"fields": ["role", "task"]})

    def test_request_is_stored_as_data_not_sql(self):
        request = "Build feature'; DROP TABLE sessions; --"
        session = self.store.create_session(self.root, request)
        self.assertEqual(self.store.get_session(session.session_id).user_request, request)
        self.assertEqual(len(self.store.list_sessions()), 1)

    def test_events_are_append_only(self):
        session = self.store.create_session(self.root, "Test event immutability")
        with self.assertRaises(sqlite3.IntegrityError):
            with sqlite3.connect(self.store.database_path) as connection:
                connection.execute(
                    "UPDATE core_events SET summary = ? WHERE session_id = ?",
                    ("tampered", session.session_id),
                )

    def test_finish_session_records_terminal_state(self):
        session = self.store.create_session(self.root, "Finish this session")
        finished = self.store.finish_session(session.session_id, "completed")

        self.assertEqual(finished.status, "completed")
        events = self.store.list_events(session.session_id)
        self.assertEqual(events[-1].event_type, "SESSION_ENDED")
        self.assertEqual(events[-1].details, {"status": "completed"})
        with self.assertRaises(InvalidSession):
            self.store.finish_session(session.session_id, "failed")

    def test_invalid_requests_and_unknown_sessions_fail_explicitly(self):
        with self.assertRaises(InvalidSession):
            self.store.create_session(self.root, "  ")
        with self.assertRaises(SessionNotFound):
            self.store.get_session("missing")
        with self.assertRaises(SessionNotFound):
            self.store.add_event("missing", "CLI", "STARTED", "start")

    def test_database_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            metadata = parent / ".envcore"
            metadata.mkdir(mode=0o700)
            external_database = parent / "external.sqlite3"
            external_database.write_text("not a database", encoding="utf-8")
            (metadata / "cliverse.sqlite3").symlink_to(external_database)

            with self.assertRaises(InvalidSession):
                SessionStore(metadata / "cliverse.sqlite3")

    def test_cli_session_lifecycle(self):
        repository = Path(__file__).resolve().parents[1]

        def invoke(*arguments):
            return subprocess.run(
                [sys.executable, str(repository / "env.py"), *arguments],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(invoke("init", "--root", str(self.root)).returncode, 0)
        started = invoke(
            "session", "start", "--root", str(self.root), "--request", "Create a CLI session"
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        session_id = json.loads(started.stdout)["session"]["session_id"]

        shown = invoke("session", "show", "--root", str(self.root), session_id)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertEqual(
            json.loads(shown.stdout)["events"][0]["event_type"],
            "SESSION_STARTED",
        )

        finished = invoke("session", "finish", "--root", str(self.root), session_id)
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertEqual(json.loads(finished.stdout)["session"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
