"""Confirmation- and authorization-gated recovery for CLIVERSE session commits."""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .contracts import AuthorizationDecision, AuthorizationRequest, Authorizer, require_authorized
from .errors import CliverseError
from .git_inspection import GitCommandFailed, GitInspector


class UndoConfirmationRequired(CliverseError):
    code = "UNDO_CONFIRMATION_REQUIRED"
    suggestion = "Review the target session commit and explicitly confirm this undo."


class UndoNotSafe(CliverseError):
    code = "UNDO_NOT_SAFE"
    suggestion = "Review the Git work tree and target session commit before retrying."


class RecoveryFailed(CliverseError):
    code = "RECOVERY_FAILED"
    suggestion = "Inspect Git state; if a revert is in progress, resolve or abort it manually."


@dataclass(frozen=True)
class UndoPreview:
    session_id: str
    target_commit: str
    changed_paths: tuple[str, ...]


@dataclass(frozen=True)
class UndoResult:
    session_id: str
    reverted_commit: str
    recovery_commit: str
    changed_paths: tuple[str, ...]
    authorization_decision: str


class GitRecovery:
    """Revert only a clean work tree's current HEAD when tagged to this session."""

    def __init__(self, project_root: str | Path) -> None:
        self._inspector = GitInspector(project_root)
        self.project_root = self._inspector.project_root
        self._git = shutil.which("git")
        if self._git is None:
            raise RecoveryFailed("Git executable is not available.")
        self._git = str(Path(self._git).resolve())

    def preview(self, session_id: str) -> UndoPreview:
        if not isinstance(session_id, str) or not session_id.strip():
            raise UndoNotSafe("A non-empty session ID is required.")
        status = self._inspector.status()
        if not status.is_clean:
            raise UndoNotSafe("Refusing undo because the work tree has uncommitted changes.")
        latest = self._inspector.history(1)
        if not latest:
            raise UndoNotSafe("Repository has no commit to undo.")
        target = latest[0]
        if target.session_id != session_id:
            raise UndoNotSafe(
                "The current HEAD is not tagged as the requested CLIVERSE session."
            )
        parents = self._inspector.commit_parents(target.commit_id)
        if len(parents) != 1:
            raise UndoNotSafe("Only non-merge commits with one parent can be undone.")
        return UndoPreview(
            session_id=session_id,
            target_commit=target.commit_id,
            changed_paths=self._inspector.files_in_commit(target.commit_id),
        )

    def undo(
        self,
        session_id: str,
        identity: str,
        authorizer: Authorizer | None,
        *,
        confirmed: bool = False,
    ) -> UndoResult:
        if not isinstance(confirmed, bool) or not confirmed:
            raise UndoConfirmationRequired("Undo requires explicit confirmation.")
        if authorizer is None:
            raise UndoNotSafe("No Member 4 authorizer is configured.")
        if not isinstance(identity, str) or not identity.strip():
            raise UndoNotSafe("A valid execution identity is required.")

        preview = self.preview(session_id)
        request = AuthorizationRequest(
            identity=identity,
            operation="git_revert",
            project_root=str(self.project_root),
            paths=preview.changed_paths,
            executable=self._git,
            arguments=("revert", "--no-edit", preview.target_commit),
        )
        decision: AuthorizationDecision = authorizer.authorize(request)
        require_authorized(decision, warning_confirmed=confirmed)

        current = self.preview(session_id)
        if current != preview:
            raise UndoNotSafe("Repository state changed after the authorization check.")

        try:
            result = subprocess.run(
                [
                    self._git,
                    "--no-pager",
                    "-C",
                    str(self.project_root),
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-c",
                    "core.fsmonitor=false",
                    "revert",
                    "--no-edit",
                    preview.target_commit,
                ],
                shell=False,
                cwd=self.project_root,
                env={
                    "PATH": os.defpath,
                    "LC_ALL": "C",
                    "GIT_OPTIONAL_LOCKS": "0",
                    "GIT_PAGER": "cat",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
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
            raise RecoveryFailed("Git revert exceeded its 30-second timeout.") from exc
        except OSError as exc:
            raise RecoveryFailed(f"Could not start Git revert: {exc}") from exc

        if result.returncode != 0:
            raise RecoveryFailed(result.stderr.strip() or "Git revert failed.")
        if not self._inspector.status().is_clean:
            raise RecoveryFailed("Git revert returned success but left a dirty work tree.")
        history = self._inspector.history(1)
        if not history or history[0].commit_id == preview.target_commit:
            raise RecoveryFailed("Git revert completed without creating a recovery commit.")

        return UndoResult(
            session_id=session_id,
            reverted_commit=preview.target_commit,
            recovery_commit=history[0].commit_id,
            changed_paths=preview.changed_paths,
            authorization_decision=decision.decision.value,
        )
