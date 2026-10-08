"""
Sandbox — Security Layer

Provides scoped process execution boundaries, environment scrubbing,
and isolation for CLI agent operations.

Defaults to STRICT mode to ensure fail-closed isolation.
"""

import os
import re
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum


class SandboxMode(str, Enum):
    STRICT = "strict"          # Default: Only explicitly allowed operations pass
    PERMISSIVE = "permissive"  # Allows operations unless matching blocked patterns
    DRY_RUN = "dry_run"        # Simulation only — no actual execution


@dataclass
class SandboxPolicy:
    """Defines the operational boundaries for a CLI agent."""

    mode: SandboxMode = SandboxMode.STRICT
    allowed_root: str = "."
    allowed_commands: list[str] = field(default_factory=lambda: [
        "git", "python", "node", "npm", "pip", "ls", "cat", "echo", "pytest", "uvicorn", "cargo", "go",
        "claude", "gemini", "codex", "aider", "agy"
    ])
    blocked_commands: list[str] = field(default_factory=lambda: [
        "rm -rf /", "dd if=", "mkfs", "shutdown", "reboot", ":(){:|:&};:", "chmod 777 /"
    ])
    allowed_extensions: list[str] = field(default_factory=lambda: [
        ".py", ".ts", ".js", ".tsx", ".jsx", ".md",
        ".json", ".yaml", ".yml", ".toml", ".txt",
        ".html", ".css", ".sql", ".sh", ".go", ".rs",
    ])
    block_network: bool = False
    max_file_size_mb: int = 10
    max_ops_per_session: int = 500
    execution_timeout_seconds: int = 30


@dataclass
class SandboxViolation:
    operation: str
    reason: str
    severity: str  # LOW | MEDIUM | HIGH | CRITICAL


class Sandbox:
    """
    Process-aware Sandbox for CLIVERSE CLI agents.

    Features:
    - Defaults to STRICT mode for fail-closed security.
    - Environment Variable Scrubbing: Removes sensitive credentials before spawning subprocesses.
    - Execution Boundaries: Enforces timeouts, directory jail, and command validation.
    """

    SENSITIVE_ENV_KEYS = {
        "AWS_SECRET_ACCESS_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
        "GITHUB_TOKEN", "DATABASE_PASSWORD", "PRIVATE_KEY", "JWT_SECRET"
    }

    def __init__(self, policy: Optional[SandboxPolicy] = None, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self.policy = policy or SandboxPolicy(mode=SandboxMode.STRICT, allowed_root=str(self.project_root))
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
        Returns (True, None) if permitted, (False, violation) if blocked.
        """
        if self.policy.mode == SandboxMode.DRY_RUN:
            self._op_count += 1
            return False, SandboxViolation(
                operation=operation,
                reason="Sandbox is in DRY_RUN mode — no operations execute",
                severity="LOW",
            )

        if self._op_count >= self.policy.max_ops_per_session:
            violation = SandboxViolation(
                operation=operation,
                reason=f"Operation rate limit exceeded ({self.policy.max_ops_per_session} ops/session)",
                severity="HIGH",
            )
            self._violations.append(violation)
            return False, violation

        if command:
            violation = self._check_command(command)
            if violation:
                self._violations.append(violation)
                return False, violation

        if path:
            violation = self._check_path(path)
            if violation:
                self._violations.append(violation)
                return False, violation

        self._op_count += 1
        return True, None

    def execute_contained(
        self,
        command: str,
        cwd: Optional[str] = None,
        custom_env: Optional[Dict[str, str]] = None,
    ) -> tuple[int, str, str]:
        """
        Executes a shell command inside an isolated environment:
        - Scrubs sensitive API keys and secrets from the child process environment.
        - Enforces strict working directory containment.
        - Enforces execution timeout to prevent runaway hangs.
        """
        # Pre-execution validation
        allowed, violation = self.check_operation("execute", command=command)
        if not allowed:
            raise PermissionError(f"Sandbox execution blocked: {violation.reason if violation else 'Policy block'}")

        # Scrub environment
        clean_env = os.environ.copy()
        for key in self.SENSITIVE_ENV_KEYS:
            clean_env.pop(key, None)
        if custom_env:
            clean_env.update(custom_env)

        working_dir = Path(cwd or self.project_root).resolve()
        try:
            working_dir.relative_to(self.project_root)
        except ValueError:
            raise PermissionError(f"Working directory '{working_dir}' is outside project root '{self.project_root}'")

        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=str(working_dir),
                env=clean_env,
                capture_output=True,
                text=True,
                timeout=self.policy.execution_timeout_seconds,
            )
            return res.returncode, res.stdout, res.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"Execution timed out after {self.policy.execution_timeout_seconds} seconds"

    def violations(self) -> list[SandboxViolation]:
        return list(self._violations)

    def reset_session(self) -> None:
        self._op_count = 0
        self._violations.clear()

    # ------------------------------------------------------------------ #
    #  Internal Validation                                                 #
    # ------------------------------------------------------------------ #

    def _check_command(self, command: str) -> Optional[SandboxViolation]:
        for blocked in self.policy.blocked_commands:
            if re.search(re.escape(blocked), command, re.IGNORECASE):
                return SandboxViolation(
                    operation="execute",
                    reason=f"Command '{command}' matches blocked pattern '{blocked}'",
                    severity="CRITICAL",
                )

        if self.policy.mode == SandboxMode.STRICT and self.policy.allowed_commands:
            cmd_base = command.strip().split()[0] if command.strip() else ""
            # Handle path/arguments in cmd_base (support Windows .exe, .cmd, .bat stems)
            cmd_name = Path(cmd_base).name.lower()
            cmd_stem = Path(cmd_base).stem.lower()
            allowed_names = {Path(c).name.lower() for c in self.policy.allowed_commands}
            allowed_stems = {Path(c).stem.lower() for c in self.policy.allowed_commands}
            if (cmd_name not in allowed_names and cmd_stem not in allowed_stems) and not any(command.startswith(c) for c in self.policy.allowed_commands):
                return SandboxViolation(
                    operation="execute",
                    reason=f"Command binary '{cmd_base}' is not in sandbox allowlist (Strict Mode)",
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

        if self.policy.mode == SandboxMode.STRICT and self.policy.allowed_extensions:
            ext = Path(path).suffix.lower()
            if ext and ext not in [e.lower() for e in self.policy.allowed_extensions]:
                return SandboxViolation(
                    operation="filesystem",
                    reason=f"File extension '{ext}' is not permitted in strict sandbox",
                    severity="MEDIUM",
                )

        p = Path(path)
        if p.exists() and p.is_file():
            size_mb = p.stat().st_size / (1024 * 1024)
            if size_mb > self.policy.max_file_size_mb:
                return SandboxViolation(
                    operation="filesystem",
                    reason=f"File size {size_mb:.1f}MB exceeds sandbox limit {self.policy.max_file_size_mb}MB",
                    severity="MEDIUM",
                )
        return None
