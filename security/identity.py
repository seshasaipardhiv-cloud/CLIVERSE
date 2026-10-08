"""
Identity Manager — Security Layer

Manages CLI/agent identity within the CLIVERSE environment.
Each CLI session is assigned a unique identity with metadata
that is carried through every pipeline stage.
"""

import uuid
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
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


class IdentityManager:
    """
    Manages agent identities for the CLIVERSE environment.

    Each time an AI CLI starts a session, it receives a unique identity.
    The identity is used downstream by the PermissionEngine and AuditLogger.

    Usage:
        manager = IdentityManager(storage_path=".envcore/identities")
        identity = manager.register("claude-cli", scopes=["read", "write"])
        manager.validate(identity.agent_id)
    """

    KNOWN_TRUSTED_CLIS = {
        "claude-cli",
        "gemini-cli",
        "copilot-cli",
        "gpt-cli",
        "agy",
        "antigravity",
        "cursor",
        "aider",
    }

    def __init__(self, storage_path: str = ".envcore/identities"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
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
    ) -> AgentIdentity:
        """Register a new CLI session and return its identity."""
        agent_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        fingerprint = self._fingerprint(cli_name, agent_id, created_at)
        is_trusted = cli_name.lower() in self.KNOWN_TRUSTED_CLIS

        identity = AgentIdentity(
            agent_id=agent_id,
            cli_name=cli_name,
            session_id=session_id,
            created_at=created_at,
            fingerprint=fingerprint,
            is_trusted=is_trusted,
            scopes=scopes or self._default_scopes(is_trusted),
            metadata=metadata or {},
        )

        self._registry[agent_id] = identity
        self._persist(identity)
        return identity

    def validate(self, agent_id: str) -> Optional[AgentIdentity]:
        """Return identity if valid, else None."""
        return self._registry.get(agent_id)

    def revoke(self, agent_id: str) -> bool:
        """Revoke an agent's identity (removes from registry)."""
        if agent_id in self._registry:
            identity = self._registry.pop(agent_id)
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
                pass  # Skip corrupted identity files
