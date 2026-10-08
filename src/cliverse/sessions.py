"""SQLite persistence for CLIVERSE sessions and append-only core events."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .errors import CliverseError


class SessionNotFound(CliverseError):
    code = "SESSION_NOT_FOUND"
    suggestion = "List sessions and use an existing session ID."


class InvalidSession(CliverseError):
    code = "INVALID_SESSION"
    suggestion = "Provide a non-empty request and a supported session status."


@dataclass(frozen=True)
class Session:
    session_id: str
    project_root: str
    user_request: str
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CoreEvent:
    event_id: str
    session_id: str
    timestamp: str
    source: str
    event_type: str
    summary: str
    details: dict[str, Any]
    decision: str | None


class SessionStore:
    """Store sessions and append-only events in one project-local SQLite file."""

    VALID_STATUSES = {"running", "completed", "failed", "cancelled"}
    MAX_LIST_LIMIT = 1000

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._initialize_schema()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize_schema(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    project_root TEXT NOT NULL,
                    user_request TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('running', 'completed', 'failed', 'cancelled')
                    ),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS core_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    decision TEXT
                );

                CREATE INDEX IF NOT EXISTS core_events_session_timestamp
                    ON core_events(session_id, timestamp);

                CREATE TRIGGER IF NOT EXISTS core_events_no_update
                BEFORE UPDATE ON core_events
                BEGIN
                    SELECT RAISE(ABORT, 'core events are append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS core_events_no_delete
                BEFORE DELETE ON core_events
                BEGIN
                    SELECT RAISE(ABORT, 'core events are append-only');
                END;
                """
            )

    def create_session(self, project_root: str | Path, user_request: str) -> Session:
        request = user_request.strip()
        if not request:
            raise InvalidSession("The user request must not be empty.")

        now = datetime.now(timezone.utc).isoformat()
        session = Session(
            session_id=str(uuid.uuid4()),
            project_root=str(Path(project_root).expanduser().resolve()),
            user_request=request,
            status="running",
            created_at=now,
            updated_at=now,
        )
        event = CoreEvent(
            event_id=str(uuid.uuid4()),
            session_id=session.session_id,
            timestamp=now,
            source="ENVIRONMENT",
            event_type="SESSION_STARTED",
            summary="Session created",
            details={},
            decision=None,
        )

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO sessions
                    (session_id, project_root, user_request, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.project_root,
                    session.user_request,
                    session.status,
                    session.created_at,
                    session.updated_at,
                ),
            )
            self._insert_event(connection, event)
        return session

    def add_event(
        self,
        session_id: str,
        source: str,
        event_type: str,
        summary: str,
        details: dict[str, Any] | None = None,
        decision: str | None = None,
    ) -> CoreEvent:
        values = (session_id, source, event_type, summary)
        if any(not value or not value.strip() for value in values):
            raise InvalidSession("Session ID, source, event type and summary are required.")
        event = CoreEvent(
            event_id=str(uuid.uuid4()),
            session_id=session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source=source,
            event_type=event_type,
            summary=summary,
            details=details or {},
            decision=decision,
        )
        with self._connection() as connection:
            try:
                self._insert_event(connection, event)
            except sqlite3.IntegrityError as exc:
                if "FOREIGN KEY constraint failed" in str(exc):
                    raise SessionNotFound(f"Unknown session ID: {session_id}") from exc
                raise
        return event

    def _insert_event(self, connection: sqlite3.Connection, event: CoreEvent) -> None:
        connection.execute(
            """
            INSERT INTO core_events
                (event_id, session_id, timestamp, source, event_type, summary,
                 details_json, decision)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.session_id,
                event.timestamp,
                event.source,
                event.event_type,
                event.summary,
                json.dumps(event.details, sort_keys=True),
                event.decision,
            ),
        )

    def finish_session(self, session_id: str, status: str) -> Session:
        if status not in self.VALID_STATUSES - {"running"}:
            raise InvalidSession(f"Unsupported final session status: {status}")
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE sessions SET status = ?, updated_at = ?
                WHERE session_id = ? AND status = 'running'
                """,
                (status, now, session_id),
            )
            if cursor.rowcount == 0:
                if connection.execute(
                    "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
                ).fetchone() is None:
                    raise SessionNotFound(f"Unknown session ID: {session_id}")
                raise InvalidSession(f"Session is not running: {session_id}")
            self._insert_event(
                connection,
                CoreEvent(
                    event_id=str(uuid.uuid4()),
                    session_id=session_id,
                    timestamp=now,
                    source="ENVIRONMENT",
                    event_type="SESSION_ENDED",
                    summary=f"Session finished with status {status}",
                    details={"status": status},
                    decision=None,
                ),
            )
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return self._session_from_row(row)

    def get_session(self, session_id: str) -> Session:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise SessionNotFound(f"Unknown session ID: {session_id}")
        return self._session_from_row(row)

    def list_sessions(self, limit: int = 100) -> list[Session]:
        self._validate_limit(limit)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._session_from_row(row) for row in rows]

    def list_events(self, session_id: str, limit: int = 100) -> list[CoreEvent]:
        self._validate_limit(limit)
        with self._connection() as connection:
            if connection.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone() is None:
                raise SessionNotFound(f"Unknown session ID: {session_id}")
            rows = connection.execute(
                """
                SELECT * FROM core_events WHERE session_id = ?
                ORDER BY timestamp, rowid LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    @classmethod
    def _validate_limit(cls, limit: int) -> None:
        if not isinstance(limit, int) or not 1 <= limit <= cls.MAX_LIST_LIMIT:
            raise InvalidSession(f"Limit must be between 1 and {cls.MAX_LIST_LIMIT}.")

    @staticmethod
    def _session_from_row(row: sqlite3.Row) -> Session:
        return Session(
            session_id=row["session_id"],
            project_root=row["project_root"],
            user_request=row["user_request"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> CoreEvent:
        return CoreEvent(
            event_id=row["event_id"],
            session_id=row["session_id"],
            timestamp=row["timestamp"],
            source=row["source"],
            event_type=row["event_type"],
            summary=row["summary"],
            details=json.loads(row["details_json"]),
            decision=row["decision"],
        )
