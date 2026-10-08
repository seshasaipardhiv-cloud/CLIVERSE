"""
Trust Gate — Unified Security, Governance & Audit Pipeline
Member 4: Security + Governance + Audit

Coordinates the complete 5-stage verification pipeline with explicit user
confirmation requirements for WARN decisions and strict sandbox isolation.
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional, Any, Dict
from pathlib import Path

try:
    from .security.identity import IdentityManager, AgentIdentity, ScopeViolationError
    from .security.permissions import PermissionEngine, Decision, PermissionResult
    from .security.sandbox import Sandbox, SandboxPolicy, SandboxMode, SandboxViolation
    from .security.secrets import SecretsManager
    from .governance.policies import PolicyEngine, PolicyDecision, PolicyResult
    from .governance.regulatory import RegulatoryMonitor
    from .governance.compliance import ComplianceChecker, ComplianceResult
    from .audit.events import AuditLogger, AuditEvent, EventSource, EventType
except (ImportError, ValueError):
    from security.identity import IdentityManager, AgentIdentity, ScopeViolationError
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
    requires_user_confirmation: bool = False
    confirmation_token: Optional[str] = None
    identity: Optional[AgentIdentity] = None
    permission_result: Optional[PermissionResult] = None
    sandbox_violation: Optional[SandboxViolation] = None
    compliance_result: Optional[ComplianceResult] = None
    audit_event: Optional[AuditEvent] = None
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        conf_str = " [CONFIRMATION REQUIRED]" if self.requires_user_confirmation else ""
        return f"[{self.decision}] ({self.risk_level}){conf_str} {self.reason}"


class TrustGate:
    """
    Unified entrypoint for Member 4 Trust, Governance, and Audit.
    Enforces Strict Sandboxing, Scope Authorization, and User Confirmation on Warnings.
    """

    def __init__(
        self,
        project_root: str = ".",
        storage_dir: str = ".envcore",
        sandbox_mode: SandboxMode = SandboxMode.STRICT,
        admin_secret: str = "cliverse-admin-default-key",
    ):
        self.project_root = Path(project_root).resolve()
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.admin_secret = admin_secret

        self.secrets = SecretsManager(storage_path=str(self.storage_dir / "secrets"))
        self.identity = IdentityManager(
            storage_path=str(self.storage_dir / "identities"),
            admin_secret=self.admin_secret,
        )
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
        
        # Pending confirmation tokens for WARN states
        self._pending_confirmations: Dict[str, Dict[str, Any]] = {}

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
        user_confirmed: bool = False,
    ) -> PipelineEvaluation:
        """
        Executes the 5-stage Trust Gate evaluation:
        1. Identity & Scope Authorization
        2. Scoped Permissions & Blocked Pattern Check
        3. Strict Sandbox Process Boundary Check
        4. Regulatory Compliance & Policy Evaluation
        5. User Confirmation Requirement for Warnings & Chain-Hashed Audit
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

        # ── STAGE 3: Strict Sandbox ────────────────────────────────────
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

        # ── STAGE 5: Decision Resolution & User Confirmation ───────────
        if warnings:
            if not user_confirmed:
                # Generate confirmation token and block execution until confirmed
                token = str(uuid.uuid4())
                self._pending_confirmations[token] = {
                    "agent_id": agent_id,
                    "operation": operation,
                    "command": command,
                    "path": path,
                    "warnings": warnings,
                }
                event = self.audit.log(
                    source=EventSource.SECURITY,
                    event_type=EventType.PERMISSION_WARNED,
                    summary=f"Operation flagged with warnings; awaiting user confirmation: {op_desc}",
                    session_id=ident.session_id,
                    agent_id=ident.agent_id,
                    decision="WARN",
                    risk_level="HIGH",
                    details={"warnings": warnings, "confirmation_token": token},
                )
                return PipelineEvaluation(
                    allowed=False,  # Blocked until explicit confirmation
                    decision="WARN",
                    risk_level="HIGH",
                    reason="Operation flagged with security/policy warnings. Explicit user confirmation required.",
                    requires_user_confirmation=True,
                    confirmation_token=token,
                    identity=ident,
                    permission_result=perm_res,
                    compliance_result=comp_res,
                    audit_event=event,
                    warnings=warnings,
                )
            else:
                # User provided explicit confirmation
                event = self.audit.log(
                    source=EventSource.USER,
                    event_type=EventType.APPROVAL,
                    summary=f"User confirmed execution despite warnings: {op_desc}",
                    session_id=ident.session_id,
                    agent_id=ident.agent_id,
                    decision="ALLOW",
                    risk_level="MEDIUM",
                    details={"warnings": warnings},
                )
                return PipelineEvaluation(
                    allowed=True,
                    decision="WARN_CONFIRMED",
                    risk_level="MEDIUM",
                    reason="Operation approved following explicit user confirmation",
                    requires_user_confirmation=False,
                    identity=ident,
                    permission_result=perm_res,
                    compliance_result=comp_res,
                    audit_event=event,
                    warnings=warnings,
                )

        # Clean allow
        event = self.audit.log(
            source=EventSource.SECURITY,
            event_type=EventType.PERMISSION_ALLOWED,
            summary=f"Gate evaluated: ALLOW for {op_desc}",
            session_id=ident.session_id,
            agent_id=ident.agent_id,
            decision="ALLOW",
            risk_level="LOW",
            details={"operation": operation, "command": command, "path": path},
        )

        return PipelineEvaluation(
            allowed=True,
            decision="ALLOW",
            risk_level="LOW",
            reason="Operation cleared all security and compliance gates",
            identity=ident,
            permission_result=perm_res,
            compliance_result=comp_res,
            audit_event=event,
            warnings=[],
        )

    def confirm_warning(self, confirmation_token: str) -> PipelineEvaluation:
        """Confirms a previously warned operation using its confirmation token."""
        pending = self._pending_confirmations.pop(confirmation_token, None)
        if not pending:
            raise ValueError(f"Invalid or expired confirmation token: {confirmation_token}")
        
        return self.evaluate(
            agent_id=pending["agent_id"],
            operation=pending["operation"],
            command=pending.get("command"),
            path=pending.get("path"),
            user_confirmed=True,
        )
