"""Fail-closed external CLI execution through an injected authorizer."""

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .contracts import (
    AuthorizationDecision,
    AuthorizationRequest,
    Authorizer,
    require_authorized,
)
from .errors import CliverseError


class AuthorizationUnavailable(CliverseError):
    code = "AUTHORIZER_UNAVAILABLE"
    suggestion = "Connect Member 4's confirmed authorizer before enabling CLI execution."


class InvalidProcessRequest(CliverseError):
    code = "INVALID_PROCESS_REQUEST"
    suggestion = "Provide an executable, argument list, project root and bounded timeout."


class CliUnavailable(CliverseError):
    code = "CLI_UNAVAILABLE"
    suggestion = "Check the configured executable path and project permissions."


class CliTimeout(CliverseError):
    code = "CLI_TIMEOUT"
    suggestion = "Reduce the task scope or increase the explicit timeout within the supported limit."


@dataclass(frozen=True)
class ProcessRequest:
    executable: str
    arguments: tuple[str, ...]
    project_root: str
    identity: str
    timeout_seconds: float = 60.0
    environment: Mapping[str, str] | None = None
    warning_confirmed: bool = False


@dataclass(frozen=True)
class ExecutionResult:
    executable: str
    arguments: tuple[str, ...]
    project_root: str
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    authorization_decision: str
    authorization_reason: str


class CliExecutionFailed(CliverseError):
    code = "CLI_NONZERO_EXIT"
    suggestion = "Review the CLI output and session logs; the operation did not succeed."

    def __init__(self, result: ExecutionResult) -> None:
        self.result = result
        super().__init__(
            f"CLI exited with status {result.returncode}: {result.executable}"
        )


class CliAdapter:
    """Run a process with a fixed cwd, argv, timeout and explicit environment."""

    MAX_TIMEOUT_SECONDS = 3600.0
    RESERVED_ENVIRONMENT_KEYS = {"PATH", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME"}

    def _prepare(self, request: ProcessRequest) -> ProcessRequest:
        if not isinstance(request.project_root, (str, os.PathLike)):
            raise InvalidProcessRequest("Project root must be a filesystem path.")
        project_root = Path(request.project_root).expanduser().resolve()
        if not project_root.is_dir():
            raise InvalidProcessRequest(f"Project root is not a directory: {project_root}")
        if not isinstance(request.executable, str) or not request.executable.strip():
            raise InvalidProcessRequest("Executable must be a non-empty string.")
        if "\x00" in request.executable:
            raise InvalidProcessRequest("Executable must not contain a null byte.")
        if not isinstance(request.arguments, (tuple, list)) or any(
            not isinstance(argument, str) or "\x00" in argument
            for argument in request.arguments
        ):
            raise InvalidProcessRequest("Arguments must be a list of valid strings.")
        if (
            isinstance(request.timeout_seconds, bool)
            or not isinstance(request.timeout_seconds, (int, float))
            or not 0 < request.timeout_seconds <= self.MAX_TIMEOUT_SECONDS
        ):
            raise InvalidProcessRequest(
                f"Timeout must be greater than 0 and at most {self.MAX_TIMEOUT_SECONDS} seconds."
            )
        if not isinstance(request.identity, str) or not request.identity.strip():
            raise InvalidProcessRequest("An execution identity is required.")
        if not isinstance(request.warning_confirmed, bool):
            raise InvalidProcessRequest("Warning confirmation must be a boolean.")

        resolved_executable = shutil.which(request.executable)
        if resolved_executable is None:
            raise CliUnavailable(f"Executable was not found: {request.executable}")
        executable = str(Path(resolved_executable).expanduser().resolve())

        if request.environment is not None and not isinstance(request.environment, Mapping):
            raise InvalidProcessRequest(
                "Environment must be a mapping of explicit string keys and values."
            )
        child_environment = {"PATH": os.defpath, "LANG": "C.UTF-8"}
        for key, value in (request.environment or {}).items():
            if (
                not isinstance(key, str)
                or not key
                or "=" in key
                or "\x00" in key
                or not isinstance(value, str)
                or "\x00" in value
            ):
                raise InvalidProcessRequest("Environment keys and values must be valid strings.")
            if key.upper() in self.RESERVED_ENVIRONMENT_KEYS:
                raise InvalidProcessRequest(f"Environment key cannot be overridden: {key}")
            child_environment[key] = value
        return ProcessRequest(
            executable=executable,
            arguments=tuple(request.arguments),
            project_root=str(project_root),
            identity=request.identity,
            timeout_seconds=request.timeout_seconds,
            environment=child_environment,
            warning_confirmed=request.warning_confirmed,
        )

    def _run_prepared(
        self,
        request: ProcessRequest,
        authorization: AuthorizationDecision,
    ) -> ExecutionResult:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                [request.executable, *request.arguments],
                shell=False,
                cwd=request.project_root,
                env=dict(request.environment or {}),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=request.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CliTimeout(
                f"CLI exceeded its {request.timeout_seconds}-second timeout."
            ) from exc
        except OSError as exc:
            raise CliUnavailable(
                f"Could not start executable {request.executable}: {exc}"
            ) from exc

        result = ExecutionResult(
            executable=request.executable,
            arguments=request.arguments,
            project_root=request.project_root,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=time.monotonic() - started,
            authorization_decision=authorization.decision.value,
            authorization_reason=authorization.reason,
        )
        if result.returncode != 0:
            raise CliExecutionFailed(result)
        return result


def execute_guarded(
    request: ProcessRequest,
    authorizer: Authorizer | None,
    *,
    adapter: CliAdapter | None = None,
) -> ExecutionResult:
    """Authorize first; missing, malformed, blocked or unconfirmed decisions stop."""
    if authorizer is None:
        raise AuthorizationUnavailable("No Member 4 authorizer is configured.")

    process_adapter = adapter or CliAdapter()
    prepared_request = process_adapter._prepare(request)
    authorization_request = AuthorizationRequest(
        identity=prepared_request.identity,
        operation="execute",
        project_root=prepared_request.project_root,
        executable=prepared_request.executable,
        arguments=prepared_request.arguments,
    )
    decision: AuthorizationDecision = authorizer.authorize(authorization_request)
    require_authorized(decision, warning_confirmed=request.warning_confirmed)
    return process_adapter._run_prepared(prepared_request, decision)
