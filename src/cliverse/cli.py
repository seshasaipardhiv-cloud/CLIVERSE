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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    actions: dict[str, Callable[[], ProjectEnvironment]] = {
        "init": lambda: ProjectEnvironment.initialize(args.root),
        "status": lambda: ProjectEnvironment.load(args.root),
    }

    try:
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
