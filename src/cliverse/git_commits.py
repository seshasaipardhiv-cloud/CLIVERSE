"""Explicit, path-scoped Git commits linked to a CLIVERSE session."""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .contracts import AuthorizationDecision, AuthorizationRequest, Authorizer, require_authorized
from .errors import CliverseError
from .git_inspection import GitCommandFailed, GitInspector


class GitCommitConfirmationRequired(CliverseError):
    code = "GIT_COMMIT_CONFIRMATION_REQUIRED"
    suggestion = "Review the diff and explicitly confirm the commit."


class GitCommitNotSafe(CliverseError):
    code = "GIT_COMMIT_NOT_SAFE"
    suggestion = "Review the work tree and requested paths; do not stage unrelated changes."


class GitCommitFailed(CliverseError):
    code = "GIT_COMMIT_FAILED"
    suggestion = "Inspect Git state; requested paths may remain staged after a failed commit."


@dataclass(frozen=True)
class GitCommitResult:
    commit_id: str
    session_id: str
    summary: str
    paths: tuple[str, ...]
    authorization_decision: str


class GitCommitter:
    """Stage only explicitly named changed paths and record a session trailer."""

    def __init__(self, project_root: str | Path) -> None:
        self._inspector = GitInspector(project_root)
        self.project_root = self._inspector.project_root
        executable = shutil.which("git")
        if executable is None:
            raise GitCommitFailed("Git executable is not available.")
        self._git = str(Path(executable).resolve())

    def commit_changes(
        self,
        session_id: str,
        identity: str,
        summary: str,
        paths: Sequence[str],
        authorizer: Authorizer | None,
        *,
        confirmed: bool = False,
    ) -> GitCommitResult:
        if not isinstance(confirmed, bool) or not confirmed:
            raise GitCommitConfirmationRequired("Git commit requires explicit confirmation.")
        if authorizer is None:
            raise GitCommitNotSafe("No Member 4 authorizer is configured.")
        if not isinstance(identity, str) or not identity.strip():
            raise GitCommitNotSafe("A valid execution identity is required.")
        if not isinstance(session_id, str) or not session_id.strip():
            raise GitCommitNotSafe("A non-empty session ID is required.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", session_id):
            raise GitCommitNotSafe("Session ID contains unsupported characters.")
        if (
            not isinstance(summary, str)
            or not summary.strip()
            or "\n" in summary
            or "\r" in summary
            or len(summary.strip()) > 200
        ):
            raise GitCommitNotSafe("Commit summary must be a single line of at most 200 characters.")

        normalized_paths = self._normalize_paths(paths)
        status = self._inspector.status()
        if status.is_clean:
            raise GitCommitNotSafe("There are no changes to commit.")
        if self._inspector.has_staged_changes():
            raise GitCommitNotSafe("Refusing to mix with changes already staged by the user.")
        if set(status.changed_paths) != set(normalized_paths):
            raise GitCommitNotSafe(
                "Requested paths must exactly match all changed paths; unrelated changes are present."
            )
        reviewed_diff = self._inspector.diff()

        request = AuthorizationRequest(
            identity=identity,
            operation="git_commit",
            project_root=str(self.project_root),
            paths=normalized_paths,
            executable=self._git,
            arguments=("add", "--", *normalized_paths),
        )
        decision: AuthorizationDecision = authorizer.authorize(request)
        require_authorized(decision, warning_confirmed=confirmed)

        current_status = self._inspector.status()
        if (
            current_status.changed_paths != status.changed_paths
            or self._inspector.has_staged_changes()
            or self._inspector.diff() != reviewed_diff
        ):
            raise GitCommitNotSafe("Repository state changed after the authorization check.")

        self._run_git(
            ["add", "--", *(f":(literal){path}" for path in normalized_paths)]
        )
        staged_status = self._inspector.status()
        if set(staged_status.changed_paths) != set(normalized_paths):
            raise GitCommitNotSafe("Staged paths differ from the authorized path set.")
        self._run_git(
            [
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "core.fsmonitor=false",
                "commit",
                "--no-verify",
                "-m",
                f"CLIVERSE: {summary.strip()}",
                "-m",
                f"CLIVERSE-Session: {session_id}",
            ]
        )
        latest = self._inspector.history(1)
        if not latest or latest[0].session_id != session_id:
            raise GitCommitFailed("Git commit completed without the expected session trailer.")
        return GitCommitResult(
            commit_id=latest[0].commit_id,
            session_id=session_id,
            summary=summary.strip(),
            paths=normalized_paths,
            authorization_decision=decision.decision.value,
        )

    def _normalize_paths(self, paths: Sequence[str]) -> tuple[str, ...]:
        if not isinstance(paths, (tuple, list)) or not paths:
            raise GitCommitNotSafe("At least one changed path must be specified.")
        normalized: list[str] = []
        for raw_path in paths:
            if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path:
                raise GitCommitNotSafe("Changed paths must be non-empty strings.")
            candidate = Path(raw_path)
            if candidate.is_absolute():
                raise GitCommitNotSafe(f"Paths must be relative to the project: {raw_path}")
            resolved = (self.project_root / candidate).resolve()
            try:
                relative = resolved.relative_to(self.project_root)
            except ValueError as exc:
                raise GitCommitNotSafe(f"Path escapes the project root: {raw_path}") from exc
            if not relative.parts or relative.parts[0] == ".git":
                raise GitCommitNotSafe(f"Path is not a project file: {raw_path}")
            normalized_path = relative.as_posix()
            if normalized_path in normalized:
                raise GitCommitNotSafe(f"Duplicate path: {normalized_path}")
            normalized.append(normalized_path)
        return tuple(sorted(normalized))

    def _run_git(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                [
                    self._git,
                    "--no-pager",
                    "-C",
                    str(self.project_root),
                    *arguments,
                ],
                shell=False,
                cwd=self.project_root,
                env={
                    "PATH": os.defpath,
                    "HOME": str(Path.home()),
                    "LC_ALL": "C",
                    "GIT_OPTIONAL_LOCKS": "0",
                    "GIT_PAGER": "cat",
                    "GIT_EDITOR": "true",
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_CONFIG_NOSYSTEM": "1",
                },
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitCommitFailed("Git operation exceeded its 30-second timeout.") from exc
        except OSError as exc:
            raise GitCommitFailed(f"Could not start Git: {exc}") from exc
        if result.returncode != 0:
            raise GitCommitFailed(result.stderr.strip() or "Git operation failed.")
        return result
