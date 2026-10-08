"""
CLIVERSE — End-to-End Execution Orchestrator
==============================================

Orchestrates the complete invariant pipeline:
USER COMMAND / REQUEST
       ↓
PROJECT DETECTION
       ↓
TASK NORMALIZATION
       ↓
MEMBER 2 MEMORY / RAG & RULES
       ↓
LAYA INTELLIGENCE CONTEXT
       ↓
MEMBER 1 PLANNING
       ↓
MEMBER 4 TRUSTGATE AUTHORIZATION
       ↓
REAL AI CLI SUBPROCESS (Claude / Gemini / Codex / Aider)
       ↓
STDOUT / STDERR LIVE STREAMING
       ↓
SESSION & EVENT RECORDING
       ↓
DASHBOARD ACTIVITY EVENT EMISSION
"""

import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .contracts import Decision as Member1Decision
from .environment import ProjectEnvironment
from .planning import PlanningRequest, RequestPlanner
from .providers import (
    BaseCLIAdapter,
    ProviderExecutionResult,
    build_enriched_prompt,
    provider_registry,
)
from .sessions import SessionStore

# Safe imports for Member 2 & Member 4
try:
    from memory.adapter import CliverseMemoryProviderAdapter
    from memory.intelligence import LayaIntelligenceContext, LayaIntelligenceService, RuleDecision
except ImportError:
    CliverseMemoryProviderAdapter = None  # type: ignore[assignment,misc]
    LayaIntelligenceService = None  # type: ignore[assignment,misc]
    RuleDecision = None  # type: ignore[assignment,misc]

try:
    from trust_gate import TrustGate, PipelineEvaluation
    from security.sandbox import SandboxMode
except ImportError:
    TrustGate = None  # type: ignore[assignment,misc]
    PipelineEvaluation = None  # type: ignore[assignment,misc]
    SandboxMode = None  # type: ignore[assignment,misc]

logger = logging.getLogger("cliverse.orchestrator")


@dataclass
class OrchestrationEvent:
    timestamp: str
    phase: str
    message: str
    level: str = "INFO"
    data: Optional[dict[str, Any]] = None


@dataclass
class OrchestrationResult:
    ok: bool
    session_id: str
    provider_id: str
    project_root: str
    task: str
    status: str  # "completed", "failed", "blocked", "timed_out", "error"
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    memory_count: int
    rule_decision: str
    trust_gate_decision: str
    trust_gate_reason: str
    error_message: Optional[str] = None
    events: list[OrchestrationEvent] = None  # type: ignore[assignment]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "session_id": self.session_id,
            "provider_id": self.provider_id,
            "project_root": self.project_root,
            "task": self.task,
            "status": self.status,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
            "memory_count": self.memory_count,
            "rule_decision": self.rule_decision,
            "trust_gate_decision": self.trust_gate_decision,
            "trust_gate_reason": self.trust_gate_reason,
            "error_message": self.error_message,
        }


class ExecutionOrchestrator:
    """
    Main orchestration engine executing the 8-stage pipeline.
    """

    def __init__(
        self,
        project_root: Optional[str | Path] = None,
        event_sink: Optional[Callable[[OrchestrationEvent], None]] = None,
    ) -> None:
        self.project_root = Path(project_root or ".").resolve()
        self.event_sink = event_sink
        self.events: list[OrchestrationEvent] = []

    def _emit_event(self, phase: str, message: str, level: str = "INFO", data: Optional[dict[str, Any]] = None) -> None:
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
        evt = OrchestrationEvent(timestamp=now_str, phase=phase, message=message, level=level, data=data)
        self.events.append(evt)
        if self.event_sink:
            try:
                self.event_sink(evt)
            except Exception as e:
                logger.warning("Event sink error: %s", e)

    def run(
        self,
        provider_name: str,
        task: str,
        user_confirmed: bool = False,
        timeout_seconds: Optional[float] = None,
        on_stdout: Optional[Callable[[str], None]] = None,
        on_stderr: Optional[Callable[[str], None]] = None,
    ) -> OrchestrationResult:
        started_at = time.monotonic()
        clean_task = task.strip()
        if not clean_task:
            return OrchestrationResult(
                ok=False,
                session_id="",
                provider_id=provider_name,
                project_root=str(self.project_root),
                task=task,
                status="error",
                returncode=-1,
                stdout="",
                stderr="Task cannot be empty.",
                duration_seconds=0.0,
                memory_count=0,
                rule_decision="UNKNOWN",
                trust_gate_decision="BLOCK",
                trust_gate_reason="Empty task",
                error_message="Task cannot be empty.",
                events=self.events,
            )

        # ── 1. PROJECT DETECTION & ENVIRONMENT ──────────────────────────────
        self._emit_event("PROJECT", f"Detecting environment at {self.project_root}")
        project_id = self.project_root.name or "cliverse-core"
        try:
            env = ProjectEnvironment.load(str(self.project_root))
            metadata_dir = env.metadata_dir
            project_id = env.config.get("environment_id", project_id)
        except Exception:
            # Fallback to local .envcore or .cliverse
            metadata_dir = self.project_root / ".envcore"
            metadata_dir.mkdir(parents=True, exist_ok=True)

        session_db = metadata_dir / "sessions" / "sessions.db"
        session_db.parent.mkdir(parents=True, exist_ok=True)
        session_store = SessionStore(session_db)
        session = session_store.create_session(str(self.project_root), clean_task)
        session_id = session.session_id
        self._emit_event("SESSION", f"Created session {session_id}", data={"session_id": session_id})

        # ── 2. PROVIDER DISCOVERY ───────────────────────────────────────────
        self._emit_event("PROVIDER", f"Resolving AI CLI provider '{provider_name}'")
        adapter = provider_registry.get(provider_name)
        if adapter is None:
            err = f"Unknown provider '{provider_name}'. Supported: claude, gemini, codex, aider"
            self._emit_event("PROVIDER", err, level="ERROR")
            session_store.finish_session(session_id, "failed")
            return OrchestrationResult(
                ok=False,
                session_id=session_id,
                provider_id=provider_name,
                project_root=str(self.project_root),
                task=clean_task,
                status="error",
                returncode=-1,
                stdout="",
                stderr=err,
                duration_seconds=time.monotonic() - started_at,
                memory_count=0,
                rule_decision="UNKNOWN",
                trust_gate_decision="BLOCK",
                trust_gate_reason=err,
                error_message=err,
                events=self.events,
            )

        info = adapter.detect()
        if not info.is_available or not info.executable_path:
            err = (
                f"Provider '{adapter.display_name}' executable '{adapter.default_command}' "
                f"is not installed or not in PATH."
            )
            self._emit_event("PROVIDER", err, level="ERROR")
            session_store.finish_session(session_id, "failed")
            return OrchestrationResult(
                ok=False,
                session_id=session_id,
                provider_id=adapter.provider_id,
                project_root=str(self.project_root),
                task=clean_task,
                status="failed",
                returncode=-1,
                stdout="",
                stderr=err,
                duration_seconds=time.monotonic() - started_at,
                memory_count=0,
                rule_decision="UNKNOWN",
                trust_gate_decision="BLOCK",
                trust_gate_reason="Executable not found",
                error_message=err,
                events=self.events,
            )

        self._emit_event("PROVIDER", f"Found {adapter.display_name} at {info.executable_path} ({info.version or 'version ok'})")

        # ── 3. MEMBER 2: MEMORY / RAG & RULES ───────────────────────────────
        self._emit_event("MEMORY", "Querying project memory & rules knowledge...")
        rag_items: list[Any] = []
        rules: list[Any] = []
        planning_text: Optional[str] = None
        rule_dec_str = "ALLOW"

        if LayaIntelligenceService is not None:
            try:
                intel_service = LayaIntelligenceService()
                intel_ctx: LayaIntelligenceContext = intel_service.build_intelligence_context(
                    task=clean_task,
                    project_id=project_id,
                    cli_name=f"{adapter.provider_id}-cli",
                )
                rag_items = intel_ctx.memory_context.items
                rules = intel_ctx.applicable_rules
                planning_text = intel_ctx.combined_laya_context
                rule_dec_str = getattr(intel_ctx.rule_decision, "value", str(intel_ctx.rule_decision))
                self._emit_event(
                    "MEMORY",
                    f"Retrieved {len(rag_items)} memory items. Rules decision: {rule_dec_str}",
                    data={"count": len(rag_items), "rules_count": len(rules), "decision": rule_dec_str},
                )
            except Exception as e:
                logger.warning("Member 2 intelligence lookup warning: %s", e)
                self._emit_event("MEMORY", f"Memory lookup skipped/warning: {e}", level="WARN")

        # Record retrieval event in session
        try:
            session_store.add_event(
                session_id=session_id,
                source="MEMORY",
                event_type="context_retrieved",
                summary=f"Retrieved {len(rag_items)} memories, rules: {rule_dec_str}",
                details={"memory_count": len(rag_items), "rules_count": len(rules), "decision": rule_dec_str},
            )
        except Exception:
            pass

        # ── 4. MEMBER 1: PLANNING & PROMPT ENRICHMENT ───────────────────────
        self._emit_event("PLANNING", "Assembling enriched AI instruction packet...")
        enriched_prompt = build_enriched_prompt(
            task=clean_task,
            project_name=project_id,
            rag_items=rag_items,
            rules=rules,
            planning_context=planning_text,
        )

        # ── 5. MEMBER 4: TRUSTGATE AUTHORIZATION ─────────────────────────────
        self._emit_event("TRUSTGATE", "Evaluating security, sandbox, and policy boundaries...")
        tg_allowed = True
        tg_decision = "ALLOW"
        tg_reason = "Default allow (TrustGate unmounted)"

        if TrustGate is not None:
            try:
                storage_dir = str(metadata_dir)
                gate = TrustGate(
                    project_root=str(self.project_root),
                    storage_dir=storage_dir,
                    sandbox_mode=SandboxMode.STRICT if SandboxMode else None,
                )
                cli_name = f"{adapter.provider_id}-cli"
                agent_ident = None
                for existing in gate.identity.list_active():
                    if existing.cli_name == cli_name and existing.is_trusted:
                        agent_ident = existing
                        break
                if not agent_ident:
                    try:
                        agent_ident = gate.identity.register(
                            cli_name=cli_name,
                            scopes=["read", "write", "git", "execute"],
                            admin_token=gate.admin_secret,
                            metadata={"role": "cli_runner", "provider": adapter.provider_id},
                        )
                    except Exception:
                        pass

                agent_id = agent_ident.agent_id if agent_ident else cli_name

                evaluation: PipelineEvaluation = gate.evaluate(
                    agent_id=agent_id,
                    operation="execute",
                    command=f"{adapter.executable()} -p",
                    path=str(self.project_root),
                    user_confirmed=user_confirmed,
                )
                tg_allowed = evaluation.allowed
                tg_decision = evaluation.decision
                tg_reason = evaluation.reason

                if not tg_allowed:
                    self._emit_event("TRUSTGATE", f"BLOCKED: {tg_reason}", level="ERROR")
                    try:
                        session_store.add_event(
                            session_id=session_id,
                            source="TRUSTGATE",
                            event_type="execution_blocked",
                            summary=tg_reason,
                            details={"decision": tg_decision, "reason": tg_reason},
                            decision=tg_decision,
                        )
                    except Exception:
                        pass
                    session_store.finish_session(session_id, "failed")
                    return OrchestrationResult(
                        ok=False,
                        session_id=session_id,
                        provider_id=adapter.provider_id,
                        project_root=str(self.project_root),
                        task=clean_task,
                        status="blocked",
                        returncode=-1,
                        stdout="",
                        stderr=f"Execution blocked by TrustGate: {tg_reason}",
                        duration_seconds=time.monotonic() - started_at,
                        memory_count=len(rag_items),
                        rule_decision=rule_dec_str,
                        trust_gate_decision=tg_decision,
                        trust_gate_reason=tg_reason,
                        error_message=f"TrustGate Blocked: {tg_reason}",
                        events=self.events,
                    )
                else:
                    self._emit_event("TRUSTGATE", f"Authorized [{tg_decision}]: {tg_reason}")
            except Exception as e:
                logger.warning("TrustGate evaluation exception: %s", e)
                tg_reason = f"TrustGate exception: {e}"

        # ── 6. REAL CLI SUBPROCESS EXECUTION ────────────────────────────────
        self._emit_event("EXECUTION", f"Spawning real {adapter.display_name} process in {self.project_root}")
        try:
            session_store.add_event(
                session_id=session_id,
                source="CLI",
                event_type="process_started",
                summary=f"Process started: {adapter.provider_id}",
                details={"provider": adapter.provider_id, "executable": adapter.executable()},
            )
        except Exception:
            pass

        exec_res: ProviderExecutionResult = adapter.execute(
            task=clean_task,
            enriched_prompt=enriched_prompt,
            project_root=str(self.project_root),
            session_id=session_id,
            authorization_decision=tg_decision,
            authorization_reason=tg_reason,
            timeout_seconds=timeout_seconds,
            on_stdout_line=on_stdout,
            on_stderr_line=on_stderr,
        )

        total_duration = time.monotonic() - started_at
        final_ok = (exec_res.returncode == 0 and exec_res.status == "completed")

        # ── 7. FINALIZE SESSION & LOGS ──────────────────────────────────────
        self._emit_event(
            "EXECUTION",
            f"Process exited with code {exec_res.returncode} ({exec_res.status}) in {exec_res.duration_seconds:.2f}s",
            level="INFO" if final_ok else "ERROR",
        )
        try:
            session_store.add_event(
                session_id=session_id,
                source="CLI",
                event_type="process_exited",
                summary=f"Process exited with code {exec_res.returncode}",
                details={
                    "returncode": exec_res.returncode,
                    "status": exec_res.status,
                    "duration_seconds": exec_res.duration_seconds,
                },
            )
            session_store.finish_session(session_id, "completed" if final_ok else "failed")
        except Exception:
            pass

        return OrchestrationResult(
            ok=final_ok,
            session_id=session_id,
            provider_id=adapter.provider_id,
            project_root=str(self.project_root),
            task=clean_task,
            status=exec_res.status,
            returncode=exec_res.returncode,
            stdout=exec_res.stdout,
            stderr=exec_res.stderr,
            duration_seconds=total_duration,
            memory_count=len(rag_items),
            rule_decision=rule_dec_str,
            trust_gate_decision=tg_decision,
            trust_gate_reason=tg_reason,
            error_message=None if final_ok else f"CLI exited with code {exec_res.returncode}",
            events=self.events,
        )
