"""Read-only Git status, diff and history inspection scoped to one project."""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import CliverseError


class GitUnavailable(CliverseError):
    code = "GIT_UNAVAILABLE"
    suggestion = "Install Git or check that it is available on PATH."


class NotGitRepository(CliverseError):
    code = "NOT_GIT_REPOSITORY"
    suggestion = "Pass the root directory of a Git repository."


class GitCommandFailed(CliverseError):
    code = "GIT_COMMAND_FAILED"
    suggestion = "Inspect the Git error and repository state before retrying."


class InvalidGitRequest(CliverseError):
    code = "INVALID_GIT_REQUEST"
    suggestion = "Use a history limit between 1 and 100."


@dataclass(frozen=True)
class GitStatus:
    project_root: str
    branch: str
    is_clean: bool
    changed_paths: tuple[str, ...]
    porcelain: str


@dataclass(frozen=True)
class GitCommit:
    commit_id: str
    subject: str
    session_id: str | None


@dataclass(frozen=True)
class GitInspection:
    status: GitStatus
    diff: str
    history: tuple[GitCommit, ...]


class GitInspector:
    MAX_HISTORY_LIMIT = 100
    SESSION_TRAILER = re.compile(r"^CLIVERSE-Session:\s*(\S+)\s*$", re.MULTILINE)

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        if not self.project_root.is_dir():
            raise NotGitRepository(f"Project root is not a directory: {self.project_root}")
        self._git = shutil.which("git")
        if self._git is None:
            raise GitUnavailable("Git executable is not available.")
        self._git = str(Path(self._git).resolve())

        try:
            top_level = self._run(["rev-parse", "--show-toplevel"]).stdout.strip()
        except GitCommandFailed as exc:
            raise NotGitRepository(
                f"No Git work tree found at {self.project_root}"
            ) from exc
        if not top_level:
            raise NotGitRepository(f"No Git work tree found at {self.project_root}")
        repository_root = Path(top_level).resolve()
        if repository_root != self.project_root:
            raise NotGitRepository(
                f"Project root must be the Git work-tree root; found {repository_root}"
            )

    def _run_result(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                [self._git, "--no-pager", "-C", str(self.project_root), *arguments],
                shell=False,
                cwd=self.project_root,
                env={
                    "PATH": os.defpath,
                    "LC_ALL": "C",
                    "GIT_OPTIONAL_LOCKS": "0",
                    "GIT_PAGER": "cat",
                },
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitCommandFailed("Git inspection exceeded its 10-second timeout.") from exc
        except OSError as exc:
            raise GitUnavailable(f"Could not start Git: {exc}") from exc
        return completed

    def _run(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        completed = self._run_result(arguments)
        if completed.returncode != 0:
            raise GitCommandFailed(
                completed.stderr.strip() or f"Git command failed: {arguments[0]}"
            )
        return completed

    def status(self) -> GitStatus:
        result = self._run(
            ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=all"]
        )
        tokens = result.stdout.split("\x00")
        paths: list[str] = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            index += 1
            if not token:
                continue
            if len(token) < 4:
                raise GitCommandFailed("Git returned a malformed porcelain status record.")
            status_code = token[:2]
            paths.append(token[3:])
            if "R" in status_code or "C" in status_code:
                if index >= len(tokens) or not tokens[index]:
                    raise GitCommandFailed("Git returned an incomplete rename status record.")
                paths.append(tokens[index])
                index += 1

        branch_result = self._run_result(["symbolic-ref", "--short", "HEAD"])
        if branch_result.returncode == 0:
            branch = branch_result.stdout.strip()
        else:
            head_result = self._run_result(["rev-parse", "--short", "HEAD"])
            if head_result.returncode == 0:
                branch = f"detached:{head_result.stdout.strip()}"
            elif "Needed a single revision" in head_result.stderr:
                branch = "unborn"
            else:
                raise GitCommandFailed(
                    head_result.stderr.strip() or "Could not determine the current Git branch."
                )
        return GitStatus(
            project_root=str(self.project_root),
            branch=branch,
            is_clean=not paths,
            changed_paths=tuple(paths),
            porcelain=result.stdout,
        )

    def diff(self) -> str:
        sections = [
            self._run(["diff", "--no-ext-diff", "--no-color", "--no-renames"]).stdout,
            self._run(
                ["diff", "--cached", "--no-ext-diff", "--no-color", "--no-renames"]
            ).stdout,
        ]
        untracked = self._run(["ls-files", "--others", "--exclude-standard", "-z"]).stdout
        for relative_path in (path for path in untracked.split("\x00") if path):
            prefixed_path = f"./{relative_path}"
            try:
                completed = subprocess.run(
                    [
                        self._git,
                        "--no-pager",
                        "diff",
                        "--no-index",
                        "--no-ext-diff",
                        "--no-color",
                        "/dev/null",
                        prefixed_path,
                    ],
                    shell=False,
                    cwd=self.project_root,
                    env={
                        "PATH": os.defpath,
                        "LC_ALL": "C",
                        "GIT_PAGER": "cat",
                    },
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise GitCommandFailed(
                    f"Diffing untracked file exceeded its 10-second timeout: {relative_path}"
                ) from exc
            except OSError as exc:
                raise GitUnavailable(f"Could not diff untracked file {relative_path}: {exc}") from exc
            if completed.returncode not in (0, 1):
                raise GitCommandFailed(
                    completed.stderr.strip() or f"Could not diff untracked file: {relative_path}"
                )
            sections.append(completed.stdout)
        return "".join(sections)

    def has_staged_changes(self) -> bool:
        result = self._run_result(["diff", "--cached", "--quiet"])
        if result.returncode == 0:
            return False
        if result.returncode == 1:
            return True
        raise GitCommandFailed(result.stderr.strip() or "Could not inspect the Git index.")

    def history(self, limit: int = 20) -> tuple[GitCommit, ...]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= self.MAX_HISTORY_LIMIT:
            raise InvalidGitRequest(f"History limit must be between 1 and {self.MAX_HISTORY_LIMIT}.")
        head = self._run_result(["rev-parse", "--verify", "HEAD"])
        if head.returncode != 0:
            if "Needed a single revision" in head.stderr:
                return ()
            raise GitCommandFailed(head.stderr.strip() or "Could not determine Git HEAD.")
        result = self._run(
            [
                "log",
                f"-n{limit}",
                "--format=%H%x00%s%x00%b%x00",
            ]
        )
        tokens = result.stdout.split("\x00")
        commits: list[GitCommit] = []
        index = 0
        while index + 2 < len(tokens):
            commit_id, subject, body = tokens[index : index + 3]
            index += 3
            if not commit_id:
                continue
            match = self.SESSION_TRAILER.search(body)
            commits.append(
                GitCommit(
                    commit_id=commit_id,
                    subject=subject,
                    session_id=match.group(1) if match else None,
                )
            )
        return tuple(commits)

    def commit_parents(self, commit_id: str) -> tuple[str, ...]:
        self._validate_commit_id(commit_id)
        result = self._run(["rev-list", "--parents", "-n", "1", commit_id])
        values = result.stdout.strip().split()
        if not values or values[0] != commit_id:
            raise GitCommandFailed(f"Could not inspect commit: {commit_id}")
        return tuple(values[1:])

    def files_in_commit(self, commit_id: str) -> tuple[str, ...]:
        self._validate_commit_id(commit_id)
        result = self._run(
            ["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "-z", commit_id]
        )
        return tuple(path for path in result.stdout.split("\x00") if path)

    @staticmethod
    def _validate_commit_id(commit_id: str) -> None:
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit_id):
            raise InvalidGitRequest("Commit ID must be a full hexadecimal object ID.")

    def inspect(self, limit: int = 20) -> GitInspection:
        return GitInspection(
            status=self.status(),
            diff=self.diff(),
            history=self.history(limit),
        )
