"""Command-line interface for the CLIVERSE core."""

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any

from . import __version__
from .environment import ProjectEnvironment
from .errors import CliverseError


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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    actions: dict[str, Callable[[], ProjectEnvironment]] = {
        "init": lambda: ProjectEnvironment.initialize(args.root),
        "status": lambda: ProjectEnvironment.load(args.root),
    }

    try:
        environment = actions[args.command]()
    except CliverseError as exc:
        print(json.dumps(exc.as_dict(), sort_keys=True), file=sys.stderr)
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
