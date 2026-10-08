"""
Audit Logger — Audit Layer

Provides complete, tamper-evident, chain-hashed event logging for all
operations passing through the CLIVERSE pipeline.

Includes cryptographic verification to validate log integrity on reload.
"""

import json
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any, List, Tuple
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
    REQUEST = "REQUEST"
    APPROVAL = "APPROVAL"
    REJECTION = "REJECTION"
    INTENT_ANALYSIS = "INTENT_ANALYSIS"
    PROMPT_GENERATED = "PROMPT_GENERATED"
    CLARIFICATION = "CLARIFICATION"
    CLI_STARTED = "CLI_STARTED"
    CLI_COMPLETED = "CLI_COMPLETED"
    CLI_FAILED = "CLI_FAILED"
    FILE_MODIFIED = "FILE_MODIFIED"
    COMMAND_EXECUTED = "COMMAND_EXECUTED"
    IDENTITY_REGISTERED = "IDENTITY_REGISTERED"
    IDENTITY_REVOKED = "IDENTITY_REVOKED"
    PERMISSION_ALLOWED = "PERMISSION_ALLOWED"
    PERMISSION_WARNED = "PERMISSION_WARNED"
    PERMISSION_BLOCKED = "PERMISSION_BLOCKED"
    SANDBOX_VIOLATION = "SANDBOX_VIOLATION"
    SECRET_ACCESSED = "SECRET_ACCESSED"
    POLICY_ALLOW = "POLICY_ALLOW"
    POLICY_WARN = "POLICY_WARN"
    POLICY_BLOCK = "POLICY_BLOCK"
    COMPLIANCE_CHECK = "COMPLIANCE_CHECK"
    GIT_COMMIT = "GIT_COMMIT"
    GIT_BRANCH = "GIT_BRANCH"
    GIT_REVERT = "GIT_REVERT"
    ENVIRONMENT_INIT = "ENVIRONMENT_INIT"
    SESSION_STARTED = "SESSION_STARTED"
    SESSION_ENDED = "SESSION_ENDED"
    ERROR = "ERROR"


@dataclass
class AuditEvent:
    """
    A single immutable audit record with cryptographic hash integrity.
    """
    event_id: str
    timestamp: str
    source: EventSource
    event_type: EventType
    session_id: Optional[str]
    agent_id: Optional[str]
    summary: str
    details: dict = field(default_factory=dict)
    decision: Optional[str] = None
    risk_level: Optional[str] = None
    previous_hash: Optional[str] = None
    chain_hash: Optional[str] = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["source"] = self.source.value if isinstance(self.source, EventSource) else self.source
        data["event_type"] = self.event_type.value if isinstance(self.event_type, EventType) else self.event_type
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def display(self) -> str:
        decision_badge = f" [{self.decision}]" if self.decision else ""
        src_val = self.source.value if isinstance(self.source, EventSource) else str(self.source)
        evt_val = self.event_type.value if isinstance(self.event_type, EventType) else str(self.event_type)
        return (
            f"{self.timestamp[11:19]}  "
            f"{src_val:<12} "
            f"{evt_val:<25} "
            f"{decision_badge:<10} "
            f"{self.summary}"
        )


class AuditLogger:
    """
    Central audit logging service with full-field SHA-256 chain verification.
    """

    def __init__(
        self,
        log_dir: str = ".envcore/audit",
        session_id: Optional[str] = None,
        secrets_manager=None,
    ):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or str(uuid.uuid4())
        self.secrets_manager = secrets_manager
        self._events: list[AuditEvent] = []
        self._last_hash: str = "GENESIS_BLOCK_00000000000000000000"
        self._log_file = self.log_dir / f"audit-{self.session_id}.jsonl"
        self._all_log_file = self.log_dir / "audit-all.jsonl"

        # Initialize session event
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
        Record a cryptographically bound audit event including all metadata fields in hash.
        """
        clean_summary = self._redact(summary)
        clean_details = self._redact_dict(details or {})

        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        prev_hash = self._last_hash

        # Compute full-field canonical hash
        chain_hash = self._compute_full_chain_hash(
            event_id=event_id,
            timestamp=timestamp,
            source=source.value if isinstance(source, EventSource) else source,
            event_type=event_type.value if isinstance(event_type, EventType) else event_type,
            session_id=session_id or self.session_id,
            agent_id=agent_id,
            summary=clean_summary,
            decision=decision,
            risk_level=risk_level,
            details=clean_details,
            previous_hash=prev_hash,
        )

        event = AuditEvent(
            event_id=event_id,
            timestamp=timestamp,
            source=source,
            event_type=event_type,
            session_id=session_id or self.session_id,
            agent_id=agent_id,
            summary=clean_summary,
            details=clean_details,
            decision=decision,
            risk_level=risk_level,
            previous_hash=prev_hash,
            chain_hash=chain_hash,
        )

        self._events.append(event)
        self._write(event)
        self._last_hash = chain_hash
        return event

    def verify_chain_integrity(self, log_path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Verifies the cryptographic chain across all stored events.
        Detects any tampering, alteration, or sequence corruption.
        """
        target_path = Path(log_path) if log_path else self._log_file
        if not target_path.exists():
            return True, "No log file found to verify"

        expected_prev = "GENESIS_BLOCK_00000000000000000000"
        line_num = 0

        with open(target_path, "r", encoding="utf-8") as f:
            for line in f:
                line_num += 1
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except Exception as e:
                    return False, f"Line {line_num}: JSON corruption - {str(e)}"

                # Check previous hash link
                if data.get("previous_hash") != expected_prev:
                    return False, (
                        f"Line {line_num}: Chain broken! Expected prev hash '{expected_prev}', "
                        f"found '{data.get('previous_hash')}'"
                    )

                # Recompute and verify current hash
                computed = self._compute_full_chain_hash(
                    event_id=data["event_id"],
                    timestamp=data["timestamp"],
                    source=data["source"],
                    event_type=data["event_type"],
                    session_id=data["session_id"],
                    agent_id=data["agent_id"],
                    summary=data["summary"],
                    decision=data["decision"],
                    risk_level=data["risk_level"],
                    details=data.get("details", {}),
                    previous_hash=data["previous_hash"],
                )

                if computed != data.get("chain_hash"):
                    return False, (
                        f"Line {line_num}: Tampering detected! Computed hash '{computed}' "
                        f"does not match recorded '{data.get('chain_hash')}'"
                    )

                expected_prev = computed

        return True, f"Cryptographic integrity verified across {line_num} audit events."

    def get_events(
        self,
        source: Optional[EventSource] = None,
        event_type: Optional[EventType] = None,
        decision: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        results = self._events
        if source:
            results = [e for e in results if e.source == source]
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if decision:
            results = [e for e in results if e.decision == decision]
        return results[-limit:]

    def get_security_events(self) -> list[AuditEvent]:
        return [e for e in self._events if e.decision in ("BLOCK", "WARN")]

    def print_timeline(self, limit: int = 20) -> None:
        print(f"\n{'-'*80}")
        print(f"  CLIVERSE AUDIT TRAIL  (session: {self.session_id[:8]})")
        print(f"{'-'*80}")
        for event in self._events[-limit:]:
            print(f"  {event.display()}")
        print(f"{'-'*80}\n")

    # ------------------------------------------------------------------ #
    #  Internal Cryptographic Hashing                                     #
    # ------------------------------------------------------------------ #

    def _compute_full_chain_hash(
        self,
        event_id: str,
        timestamp: str,
        source: str,
        event_type: str,
        session_id: Optional[str],
        agent_id: Optional[str],
        summary: str,
        decision: Optional[str],
        risk_level: Optional[str],
        details: dict,
        previous_hash: str,
    ) -> str:
        canonical_details = json.dumps(details, sort_keys=True)
        raw = (
            f"{previous_hash}|{event_id}|{timestamp}|{source}|{event_type}|"
            f"{session_id or ''}|{agent_id or ''}|{decision or ''}|{risk_level or ''}|"
            f"{summary}|{canonical_details}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _write(self, event: AuditEvent) -> None:
        line = event.to_json() + "\n"
        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(line)
        with open(self._all_log_file, "a", encoding="utf-8") as f:
            f.write(line)

    def _redact(self, text: str) -> str:
        if self.secrets_manager:
            return self.secrets_manager.redact(text)
        return text

    def _redact_dict(self, data: dict) -> dict:
        result = {}
        for k, v in data.items():
            if isinstance(v, str):
                result[k] = self._redact(v)
            elif isinstance(v, dict):
                result[k] = self._redact_dict(v)
            else:
                result[k] = v
        return result
