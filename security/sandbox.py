"""
Sandbox — Security Layer

Provides scoped execution restrictions for CLI agents.
Validates operations against a sandboxed environment definition
before allowing execution. Tracks all operations for audit.

Note: Full OS-level sandboxing (containers, seccomp) is a production concern.
This module provides the logical control layer that sits above execution.
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class SandboxMode(str, Enum):
    STRICT = "strict"       # Only allowed list — everything else blocked
    PERMISSIVE = "permissive"  # Everything allowed unless explicitly blocked
    DRY_RUN = "dry_run"     # Nothing actually executed — audit only


@dataclass
class SandboxPolicy:
    """Defines the operational boundaries for a CLI agent."""

    mode: SandboxMode = SandboxMode.PERMISSIVE
    allowed_root: str = "."
    allowed_commands: list[str] = field(default_factory=list)
    blocked_commands: list[str] = field(default_factory=list)
    allowed_extensions: list[str] = field(default_factory=list)
    block_network: bool = False
    max_file_size_mb: int = 10
    max_ops_per_session: int = 500

    @classmethod
    def default_strict(cls, project_root: str) -> "SandboxPolicy":
        return cls(
            mode=SandboxMode.STRICT,
            allowed_root=project_root,
            allowed_commands=["git", "python", "node", "npm", "pip", "ls", "cat", "echo"],
            blocked_commands=["rm -rf", "dd", "mkfs", "shutdown", "reboot"],
            allowed_extensions=[
                ".py", ".ts", ".js", ".tsx", ".jsx", ".md",
                ".json", ".yaml", ".yml", ".toml", ".txt",
                ".html", ".css", ".sql", ".sh", ".go",
            ],
            block_network=False,
            max_file_size_mb=10,
            max_ops_per_session=500,
        )

    @classmethod
    def default_permissive(cls, project_root: str) -> "SandboxPolicy":
        return cls(
            mode=SandboxMode.PERMISSIVE,
            allowed_root=project_root,
            blocked_commands=["rm -rf /", "dd if=", "mkfs", ":(){:|:&};:"],
            block_network=False,
        )


@dataclass
class SandboxViolation:
    operation: str
    reason: str
    severity: str  # LOW | MEDIUM | HIGH | CRITICAL


class Sandbox:
    """
    Logical sandbox for CLIVERSE CLI agents.

    Enforces SandboxPolicy rules before any operation is executed.
    Tracks operation count per session to detect runaway agents.

    Usage:
        policy = SandboxPolicy.default_strict(project_root="/my/project")
        sandbox = Sandbox(policy=policy)
        ok, violation = sandbox.check_operation("write", path="/my/project/src/main.py")
    """

    def __init__(self, policy: Optional[SandboxPolicy] = None, project_root: str = "."):
        self.policy = policy or SandboxPolicy.default_permissive(project_root)
        self.project_root = Path(project_root).resolve()
        self._op_count: int = 0
        self._violations: list[SandboxViolation] = []

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def check_operation(
        self,
        operation: str,
        path: Optional[str] = None,
        command: Optional[str] = None,
    ) -> tuple[bool, Optional[SandboxViolation]]:
        """
        Validate an operation against the sandbox policy.
        Returns (True, None) if allowed, (False, violation) if blocked.
        """
        # 1. Dry-run mode — nothing executes
        if self.policy.mode == SandboxMode.DRY_RUN:
            self._op_count += 1
            return False, SandboxViolation(
                operation=operation,
                reason="Sandbox is in DRY_RUN mode — no operations execute",
                severity="LOW",
            )

        # 2. Rate limit check
        if self._op_count >= self.policy.max_ops_per_session:
            violation = SandboxViolation(
                operation=operation,
                reason=f"Operation limit reached ({self.policy.max_ops_per_session} ops/session)",
                severity="HIGH",
            )
            self._violations.append(violation)
            return False, violation

        # 3. Command restriction
        if command:
            violation = self._check_command(command)
            if violation:
                self._violations.append(violation)
                return False, violation

        # 4. Filesystem restriction
        if path:
            violation = self._check_path(path)
            if violation:
                self._violations.append(violation)
                return False, violation

        self._op_count += 1
        return True, None

    def violations(self) -> list[SandboxViolation]:
        """Return all violations recorded in this session."""
        return list(self._violations)

    def op_count(self) -> int:
        return self._op_count

    def reset_session(self) -> None:
        """Reset counters for a new session."""
        self._op_count = 0
        self._violations.clear()

    # ------------------------------------------------------------------ #
    #  Internal checks                                                     #
    # ------------------------------------------------------------------ #

    def _check_command(self, command: str) -> Optional[SandboxViolation]:
        # Always block explicit blocked commands
        for blocked in self.policy.blocked_commands:
            if re.search(re.escape(blocked), command, re.IGNORECASE):
                return SandboxViolation(
                    operation="execute",
                    reason=f"Command '{command}' matches blocked pattern '{blocked}'",
                    severity="CRITICAL",
                )

        # In STRICT mode, only explicitly allowed commands pass
        if self.policy.mode == SandboxMode.STRICT and self.policy.allowed_commands:
            cmd_base = command.strip().split()[0] if command.strip() else ""
            if cmd_base not in self.policy.allowed_commands:
                return SandboxViolation(
                    operation="execute",
                    reason=f"Command '{cmd_base}' is not in the allowed list (strict mode)",
                    severity="HIGH",
                )
        return None

    def _check_path(self, path: str) -> Optional[SandboxViolation]:
        try:
            resolved = Path(path).resolve()
            resolved.relative_to(self.project_root)
        except ValueError:
            return SandboxViolation(
                operation="filesystem",
                reason=f"Path '{path}' is outside sandbox root '{self.project_root}'",
                severity="CRITICAL",
            )

        # Check file extension in strict mode
        if self.policy.mode == SandboxMode.STRICT and self.policy.allowed_extensions:
            ext = Path(path).suffix
            if ext and ext not in self.policy.allowed_extensions:
                return SandboxViolation(
                    operation="filesystem",
                    reason=f"File extension '{ext}' is not in the allowed list",
                    severity="MEDIUM",
                )

        # Check file size if file exists
        p = Path(path)
        if p.exists() and p.is_file():
            size_mb = p.stat().st_size / (1024 * 1024)
            if size_mb > self.policy.max_file_size_mb:
                return SandboxViolation(
                    operation="filesystem",
                    reason=f"File size {size_mb:.1f}MB exceeds limit {self.policy.max_file_size_mb}MB",
                    severity="MEDIUM",
                )
        return None
