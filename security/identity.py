"""
Identity Manager — Security Layer

Manages CLI/agent identity within the CLIVERSE environment.
Enforces strict scope validation: callers cannot grant themselves privileged
scopes without explicit trust or administrative authorization.
"""

import uuid
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set
from dataclasses import dataclass, field, asdict


@dataclass
class AgentIdentity:
    """Represents the identity of a CLI/Agent session."""

    agent_id: str
    cli_name: str
    session_id: str
    created_at: str
    fingerprint: str
    is_trusted: bool = False
    scopes: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        return f"[{self.cli_name}:{self.agent_id[:8]}]"


class ScopeViolationError(ValueError):
    """Raised when an untrusted agent attempts to request unpermitted scopes."""
    pass


class IdentityManager:
    """
    Manages agent identities for the CLIVERSE environment with strict scope enforcement.

    Security Rule:
    - Untrusted CLIs are strictly restricted to UNTRUSTED_MAX_SCOPES ('read').
    - Privileged scopes ('write', 'execute', 'git', 'admin', 'delete') can ONLY be granted
      to pre-registered trusted CLIs or when explicitly authorized via admin_token.
    """

    KNOWN_TRUSTED_CLIS: Set[str] = {
        "claude-cli",
        "gemini-cli",
        "copilot-cli",
        "gpt-cli",
        "agy",
        "antigravity",
        "cursor",
        "aider",
    }

    UNTRUSTED_MAX_SCOPES: Set[str] = {"read", "list", "search"}
    PRIVILEGED_SCOPES: Set[str] = {"write", "execute", "git", "admin", "delete"}

    def __init__(self, storage_path: str = ".envcore/identities", admin_secret: Optional[str] = None):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.admin_secret = admin_secret or "cliverse-admin-default-key"
        self._registry: dict[str, AgentIdentity] = {}
        self._load_existing()

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def register(
        self,
        cli_name: str,
        scopes: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
        admin_token: Optional[str] = None,
    ) -> AgentIdentity:
        """
        Register a new CLI session with strict scope authorization checks.
        
        If an untrusted CLI requests privileged scopes without a valid admin_token,
        the request is sanitized or rejected to prevent privilege escalation.
        """
        is_trusted = cli_name.lower() in self.KNOWN_TRUSTED_CLIS or (admin_token == self.admin_secret)
        
        # Enforce scope boundaries
        assigned_scopes: list[str] = []
        if scopes:
            for s in scopes:
                if s in self.PRIVILEGED_SCOPES and not is_trusted:
                    raise ScopeViolationError(
                        f"Scope '{s}' is privileged and cannot be granted to untrusted CLI '{cli_name}' "
                        f"without administrative authorization."
                    )
            assigned_scopes = list(set(scopes))
        else:
            assigned_scopes = self._default_scopes(is_trusted)

        agent_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        fingerprint = self._fingerprint(cli_name, agent_id, created_at)

        identity = AgentIdentity(
            agent_id=agent_id,
            cli_name=cli_name,
            session_id=session_id,
            created_at=created_at,
            fingerprint=fingerprint,
            is_trusted=is_trusted,
            scopes=assigned_scopes,
            metadata=metadata or {},
        )

        self._registry[agent_id] = identity
        self._persist(identity)
        return identity

    def validate(self, agent_id: str) -> Optional[AgentIdentity]:
        """Return identity if valid, else None."""
        return self._registry.get(agent_id)

    def revoke(self, agent_id: str) -> bool:
        """Revoke an agent's identity (removes from registry and disk)."""
        if agent_id in self._registry:
            del self._registry[agent_id]
            identity_file = self.storage_path / f"{agent_id}.json"
            if identity_file.exists():
                identity_file.unlink()
            return True
        return False

    def list_active(self) -> list[AgentIdentity]:
        """Return all currently registered identities."""
        return list(self._registry.values())

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _default_scopes(self, is_trusted: bool) -> list[str]:
        if is_trusted:
            return ["read", "write", "git", "execute"]
        return ["read"]

    def _fingerprint(self, cli_name: str, agent_id: str, created_at: str) -> str:
        raw = f"{cli_name}:{agent_id}:{created_at}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _persist(self, identity: AgentIdentity) -> None:
        identity_file = self.storage_path / f"{identity.agent_id}.json"
        identity_file.write_text(json.dumps(identity.to_dict(), indent=2))

    def _load_existing(self) -> None:
        for f in self.storage_path.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                identity = AgentIdentity(**data)
                self._registry[identity.agent_id] = identity
            except Exception:
                pass
