"""Command-line interface for the CLIVERSE core."""

import argparse
import json
import sqlite3
import sys
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from . import __version__
from .environment import ProjectEnvironment
from .errors import CliverseError
from .git_inspection import GitInspector
from .planning import PlanningRequest, RequestPlanner
from .sessions import SessionStore


def _emit(payload: dict[str, Any], human: bool) -> None:
    if human:
        for key, value in payload.items():
            print(f"{key}: {value}")
    else:
        print(json.dumps(payload, sort_keys=True))


def _add_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=".", help="Project directory (default: current directory)")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cliverse",
        description="Local-first AI CLI development environment",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--human",
        action="store_true",
        help="Use human-readable output instead of the default JSON",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init_parser = commands.add_parser("init", help="Initialize a project-local environment")
    _add_root_argument(init_parser)

    status_parser = commands.add_parser("status", help="Inspect initialized environment metadata")
    _add_root_argument(status_parser)

    plan_parser = commands.add_parser("plan", help="Build a structured task or request clarification")
    plan_parser.add_argument("task", nargs="?", default="")
    plan_parser.add_argument("--role", default="AI coding assistant")
    plan_parser.add_argument("--context", default="")
    plan_parser.add_argument("--requirement", action="append", default=[])
    plan_parser.add_argument("--constraint", action="append", default=[])
    plan_parser.add_argument(
        "--output",
        default="Implement the task and report verification.",
    )
    plan_parser.add_argument(
        "--clarification",
        action="append",
        default=[],
        help="Unresolved critical question from the user or a configured Laya caller",
    )
    plan_parser.add_argument(
        "--without-memory",
        action="store_true",
        help="Explicitly plan without Member 2 RAG/rules (reported in provenance)",
    )

    session_parser = commands.add_parser("session", help="Create and inspect persistent sessions")
    session_commands = session_parser.add_subparsers(dest="session_command", required=True)

    start_parser = session_commands.add_parser("start", help="Create a session for a user request")
    _add_root_argument(start_parser)
    start_parser.add_argument("--request", required=True, help="User task request to preserve")

    list_parser = session_commands.add_parser("list", help="List recent sessions")
    _add_root_argument(list_parser)
    list_parser.add_argument("--limit", type=int, default=100)

    show_parser = session_commands.add_parser("show", help="Show a session and its events")
    _add_root_argument(show_parser)
    show_parser.add_argument("session_id")
    show_parser.add_argument("--limit", type=int, default=100)

    finish_parser = session_commands.add_parser("finish", help="Mark a running session complete")
    _add_root_argument(finish_parser)
    finish_parser.add_argument("session_id")
    finish_parser.add_argument("--status", choices=("completed", "failed", "cancelled"), default="completed")

    git_parser = commands.add_parser("git", help="Read-only Git status, diff and history")
    git_commands = git_parser.add_subparsers(dest="git_command", required=True)
    git_status_parser = git_commands.add_parser("status", help="List changed paths")
    _add_root_argument(git_status_parser)
    git_diff_parser = git_commands.add_parser("diff", help="Show tracked and untracked changes")
    _add_root_argument(git_diff_parser)
    git_history_parser = git_commands.add_parser("history", help="List recent commits")
    _add_root_argument(git_history_parser)
    git_history_parser.add_argument("--limit", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    actions: dict[str, Callable[[], ProjectEnvironment]] = {
        "init": lambda: ProjectEnvironment.initialize(args.root),
        "status": lambda: ProjectEnvironment.load(args.root),
    }

    try:
        if args.command == "plan":
            result = RequestPlanner(
                allow_context_free=args.without_memory
            ).plan(
                PlanningRequest(
                    task=args.task,
                    role=args.role,
                    context=args.context,
                    requirements=tuple(args.requirement),
                    constraints=tuple(args.constraint),
                    output=args.output,
                    clarification_questions=tuple(args.clarification),
                )
            )
            payload = {
                "ok": True,
                "status": "ready" if result.ready else "needs_clarification",
                "task": result.task.as_dict() if result.task else None,
                "clarification_questions": list(result.clarification_questions),
                "context_provenance": list(result.context_provenance),
                "applicable_rule_ids": list(result.applicable_rule_ids),
            }
            _emit(payload, args.human)
            return 0

        if args.command == "session":
            environment = ProjectEnvironment.load(args.root)
            store = SessionStore(environment.metadata_dir / "cliverse.sqlite3")
            if args.session_command == "start":
                session = store.create_session(environment.root, args.request)
                payload = {"ok": True, "session": asdict(session)}
            elif args.session_command == "list":
                payload = {
                    "ok": True,
                    "sessions": [asdict(session) for session in store.list_sessions(args.limit)],
                }
            elif args.session_command == "show":
                session = store.get_session(args.session_id)
                events = store.list_events(args.session_id, args.limit)
                payload = {
                    "ok": True,
                    "session": asdict(session),
                    "events": [asdict(event) for event in events],
                }
            else:
                session = store.finish_session(args.session_id, args.status)
                payload = {"ok": True, "session": asdict(session)}
            _emit(payload, args.human)
            return 0

        if args.command == "git":
            inspector = GitInspector(args.root)
            if args.git_command == "status":
                status = inspector.status()
                payload = {
                    "ok": True,
                    "project_root": status.project_root,
                    "branch": status.branch,
                    "is_clean": status.is_clean,
                    "changed_paths": list(status.changed_paths),
                }
            elif args.git_command == "diff":
                payload = {"ok": True, "diff": inspector.diff()}
            else:
                payload = {
                    "ok": True,
                    "commits": [asdict(commit) for commit in inspector.history(args.limit)],
                }
            _emit(payload, args.human)
            return 0

        environment = actions[args.command]()
    except CliverseError as exc:
        print(json.dumps(exc.as_dict(), sort_keys=True), file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        error = {
            "error": "DatabaseError",
            "code": "DATABASE_ERROR",
            "message": str(exc),
            "suggestion": "Check that the project-local database is writable and valid.",
        }
        print(json.dumps(error, sort_keys=True), file=sys.stderr)
        return 2
    except OSError as exc:
        error = {
            "error": "OSError",
            "code": "FILESYSTEM_ERROR",
            "message": str(exc),
            "suggestion": "Check project permissions and available disk space.",
        }
        print(json.dumps(error, sort_keys=True), file=sys.stderr)
        return 2

    _emit(
        {
            "ok": True,
            "command": args.command,
            "project_root": str(environment.root),
            "metadata_dir": str(environment.metadata_dir),
            "environment_id": environment.config["environment_id"],
        },
        args.human,
    )
    return 0
