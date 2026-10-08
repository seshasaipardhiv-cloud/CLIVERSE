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
from .recovery import GitRecovery
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
    undo_preview_parser = git_commands.add_parser(
        "undo-preview",
        help="Preview a tagged session commit that may be eligible for undo",
    )
    _add_root_argument(undo_preview_parser)
    undo_preview_parser.add_argument("--session-id", required=True)

    # AI CLI Provider commands
    providers_parser = commands.add_parser("providers", help="List AI CLI provider detection status")
    _add_root_argument(providers_parser)
    providers_parser.add_argument("--human", action="store_true", help="Display readable summary")

    run_parser = commands.add_parser("run", help="Execute task with real AI CLI provider")
    run_parser.add_argument("task", help="User task to execute")
    run_parser.add_argument("--cli", required=True, choices=("claude", "gemini", "codex", "aider"), help="AI CLI provider")
    _add_root_argument(run_parser)
    run_parser.add_argument("--confirm-warning", action="store_true", help="Confirm TrustGate warnings")
    run_parser.add_argument("--timeout", type=float, default=300.0, help="Execution timeout in seconds")
    run_parser.add_argument("--human", action="store_true", help="Display formatted readable stream")
    run_parser.add_argument("--json", action="store_true", help="Output JSON instead of readable stream")

    for provider_name in ("claude", "gemini", "codex", "aider"):
        p_parser = commands.add_parser(provider_name, help=f"Run task using real {provider_name.capitalize()} CLI")
        p_parser.add_argument("task", help="User task to execute")
        _add_root_argument(p_parser)
        p_parser.add_argument("--confirm-warning", action="store_true", help="Confirm TrustGate warnings")
        p_parser.add_argument("--timeout", type=float, default=300.0, help="Execution timeout in seconds")
        p_parser.add_argument("--human", action="store_true", help="Display formatted readable stream")
        p_parser.add_argument("--json", action="store_true", help="Output JSON instead of readable stream")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    actions: dict[str, Callable[[], ProjectEnvironment]] = {
        "init": lambda: ProjectEnvironment.initialize(args.root),
        "status": lambda: ProjectEnvironment.load(args.root),
    }

    try:
        if args.command == "providers":
            from .providers import provider_registry
            providers = provider_registry.list_providers(force_refresh=True)
            if args.human:
                print("CLIVERSE CLI PROVIDERS")
                print("─" * 42)
                for p in providers:
                    status_symbol = "✓" if p.is_available else "✗"
                    print(f"{status_symbol} {p.display_name}")
                    print(f"  command:    {p.command_name}")
                    print(f"  status:     {p.status.value}")
                    if p.executable_path:
                        print(f"  path:       {p.executable_path}")
                    if p.version:
                        print(f"  version:    {p.version}")
                    print()
                print("─" * 42)
            else:
                _emit({"ok": True, "providers": [p.to_dict() for p in providers]}, False)
            return 0

        if args.command in ("run", "claude", "gemini", "codex", "aider"):
            from pathlib import Path
            from .orchestrator import ExecutionOrchestrator
            provider = getattr(args, "cli", None) or args.command
            root = getattr(args, "root", ".")
            task = args.task
            user_confirmed = getattr(args, "confirm_warning", False)
            timeout = getattr(args, "timeout", 300.0)
            use_json = getattr(args, "json", False)

            if not use_json:
                print("CLIVERSE")
                print("─" * 42)
                print(f"Project       {Path(root).resolve()}")
                print(f"Provider      {provider.capitalize()}")
                print(f"Task          {task}")
                print()

            def _on_stdout(line: str) -> None:
                if not use_json:
                    sys.stdout.write(line)
                    sys.stdout.flush()

            def _on_stderr(line: str) -> None:
                if not use_json:
                    sys.stderr.write(line)
                    sys.stderr.flush()

            def _event_sink(evt) -> None:
                if use_json:
                    return
                if evt.phase == "MEMORY":
                    print(f"MEMORY\n✓ {evt.message}\n")
                elif evt.phase == "TRUSTGATE":
                    if "Authorized" in evt.message:
                        print(f"TRUSTGATE\n✓ {evt.message}\n")
                    elif "BLOCKED" in evt.message:
                        print(f"TRUSTGATE\n✗ {evt.message}\n")
                elif evt.phase == "EXECUTION" and "Spawning" in evt.message:
                    print(f"EXECUTION\n→ Starting {provider.capitalize()}...\n")

            orchestrator = ExecutionOrchestrator(project_root=root, event_sink=_event_sink)
            result = orchestrator.run(
                provider_name=provider,
                task=task,
                user_confirmed=user_confirmed,
                timeout_seconds=timeout,
                on_stdout=_on_stdout,
                on_stderr=_on_stderr,
            )

            if use_json:
                _emit(result.to_dict(), False)
            else:
                print()
                if result.ok:
                    print(f"✓ {provider.capitalize()} exited with code {result.returncode}")
                else:
                    print(f"✗ {provider.capitalize()} failed: {result.error_message or result.status} (exit code {result.returncode})")

                print(f"\nSession:      {result.session_id}")
                print(f"Duration:     {result.duration_seconds:.2f}s")
                print("Dashboard:    http://127.0.0.1:8000")
                print("─" * 42)
            return result.returncode if result.returncode >= 0 else 1

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
            db_candidates = [
                environment.metadata_dir / "sessions" / "sessions.db",
                environment.metadata_dir / "cliverse.sqlite3",
            ]
            db_path = next((p for p in db_candidates if p.exists()), environment.metadata_dir / "sessions" / "sessions.db")
            store = SessionStore(db_path)
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
            elif args.git_command == "history":
                payload = {
                    "ok": True,
                    "commits": [asdict(commit) for commit in inspector.history(args.limit)],
                }
            else:
                preview = GitRecovery(args.root).preview(args.session_id)
                payload = {
                    "ok": True,
                    "status": "preview_only",
                    "requires_confirmation": True,
                    "requires_authorization": True,
                    "session_id": preview.session_id,
                    "target_commit": preview.target_commit,
                    "changed_paths": list(preview.changed_paths),
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


if __name__ == "__main__":
    sys.exit(main())

