"""
Permission Engine — Security Layer

Evaluates whether an agent identity is allowed to perform
a given operation. Enforces filesystem restrictions,
command allow/deny lists, and scope-based access control.
"""

import re
from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from typing import Optional

from .identity import AgentIdentity


class Decision(str, Enum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    BLOCK = "BLOCK"


@dataclass
class PermissionResult:
    decision: Decision
    reason: str
    operation: str
    agent_id: str
    risk_level: str = "LOW"  # LOW | MEDIUM | HIGH | CRITICAL

    @property
    def allowed(self) -> bool:
        return self.decision == Decision.ALLOW

    def __str__(self) -> str:
        return f"[{self.decision}] {self.operation} — {self.reason}"


class PermissionEngine:
    """
    Evaluates permissions for CLI operations in the CLIVERSE pipeline.

    Checks happen in order:
      1. Scope check     — does the agent have the right scope?
      2. Command check   — is the command allowed/denied?
      3. Filesystem check — is the path within allowed boundaries?
      4. Destructive check — is this a dangerous operation?

    Usage:
        engine = PermissionEngine(project_root="/path/to/project")
        result = engine.check(identity, operation="write", path="/project/src/main.py")
        if result.allowed:
            execute()
    """

    # ------------------------------------------------------------------ #
    #  Dangerous command patterns (always BLOCKED)                        #
    # ------------------------------------------------------------------ #
    BLOCKED_COMMANDS: list[str] = [
        r"rm\s+-rf\s+/",            # rm -rf /
        r"dd\s+if=",                # disk destruction
        r"mkfs",                    # filesystem format
        r":\(\)\{.*\}",            # fork bomb
        r"curl.*\|\s*(bash|sh)",    # curl-pipe-execute
        r"wget.*\|\s*(bash|sh)",    # wget-pipe-execute
        r"chmod\s+777\s+/",         # chmod 777 on root
        r"sudo\s+rm",               # sudo rm
        r"DROP\s+TABLE",            # SQL drop table
        r"DROP\s+DATABASE",         # SQL drop database
        r"TRUNCATE\s+TABLE",        # SQL truncate
    ]

    # Commands that trigger WARN but still execute
    WARN_COMMANDS: list[str] = [
        r"rm\s+-rf",                # recursive delete (non-root)
        r"git\s+push\s+--force",    # force push
        r"git\s+reset\s+--hard",    # hard reset
        r"pip\s+install",           # package installation
        r"npm\s+install",           # npm install
        r"sudo",                    # sudo usage
        r"chmod",                   # permission changes
        r"chown",                   # ownership changes
        r"export\s+.*PASSWORD",     # exporting secrets
        r"export\s+.*SECRET",       # exporting secrets
        r"export\s+.*KEY",          # exporting keys
        r"DELETE\s+FROM",           # SQL delete
        r"UPDATE\s+.*SET",          # SQL update
    ]

    # ------------------------------------------------------------------ #
    #  Scope → allowed operations mapping                                 #
    # ------------------------------------------------------------------ #
    SCOPE_OPERATIONS: dict[str, set[str]] = {
        "read":    {"read", "list", "search", "diff"},
        "write":   {"read", "list", "search", "diff", "write", "create", "edit"},
        "git":     {"read", "list", "diff", "git_commit", "git_branch", "git_log"},
        "execute": {"read", "list", "execute", "shell"},
        "admin":   {"read", "write", "execute", "git_commit", "git_push", "admin", "delete"},
    }

    def __init__(
        self,
        project_root: str = ".",
        protected_paths: Optional[list[str]] = None,
        allowed_extensions: Optional[list[str]] = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.protected_paths: list[str] = protected_paths or [
            ".env",
            ".envcore/secrets",
            "*.pem",
            "*.key",
            "*.p12",
            "*.pfx",
            "id_rsa",
            "id_ed25519",
        ]
        self.allowed_extensions: list[str] = allowed_extensions or [
            ".py", ".ts", ".js", ".tsx", ".jsx", ".md", ".json",
            ".yaml", ".yml", ".toml", ".txt", ".html", ".css",
            ".sql", ".sh", ".go", ".rs", ".java", ".cs",
        ]

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def check(
        self,
        identity: AgentIdentity,
        operation: str,
        path: Optional[str] = None,
        command: Optional[str] = None,
    ) -> PermissionResult:
        """
        Main permission gate. Returns a PermissionResult with ALLOW/WARN/BLOCK.
        Called by the security pipeline before any CLI execution.
        """
        # 1. Scope check
        scope_result = self._check_scope(identity, operation)
        if scope_result.decision == Decision.BLOCK:
            return scope_result

        # 2. Command check
        if command:
            cmd_result = self._check_command(identity, command)
            if cmd_result.decision == Decision.BLOCK:
                return cmd_result
            if cmd_result.decision == Decision.WARN:
                return cmd_result  # Propagate warning

        # 3. Filesystem check
        if path:
            fs_result = self._check_filesystem(identity, path)
            if fs_result.decision == Decision.BLOCK:
                return fs_result
            if fs_result.decision == Decision.WARN:
                return fs_result

        return PermissionResult(
            decision=Decision.ALLOW,
            reason="All permission checks passed",
            operation=operation,
            agent_id=identity.agent_id,
            risk_level="LOW",
        )

    def check_command(self, identity: AgentIdentity, command: str) -> PermissionResult:
        """Convenience: check a shell command directly."""
        return self._check_command(identity, command)

    def check_path(self, identity: AgentIdentity, path: str) -> PermissionResult:
        """Convenience: check filesystem access directly."""
        return self._check_filesystem(identity, path)

    # ------------------------------------------------------------------ #
    #  Internal checks                                                     #
    # ------------------------------------------------------------------ #

    def _check_scope(self, identity: AgentIdentity, operation: str) -> PermissionResult:
        """Verify the agent has a scope that permits this operation."""
        for scope in identity.scopes:
            if operation in self.SCOPE_OPERATIONS.get(scope, set()):
                return PermissionResult(
                    decision=Decision.ALLOW,
                    reason=f"Scope '{scope}' grants '{operation}'",
                    operation=operation,
                    agent_id=identity.agent_id,
                )

        return PermissionResult(
            decision=Decision.BLOCK,
            reason=f"Agent lacks scope for operation '{operation}'. Has: {identity.scopes}",
            operation=operation,
            agent_id=identity.agent_id,
            risk_level="HIGH",
        )

    def _check_command(self, identity: AgentIdentity, command: str) -> PermissionResult:
        """Check a shell command against blocked/warned patterns."""
        for pattern in self.BLOCKED_COMMANDS:
            if re.search(pattern, command, re.IGNORECASE):
                return PermissionResult(
                    decision=Decision.BLOCK,
                    reason=f"Command matches blocked pattern: '{pattern}'",
                    operation="execute",
                    agent_id=identity.agent_id,
                    risk_level="CRITICAL",
                )

        for pattern in self.WARN_COMMANDS:
            if re.search(pattern, command, re.IGNORECASE):
                return PermissionResult(
                    decision=Decision.WARN,
                    reason=f"Command matches high-risk pattern: '{pattern}'",
                    operation="execute",
                    agent_id=identity.agent_id,
                    risk_level="HIGH",
                )

        return PermissionResult(
            decision=Decision.ALLOW,
            reason="Command is permitted",
            operation="execute",
            agent_id=identity.agent_id,
        )

    def _check_filesystem(self, identity: AgentIdentity, path: str) -> PermissionResult:
        """Check filesystem path against project root and protected patterns."""
        resolved = Path(path).resolve()

        # Must stay inside project root
        try:
            resolved.relative_to(self.project_root)
        except ValueError:
            return PermissionResult(
                decision=Decision.BLOCK,
                reason=f"Path '{path}' is outside the project root '{self.project_root}'",
                operation="filesystem",
                agent_id=identity.agent_id,
                risk_level="CRITICAL",
            )

        # Check against protected path patterns
        path_str = str(resolved)
        for protected in self.protected_paths:
            pattern = re.escape(protected).replace(r"\*", ".*")
            if re.search(pattern, path_str):
                return PermissionResult(
                    decision=Decision.BLOCK,
                    reason=f"Path matches protected pattern: '{protected}'",
                    operation="filesystem",
                    agent_id=identity.agent_id,
                    risk_level="CRITICAL",
                )

        return PermissionResult(
            decision=Decision.ALLOW,
            reason="Filesystem access permitted",
            operation="filesystem",
            agent_id=identity.agent_id,
        )
