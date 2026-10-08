"""
Trust Gate — Unified Security, Governance & Audit Pipeline
Member 4: Security + Governance + Audit

Implements the complete verification pipeline for every CLI/agent operation:
    CLI/Operation
         ↓
      Identity
         ↓
     Permission
         ↓
     Sandbox Policy
         ↓
  Regulatory Policy / Compliance
         ↓
    ALLOW / WARN / BLOCK
         ↓
    Audit Logged
         ↓
     Execution

Integrates cleanly with:
- Member 1 (Core + Laya): Call `evaluate_operation()` before execution.
- Member 3 (Dashboard): Query status, security logs, policies, and active identities.
"""

from dataclasses import dataclass, field
from typing import Optional, Any
from pathlib import Path

try:
    from .security.identity import IdentityManager, AgentIdentity
    from .security.permissions import PermissionEngine, Decision, PermissionResult
    from .security.sandbox import Sandbox, SandboxPolicy, SandboxMode, SandboxViolation
    from .security.secrets import SecretsManager
    from .governance.policies import PolicyEngine, PolicyDecision, PolicyResult
    from .governance.regulatory import RegulatoryMonitor
    from .governance.compliance import ComplianceChecker, ComplianceResult
    from .audit.events import AuditLogger, AuditEvent, EventSource, EventType
except (ImportError, ValueError):
    from security.identity import IdentityManager, AgentIdentity
    from security.permissions import PermissionEngine, Decision, PermissionResult
    from security.sandbox import Sandbox, SandboxPolicy, SandboxMode, SandboxViolation
    from security.secrets import SecretsManager
    from governance.policies import PolicyEngine, PolicyDecision, PolicyResult
    from governance.regulatory import RegulatoryMonitor
    from governance.compliance import ComplianceChecker, ComplianceResult
    from audit.events import AuditLogger, AuditEvent, EventSource, EventType


@dataclass
class PipelineEvaluation:
    """Consolidated outcome of the Trust Gate security pipeline."""
    allowed: bool
    decision: str  # ALLOW | WARN | BLOCK
    risk_level: str  # LOW | MEDIUM | HIGH | CRITICAL
    reason: str
    identity: Optional[AgentIdentity] = None
    permission_result: Optional[PermissionResult] = None
    sandbox_violation: Optional[SandboxViolation] = None
    compliance_result: Optional[ComplianceResult] = None
    audit_event: Optional[AuditEvent] = None
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return f"[{self.decision}] ({self.risk_level}) {self.reason}"


class TrustGate:
    """
    Unified entrypoint for Member 4 (Trust & Control Layer).

    Coordinates Identity, Permissions, Sandbox, Compliance, Secrets, and Audit.
    """

    def __init__(
        self,
        project_root: str = ".",
        storage_dir: str = ".envcore",
        sandbox_mode: SandboxMode = SandboxMode.PERMISSIVE,
    ):
        self.project_root = Path(project_root).resolve()
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 1. Subsystems
        self.secrets = SecretsManager(storage_path=str(self.storage_dir / "secrets"))
        self.identity = IdentityManager(storage_path=str(self.storage_dir / "identities"))
        self.permissions = PermissionEngine(project_root=str(self.project_root))
        
        sandbox_policy = SandboxPolicy(
            mode=sandbox_mode,
            allowed_root=str(self.project_root),
        )
        self.sandbox = Sandbox(policy=sandbox_policy, project_root=str(self.project_root))

        self.policies = PolicyEngine()
        self.regulatory = RegulatoryMonitor(db_path=str(self.storage_dir / "governance" / "regulatory.json"))
        self.compliance = ComplianceChecker(
            policy_engine=self.policies,
            regulatory_monitor=self.regulatory,
        )
        
        self.audit = AuditLogger(
            log_dir=str(self.storage_dir / "audit"),
            secrets_manager=self.secrets,
        )

    # ------------------------------------------------------------------ #
    #  Main Pipeline Gate                                                  #
    # ------------------------------------------------------------------ #

    def evaluate(
        self,
        agent_id: str,
        operation: str,
        command: Optional[str] = None,
        path: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> PipelineEvaluation:
        """
        Executes the 5-stage Trust Gate evaluation:
        1. Identity Validation
        2. Permission & Scope Check
        3. Sandbox Boundaries
        4. Regulatory & Governance Compliance Check
        5. Audit Event Recording
        """
        warnings: list[str] = []
        op_desc = command or (f"{operation} {path}" if path else operation)

        # ── STAGE 1: Identity ──────────────────────────────────────────
        ident = self.identity.validate(agent_id)
        if not ident:
            reason = f"Unknown or revoked agent identity: {agent_id}"
            event = self.audit.log(
                source=EventSource.SECURITY,
                event_type=EventType.PERMISSION_BLOCKED,
                summary=f"Unauthenticated request blocked: {op_desc}",
                agent_id=agent_id,
                decision="BLOCK",
                risk_level="CRITICAL",
                details={"reason": reason, "operation": operation},
            )
            return PipelineEvaluation(
                allowed=False,
                decision="BLOCK",
                risk_level="CRITICAL",
                reason=reason,
                audit_event=event,
            )

        # ── STAGE 2: Permissions ───────────────────────────────────────
        perm_res = self.permissions.check(
            identity=ident,
            operation=operation,
            path=path,
            command=command,
        )
        if perm_res.decision == Decision.BLOCK:
            event = self.audit.log(
                source=EventSource.SECURITY,
                event_type=EventType.PERMISSION_BLOCKED,
                summary=f"Permission blocked: {perm_res.reason}",
                session_id=ident.session_id,
                agent_id=ident.agent_id,
                decision="BLOCK",
                risk_level=perm_res.risk_level,
                details={"operation": operation, "command": command, "path": path},
            )
            return PipelineEvaluation(
                allowed=False,
                decision="BLOCK",
                risk_level=perm_res.risk_level,
                reason=perm_res.reason,
                identity=ident,
                permission_result=perm_res,
                audit_event=event,
            )
        elif perm_res.decision == Decision.WARN:
            warnings.append(f"Permission Warning: {perm_res.reason}")

        # ── STAGE 3: Sandbox ───────────────────────────────────────────
        sandbox_allowed, violation = self.sandbox.check_operation(
            operation=operation,
            path=path,
            command=command,
        )
        if not sandbox_allowed and violation:
            event = self.audit.log(
                source=EventSource.SECURITY,
                event_type=EventType.SANDBOX_VIOLATION,
                summary=f"Sandbox violation: {violation.reason}",
                session_id=ident.session_id,
                agent_id=ident.agent_id,
                decision="BLOCK",
                risk_level=violation.severity,
                details={"violation": vars(violation)},
            )
            return PipelineEvaluation(
                allowed=False,
                decision="BLOCK",
                risk_level=violation.severity,
                reason=violation.reason,
                identity=ident,
                permission_result=perm_res,
                sandbox_violation=violation,
                audit_event=event,
            )

        # ── STAGE 4: Governance & Compliance ───────────────────────────
        eval_text = f"{op_desc} {str(context or '')}"
        comp_res = self.compliance.check(eval_text, context=context)

        if comp_res.decision == PolicyDecision.BLOCK:
            event = self.audit.log(
                source=EventSource.POLICY,
                event_type=EventType.POLICY_BLOCK,
                summary=f"Governance policy block: {comp_res.summary}",
                session_id=ident.session_id,
                agent_id=ident.agent_id,
                decision="BLOCK",
                risk_level="HIGH",
                details={"recommendations": comp_res.recommendations},
            )
            return PipelineEvaluation(
                allowed=False,
                decision="BLOCK",
                risk_level="HIGH",
                reason=comp_res.summary,
                identity=ident,
                permission_result=perm_res,
                compliance_result=comp_res,
                audit_event=event,
            )
        elif comp_res.decision == PolicyDecision.WARN:
            warnings.append(f"Policy Warning: {comp_res.summary}")

        # ── STAGE 5: Decision Resolution & Audit ───────────────────────
        decision = "WARN" if warnings else "ALLOW"
        risk_level = "MEDIUM" if warnings else "LOW"
        reason = "Operation cleared all security and compliance gates" if not warnings else " | ".join(warnings)

        event = self.audit.log(
            source=EventSource.SECURITY if not warnings else EventSource.POLICY,
            event_type=EventType.PERMISSION_ALLOWED if not warnings else EventType.PERMISSION_WARNED,
            summary=f"Gate evaluated: {decision} for {op_desc}",
            session_id=ident.session_id,
            agent_id=ident.agent_id,
            decision=decision,
            risk_level=risk_level,
            details={"operation": operation, "command": command, "path": path, "warnings": warnings},
        )

        return PipelineEvaluation(
            allowed=True,
            decision=decision,
            risk_level=risk_level,
            reason=reason,
            identity=ident,
            permission_result=perm_res,
            compliance_result=comp_res,
            audit_event=event,
            warnings=warnings,
        )
