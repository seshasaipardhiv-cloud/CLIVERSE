"""
CLIVERSE — AI CLI Execution Bridge and Provider Abstraction
============================================================

Discovers, configures, and executes real installed AI CLI binaries
(Claude Code, Gemini CLI, Codex CLI, Aider) in the target project root.

Enforces:
- Real subprocess execution with explicit cwd=project_root
- Safe argument-list invocation (no shell injection)
- Streamed stdout/stderr capture
- TrustGate authorization enforcement before launch
- Clean environment inheritance with secret scrubbing
- CLIVERSE memory, rules, and Laya context injection
- Session recording and live event broadcasting
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger("cliverse.providers")


class ProviderStatus(str, Enum):
    INSTALLED = "INSTALLED"
    NOT_INSTALLED = "NOT_INSTALLED"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


@dataclass
class ProviderInfo:
    provider_id: str
    display_name: str
    command_name: str
    status: ProviderStatus
    executable_path: Optional[str] = None
    version: Optional[str] = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    is_available: bool = False
    last_execution_at: Optional[str] = None
    last_status: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "command_name": self.command_name,
            "status": self.status.value if isinstance(self.status, ProviderStatus) else str(self.status),
            "executable_path": self.executable_path,
            "version": self.version,
            "capabilities": self.capabilities,
            "is_available": self.is_available,
            "last_execution_at": self.last_execution_at,
            "last_status": self.last_status,
            "error_message": self.error_message,
        }


@dataclass
class ProviderExecutionResult:
    provider_id: str
    command: tuple[str, ...]
    project_root: str
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    session_id: str
    status: str  # "completed", "failed", "timed_out", "blocked"
    authorization_decision: str
    authorization_reason: str
    task: str
    enriched_prompt: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_enriched_prompt(
    task: str,
    project_name: str,
    rag_items: Sequence[Any] = (),
    rules: Sequence[Any] = (),
    planning_context: Optional[str] = None,
) -> str:
    """
    Constructs the complete enriched instruction packet for the real AI CLI.
    Keeps the user's raw task and CLIVERSE intelligence context clearly delineated.
    """
    parts: list[str] = [
        "============================================================",
        "CLIVERSE AI INTELLIGENCE CONTEXT",
        f"Project: {project_name}",
        "============================================================",
    ]

    if rag_items:
        parts.append("\n--- RETRIEVED PROJECT MEMORY & KNOWLEDGE ---")
        for idx, item in enumerate(rag_items, 1):
            if hasattr(item, "content"):
                source = getattr(item, "source", "memory")
                parts.append(f"[{idx}] ({source}) {item.content.strip()}")
            elif isinstance(item, dict):
                parts.append(f"[{idx}] {item.get('content', str(item)).strip()}")
            else:
                parts.append(f"[{idx}] {str(item).strip()}")

    if rules:
        parts.append("\n--- ACTIVE ENGINEERING RULES & GOVERNANCE CONSTRAINTS ---")
        for rule in rules:
            if hasattr(rule, "content"):
                rule_id = getattr(rule, "rule_id", "rule")
                scope = getattr(rule, "scope", "project")
                parts.append(f"! [{rule_id} | scope={scope}] {rule.content.strip()}")
            elif isinstance(rule, dict):
                rule_id = rule.get("rule_id", "rule")
                parts.append(f"! [{rule_id}] {rule.get('content', rule.get('description', str(rule))).strip()}")
            else:
                parts.append(f"! {str(rule).strip()}")

    if planning_context and planning_context.strip():
        parts.append("\n--- LAYA PLANNING GUIDELINES ---")
        parts.append(planning_context.strip())

    parts.append("\n============================================================")
    parts.append("USER TASK:")
    parts.append(task.strip())
    parts.append("============================================================")

    return "\n".join(parts)


class BaseCLIAdapter(ABC):
    """
    Abstract Base Class for an AI CLI provider.
    Handles discovery, command construction, environment sanitization,
    streaming process execution, timeout handling, and output capture.
    """

    # Keys that MUST be scrubbed from child process environment
    SENSITIVE_ENV_PATTERNS = (
        "SECRET", "TOKEN", "PASSWORD", "PRIVATE", "KEY", "CREDENTIAL", "AUTH"
    )
    # Whitelisted system variables required for Node.js / Python / OS stability on Windows
    SAFE_SYSTEM_ENV_VARS = (
        "PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT",
        "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOMEDRIVE",
        "HOMEPATH", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA",
        "COMMONPROGRAMFILES", "LANG", "LC_ALL", "TERM",
    )

    def __init__(
        self,
        provider_id: str,
        display_name: str,
        default_command: str,
        custom_executable: Optional[str] = None,
        default_timeout_seconds: float = 300.0,
    ) -> None:
        self.provider_id = provider_id
        self.display_name = display_name
        self.default_command = default_command
        self.custom_executable = custom_executable
        self.default_timeout_seconds = default_timeout_seconds
        self._cached_info: Optional[ProviderInfo] = None

    def detect(self, force_refresh: bool = False) -> ProviderInfo:
        """
        Detects if the AI CLI executable exists and retrieves its version.
        Truthful: never reports an uninstalled executable as INSTALLED.
        """
        if self._cached_info and not force_refresh:
            return self._cached_info

        # Cloud / Render environment check:
        # Host workstation binaries are not available on the cloud container.
        is_render = os.environ.get("RENDER", "").lower() in ("true", "1") or "RENDER" in os.environ
        if is_render:
            self._cached_info = ProviderInfo(
                provider_id=self.provider_id,
                display_name=self.display_name,
                command_name=self.default_command,
                status=ProviderStatus.NOT_INSTALLED,
                executable_path=None,
                version=None,
                capabilities=self.get_capabilities(),
                is_available=False,
                error_message="LOCAL CLI EXECUTION AVAILABLE only on the user's local CLIVERSE machine.",
            )
            return self._cached_info

        executable_path: Optional[str] = None
        status = ProviderStatus.NOT_INSTALLED
        version: Optional[str] = None
        error_msg: Optional[str] = None

        # Check explicit custom path or environment override first
        env_var = f"CLIVERSE_{self.provider_id.upper()}_PATH"
        candidate_paths = []
        if self.custom_executable:
            candidate_paths.append(self.custom_executable)
        if os.environ.get(env_var):
            candidate_paths.append(os.environ[env_var])

        # Standard discovery on PATH
        candidate_paths.extend([
            self.default_command,
            f"{self.default_command}.cmd",
            f"{self.default_command}.exe",
            f"{self.default_command}.bat",
        ])

        # Also check AppData/Roaming/npm and Python Scripts on Windows
        userprofile = os.environ.get("USERPROFILE", "")
        if userprofile:
            candidate_paths.append(str(Path(userprofile) / "AppData" / "Roaming" / "npm" / f"{self.default_command}.cmd"))
            candidate_paths.append(str(Path(userprofile) / "AppData" / "Roaming" / "npm" / self.default_command))
        python_scripts = Path(sys.executable).parent / "Scripts"
        if python_scripts.is_dir():
            candidate_paths.append(str(python_scripts / f"{self.default_command}.exe"))
            candidate_paths.append(str(python_scripts / self.default_command))

        for candidate in candidate_paths:
            found = shutil.which(candidate)
            if found:
                executable_path = str(Path(found).resolve())
                break

        if executable_path:
            # Query version safely
            ver, ver_err = self._query_version(executable_path)
            if ver:
                version = ver
                status = ProviderStatus.INSTALLED
            else:
                # Still installed even if version query gave error/unexpected output
                status = ProviderStatus.INSTALLED
                version = "detected (unknown version)"
                if ver_err:
                    error_msg = ver_err
        else:
            status = ProviderStatus.NOT_INSTALLED

        self._cached_info = ProviderInfo(
            provider_id=self.provider_id,
            display_name=self.display_name,
            command_name=self.default_command,
            status=status,
            executable_path=executable_path,
            version=version,
            capabilities=self.get_capabilities(),
            is_available=(status == ProviderStatus.INSTALLED),
            error_message=error_msg,
        )
        return self._cached_info

    def is_available(self) -> bool:
        return self.detect().is_available

    def executable(self) -> Optional[str]:
        return self.detect().executable_path

    def version(self) -> Optional[str]:
        return self.detect().version

    def _query_version(self, executable: str) -> Tuple[Optional[str], Optional[str]]:
        """Invokes --version to inspect installed version."""
        try:
            res = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=5.0,
                shell=False,
            )
            out = res.stdout.strip() or res.stderr.strip()
            first_line = out.splitlines()[0] if out else None
            return first_line, None
        except Exception as exc:
            return None, str(exc)

    def get_capabilities(self) -> dict[str, Any]:
        """Returns provider capabilities."""
        return {
            "non_interactive": True,
            "streaming": True,
            "project_directory_isolation": True,
        }

    @abstractmethod
    def build_command(
        self,
        task: str,
        enriched_prompt: str,
        project_root: str,
        non_interactive: bool = True,
    ) -> list[str]:
        """Builds the exact argument list for subprocess execution."""
        raise NotImplementedError

    def prepare_environment(
        self,
        project_root: str,
        extra_env: Optional[Mapping[str, str]] = None,
    ) -> dict[str, str]:
        """
        Prepares a safe environment for the child process.
        Passes essential OS/runtime environment while scrubbing secrets.
        """
        env: dict[str, str] = {}

        # Pass safe system variables
        for key, val in os.environ.items():
            key_upper = key.upper()
            # Retain system and runtime basics
            if key_upper in self.SAFE_SYSTEM_ENV_VARS or key_upper.startswith("PATH"):
                env[key] = val
            elif any(s in key_upper for s in self.SENSITIVE_ENV_PATTERNS):
                # Omit sensitive keys unless specifically needed for that CLI
                continue
            else:
                # Include standard benign environment variables
                env[key] = val

        # Set execution metadata
        env["CLIVERSE_MANAGED"] = "1"
        env["CLIVERSE_PROJECT_ROOT"] = str(Path(project_root).resolve())

        if extra_env:
            for k, v in extra_env.items():
                env[k] = v

        return env

    def execute(
        self,
        task: str,
        enriched_prompt: str,
        project_root: str,
        session_id: str,
        authorization_decision: str = "ALLOW",
        authorization_reason: str = "Authorized by TrustGate",
        timeout_seconds: Optional[float] = None,
        extra_env: Optional[Mapping[str, str]] = None,
        on_stdout_line: Optional[Callable[[str], None]] = None,
        on_stderr_line: Optional[Callable[[str], None]] = None,
    ) -> ProviderExecutionResult:
        """
        Executes the real CLI subprocess in project_root.
        Streams stdout and stderr live via callbacks and records results.
        """
        info = self.detect()
        if not info.is_available or not info.executable_path:
            raise FileNotFoundError(
                f"Provider '{self.display_name}' executable not found. Status: {info.status.value}"
            )

        root = Path(project_root).resolve()
        if not root.is_dir():
            raise NotADirectoryError(f"Target project root is not a directory: {project_root}")

        cmd = self.build_command(
            task=task,
            enriched_prompt=enriched_prompt,
            project_root=str(root),
            non_interactive=True,
        )

        timeout = timeout_seconds or self.default_timeout_seconds
        child_env = self.prepare_environment(str(root), extra_env)

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        started_at = time.monotonic()
        timed_out = False

        logger.info("Starting real CLI: %s in %s", cmd, root)

        try:
            # We use subprocess.Popen with pipes for real streaming
            process = subprocess.Popen(
                cmd,
                cwd=str(root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=child_env,
                shell=False,
            )
        except OSError as exc:
            duration = time.monotonic() - started_at
            return ProviderExecutionResult(
                provider_id=self.provider_id,
                command=tuple(cmd),
                project_root=str(root),
                returncode=-1,
                stdout="",
                stderr=f"Failed to spawn process: {exc}",
                duration_seconds=duration,
                session_id=session_id,
                status="failed",
                authorization_decision=authorization_decision,
                authorization_reason=authorization_reason,
                task=task,
                enriched_prompt=enriched_prompt,
            )

        def _reader(stream, line_list, callback):
            try:
                for line in iter(stream.readline, ""):
                    line_list.append(line)
                    if callback:
                        try:
                            callback(line)
                        except Exception as e:
                            logger.warning("Stream callback error: %s", e)
            finally:
                stream.close()

        t_out = threading.Thread(target=_reader, args=(process.stdout, stdout_lines, on_stdout_line), daemon=True)
        t_err = threading.Thread(target=_reader, args=(process.stderr, stderr_lines, on_stderr_line), daemon=True)
        t_out.start()
        t_err.start()

        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            logger.warning("CLI execution timed out after %s seconds. Terminating...", timeout)
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        t_out.join(timeout=2.0)
        t_err.join(timeout=2.0)

        duration = time.monotonic() - started_at
        returncode = process.returncode if process.returncode is not None else -1

        status = "completed" if returncode == 0 and not timed_out else ("timed_out" if timed_out else "failed")

        # Update last execution state on info
        info.last_execution_at = datetime.now(timezone.utc).isoformat()
        info.last_status = status

        return ProviderExecutionResult(
            provider_id=self.provider_id,
            command=tuple(cmd),
            project_root=str(root),
            returncode=returncode,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
            duration_seconds=duration,
            session_id=session_id,
            status=status,
            authorization_decision=authorization_decision,
            authorization_reason=authorization_reason,
            task=task,
            enriched_prompt=enriched_prompt,
        )


class ClaudeCLIAdapter(BaseCLIAdapter):
    """
    Real Claude Code Adapter.
    Executes: claude -p "<enriched_prompt>"
    """

    def __init__(self, custom_executable: Optional[str] = None) -> None:
        super().__init__(
            provider_id="claude",
            display_name="Claude Code",
            default_command="claude",
            custom_executable=custom_executable,
        )

    def build_command(
        self,
        task: str,
        enriched_prompt: str,
        project_root: str,
        non_interactive: bool = True,
    ) -> list[str]:
        exe = self.executable() or self.default_command
        # Claude Code print/non-interactive mode is -p / --print
        if non_interactive:
            return [exe, "-p", enriched_prompt]
        return [exe, enriched_prompt]


class GeminiCLIAdapter(BaseCLIAdapter):
    """
    Real Gemini CLI Adapter.
    Executes: gemini -p "<enriched_prompt>"
    """

    def __init__(self, custom_executable: Optional[str] = None) -> None:
        super().__init__(
            provider_id="gemini",
            display_name="Gemini CLI",
            default_command="gemini",
            custom_executable=custom_executable,
        )

    def build_command(
        self,
        task: str,
        enriched_prompt: str,
        project_root: str,
        non_interactive: bool = True,
    ) -> list[str]:
        exe = self.executable() or self.default_command
        # Gemini CLI prompt mode is -p / --prompt
        if non_interactive:
            return [exe, "-p", enriched_prompt]
        return [exe, enriched_prompt]


class CodexCLIAdapter(BaseCLIAdapter):
    """
    Real Codex CLI Adapter.
    Executes: codex exec "<enriched_prompt>"
    """

    def __init__(self, custom_executable: Optional[str] = None) -> None:
        super().__init__(
            provider_id="codex",
            display_name="Codex CLI",
            default_command="codex",
            custom_executable=custom_executable,
        )

    def build_command(
        self,
        task: str,
        enriched_prompt: str,
        project_root: str,
        non_interactive: bool = True,
    ) -> list[str]:
        exe = self.executable() or self.default_command
        # Codex non-interactive execution uses 'exec' subcommand
        if non_interactive:
            return [exe, "exec", enriched_prompt]
        return [exe, enriched_prompt]


class AiderCLIAdapter(BaseCLIAdapter):
    """
    Real Aider Adapter.
    Executes: aider --message "<enriched_prompt>" --no-git
    Note: --no-git is mandatory to preserve CLIVERSE's authoritative Git recovery pipeline.
    """

    def __init__(self, custom_executable: Optional[str] = None) -> None:
        super().__init__(
            provider_id="aider",
            display_name="Aider",
            default_command="aider",
            custom_executable=custom_executable,
        )

    def build_command(
        self,
        task: str,
        enriched_prompt: str,
        project_root: str,
        non_interactive: bool = True,
    ) -> list[str]:
        exe = self.executable() or self.default_command
        # Aider one-shot execution with --no-git to keep CLIVERSE Git governance
        if non_interactive:
            return [exe, "--message", enriched_prompt, "--no-git"]
        return [exe, "--message", enriched_prompt]


class AgyCLIAdapter(BaseCLIAdapter):
    """
    Real Antigravity CLI Adapter (agy).
    Executes: agy -p "<enriched_prompt>"
    """

    def __init__(self, custom_executable: Optional[str] = None) -> None:
        super().__init__(
            provider_id="agy",
            display_name="Antigravity CLI (agy)",
            default_command="agy",
            custom_executable=custom_executable,
        )

    def build_command(
        self,
        task: str,
        enriched_prompt: str,
        project_root: str,
        non_interactive: bool = True,
    ) -> list[str]:
        exe = self.executable() or self.default_command
        if non_interactive:
            return [exe, "-p", enriched_prompt]
        return [exe, "-i", enriched_prompt]


class GenericExecutableAdapter(BaseCLIAdapter):
    """
    Generic adapter for testing or custom user-configured tools.
    Allows configuring custom arguments template and flags.
    """

    def __init__(
        self,
        provider_id: str,
        display_name: str,
        executable_path: str,
        args_template: Optional[list[str]] = None,
        default_timeout_seconds: float = 300.0,
    ) -> None:
        super().__init__(
            provider_id=provider_id,
            display_name=display_name,
            default_command=executable_path,
            custom_executable=executable_path,
            default_timeout_seconds=default_timeout_seconds,
        )
        self.args_template = args_template or ["{prompt}"]

    def build_command(
        self,
        task: str,
        enriched_prompt: str,
        project_root: str,
        non_interactive: bool = True,
    ) -> list[str]:
        exe = self.executable() or self.default_command
        cmd = [exe]
        for arg in self.args_template:
            cmd.append(arg.replace("{prompt}", enriched_prompt).replace("{task}", task))
        return cmd


class CLIProviderRegistry:
    """
    Central registry for all AI CLI providers.
    Supports autodiscovery, configurable overrides via .cliverse/providers.json,
    and lookup by provider ID or alias.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path
        self._providers: dict[str, BaseCLIAdapter] = {}
        self._initialize_default_providers()
        self._load_config()

    def _initialize_default_providers(self) -> None:
        self.register(ClaudeCLIAdapter())
        self.register(GeminiCLIAdapter())
        self.register(CodexCLIAdapter())
        self.register(AiderCLIAdapter())
        self.register(AgyCLIAdapter())

    def register(self, adapter: BaseCLIAdapter) -> None:
        self._providers[adapter.provider_id.lower()] = adapter

    def get(self, name_or_alias: str) -> Optional[BaseCLIAdapter]:
        name = name_or_alias.strip().lower()
        # Aliases
        alias_map = {
            "claude-code": "claude",
            "anthropic": "claude",
            "gemini-cli": "gemini",
            "google": "gemini",
            "codex-cli": "codex",
            "openai": "codex",
            "aider-chat": "aider",
            "antigravity": "agy",
            "google-agy": "agy",
        }
        resolved = alias_map.get(name, name)
        return self._providers.get(resolved)

    def detect_all(self, force_refresh: bool = False) -> dict[str, ProviderInfo]:
        """Detects status for all registered providers."""
        results: dict[str, ProviderInfo] = {}
        for pid, adapter in self._providers.items():
            results[pid] = adapter.detect(force_refresh=force_refresh)
        return results

    def list_providers(self, force_refresh: bool = False) -> list[ProviderInfo]:
        return list(self.detect_all(force_refresh=force_refresh).values())

    def _load_config(self) -> None:
        """Loads optional provider overrides from config file."""
        if not self.config_path or not self.config_path.exists():
            return
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            providers_cfg = data.get("providers", {})
            for pid, cfg in providers_cfg.items():
                if pid in self._providers and isinstance(cfg, dict):
                    adapter = self._providers[pid]
                    if "executable" in cfg:
                        adapter.custom_executable = cfg["executable"]
                    if "timeout_seconds" in cfg:
                        adapter.default_timeout_seconds = float(cfg["timeout_seconds"])
        except Exception as e:
            logger.warning("Failed to load providers config from %s: %s", self.config_path, e)


# Global default registry instance
provider_registry = CLIProviderRegistry()
