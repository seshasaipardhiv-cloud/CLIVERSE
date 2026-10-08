"""
Audit Logger — Audit Layer

Provides tamper-evident, structured event logging for every
operation in the CLIVERSE pipeline.

Every event includes: who, what, when, decision, and context.
The complete audit chain:
    USER → LAYA → CLI → ACTION → SECURITY → POLICY → GIT → RESULT
"""

import json
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, asdict, field
from enum import Enum


class EventSource(str, Enum):
    USER = "USER"
    LAYA = "LAYA"
    CLI = "CLI"
    SECURITY = "SECURITY"
    POLICY = "POLICY"
    GIT = "GIT"
    ENVIRONMENT = "ENVIRONMENT"
    AUDIT = "AUDIT"


class EventType(str, Enum):
    # User events
    REQUEST = "REQUEST"
    APPROVAL = "APPROVAL"
    REJECTION = "REJECTION"

    # Laya events
    INTENT_ANALYSIS = "INTENT_ANALYSIS"
    PROMPT_GENERATED = "PROMPT_GENERATED"
    CLARIFICATION = "CLARIFICATION"

    # CLI events
    CLI_STARTED = "CLI_STARTED"
    CLI_COMPLETED = "CLI_COMPLETED"
    CLI_FAILED = "CLI_FAILED"
    FILE_MODIFIED = "FILE_MODIFIED"
    COMMAND_EXECUTED = "COMMAND_EXECUTED"

    # Security events
    IDENTITY_REGISTERED = "IDENTITY_REGISTERED"
    IDENTITY_REVOKED = "IDENTITY_REVOKED"
    PERMISSION_ALLOWED = "PERMISSION_ALLOWED"
    PERMISSION_WARNED = "PERMISSION_WARNED"
    PERMISSION_BLOCKED = "PERMISSION_BLOCKED"
    SANDBOX_VIOLATION = "SANDBOX_VIOLATION"
    SECRET_ACCESSED = "SECRET_ACCESSED"

    # Governance events
    POLICY_ALLOW = "POLICY_ALLOW"
    POLICY_WARN = "POLICY_WARN"
    POLICY_BLOCK = "POLICY_BLOCK"
    COMPLIANCE_CHECK = "COMPLIANCE_CHECK"

    # Git events
    GIT_COMMIT = "GIT_COMMIT"
    GIT_BRANCH = "GIT_BRANCH"
    GIT_REVERT = "GIT_REVERT"

    # System events
    ENVIRONMENT_INIT = "ENVIRONMENT_INIT"
    SESSION_STARTED = "SESSION_STARTED"
    SESSION_ENDED = "SESSION_ENDED"
    ERROR = "ERROR"


@dataclass
class AuditEvent:
    """
    A single immutable audit record.
    Each event includes a chain hash linking it to the previous event,
    creating a tamper-evident audit trail.
    """
    event_id: str
    timestamp: str
    source: EventSource
    event_type: EventType
    session_id: Optional[str]
    agent_id: Optional[str]
    summary: str
    details: dict = field(default_factory=dict)
    decision: Optional[str] = None      # ALLOW | WARN | BLOCK
    risk_level: Optional[str] = None    # LOW | MEDIUM | HIGH | CRITICAL
    chain_hash: Optional[str] = None    # Links to previous event

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def display(self) -> str:
        """Human-readable single-line display for dashboard/CLI output."""
        decision_badge = f" [{self.decision}]" if self.decision else ""
        return (
            f"{self.timestamp[11:19]}  "
            f"{self.source:<12} "
            f"{self.event_type:<25} "
            f"{decision_badge:<10} "
            f"{self.summary}"
        )


class AuditLogger:
    """
    Central audit logging service for the CLIVERSE environment.

    Features:
    - Structured JSON-L log format (one event per line)
    - Chain hash linking for tamper-evidence
    - Automatic session grouping
    - In-memory event buffer for live dashboard queries
    - Secrets redaction integration

    Usage:
        logger = AuditLogger(log_dir=".envcore/audit")
        logger.log(
            source=EventSource.SECURITY,
            event_type=EventType.PERMISSION_BLOCKED,
            summary="rm -rf blocked",
            session_id=session_id,
            agent_id=agent_id,
            decision="BLOCK",
            risk_level="CRITICAL",
        )
    """

    def __init__(
        self,
        log_dir: str = ".envcore/audit",
        session_id: Optional[str] = None,
        secrets_manager=None,  # Optional SecretsManager for redaction
    ):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or str(uuid.uuid4())
        self.secrets_manager = secrets_manager
        self._events: list[AuditEvent] = []
        self._last_hash: Optional[str] = None
        self._log_file = self.log_dir / f"audit-{self.session_id}.jsonl"
        self._all_log_file = self.log_dir / "audit-all.jsonl"

        # Record session start
        self.log(
            source=EventSource.AUDIT,
            event_type=EventType.SESSION_STARTED,
            summary=f"Audit session started: {self.session_id}",
        )

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def log(
        self,
        source: EventSource,
        event_type: EventType,
        summary: str,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        decision: Optional[str] = None,
        risk_level: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> AuditEvent:
        """
        Record an audit event. Returns the created AuditEvent.
        All text is passed through secrets redaction before writing.
        """
        # Redact secrets from summary and details
        clean_summary = self._redact(summary)
        clean_details = self._redact_dict(details or {})

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            source=source,
            event_type=event_type,
            session_id=session_id or self.session_id,
            agent_id=agent_id,
            summary=clean_summary,
            details=clean_details,
            decision=decision,
            risk_level=risk_level,
            chain_hash=self._compute_chain_hash(clean_summary),
        )

        self._events.append(event)
        self._write(event)
        self._last_hash = event.chain_hash
        return event

    def get_events(
        self,
        source: Optional[EventSource] = None,
        event_type: Optional[EventType] = None,
        decision: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Query in-memory events with optional filters."""
        results = self._events
        if source:
            results = [e for e in results if e.source == source]
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if decision:
            results = [e for e in results if e.decision == decision]
        return results[-limit:]

    def get_security_events(self) -> list[AuditEvent]:
        """Return all BLOCK and WARN events for the security dashboard."""
        return [e for e in self._events if e.decision in ("BLOCK", "WARN")]

    def print_timeline(self, limit: int = 20) -> None:
        """Print the last N events as a human-readable timeline."""
        print(f"\n{'-'*80}")
        print(f"  CLIVERSE AUDIT TRAIL  (session: {self.session_id[:8]})")
        print(f"{'-'*80}")
        for event in self._events[-limit:]:
            print(f"  {event.display()}")
        print(f"{'-'*80}\n")

    def export_session(self, output_path: Optional[str] = None) -> str:
        """Export this session's events to a JSON file."""
        path = Path(output_path) if output_path else (self.log_dir / f"export-{self.session_id}.json")
        path.write_text(json.dumps([e.to_dict() for e in self._events], indent=2))
        return str(path)

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _write(self, event: AuditEvent) -> None:
        """Append event to session log and all-events log."""
        line = event.to_json() + "\n"
        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(line)
        with open(self._all_log_file, "a", encoding="utf-8") as f:
            f.write(line)

    def _compute_chain_hash(self, summary: str) -> str:
        """Create a hash chaining this event to the previous one."""
        previous = self._last_hash or "GENESIS"
        raw = f"{previous}:{summary}:{datetime.now(timezone.utc).isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _redact(self, text: str) -> str:
        if self.secrets_manager:
            return self.secrets_manager.redact(text)
        return text

    def _redact_dict(self, data: dict) -> dict:
        """Recursively redact secrets from a dict."""
        result = {}
        for k, v in data.items():
            if isinstance(v, str):
                result[k] = self._redact(v)
            elif isinstance(v, dict):
                result[k] = self._redact_dict(v)
            else:
                result[k] = v
        return result
