"""
FastAPI Router / REST API for Member 4 (Security + Governance + Audit)

Exposes endpoints for:
- Member 1 (Core + Laya): Pipeline evaluation, identity generation, token check.
- Member 3 (Dashboard): Audit logs, security alerts, policy management, active sessions.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import FastAPI, APIRouter, HTTPException, Query, Depends

try:
    from .trust_gate import TrustGate, PipelineEvaluation
    from .governance.policies import Policy, PolicyCategory, PolicyDecision
    from .governance.regulatory import RegulatorySource, RegulatoryUpdate
except (ImportError, ValueError):
    from trust_gate import TrustGate, PipelineEvaluation
    from governance.policies import Policy, PolicyCategory, PolicyDecision
    from governance.regulatory import RegulatorySource, RegulatoryUpdate


router = APIRouter(prefix="/api/v1/security", tags=["Security, Governance & Audit"])
gate = TrustGate()


# ── Request / Response Schemas ───────────────────────────────────────────────

class RegisterAgentRequest(BaseModel):
    cli_name: str
    scopes: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

class RegisterAgentResponse(BaseModel):
    agent_id: str
    session_id: str
    cli_name: str
    is_trusted: bool
    scopes: List[str]
    fingerprint: str
    created_at: str

class EvaluateOperationRequest(BaseModel):
    agent_id: str
    operation: str
    command: Optional[str] = None
    path: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class EvaluateOperationResponse(BaseModel):
    allowed: bool
    decision: str
    risk_level: str
    reason: str
    warnings: List[str]
    audit_event_id: Optional[str] = None

class StoreSecretRequest(BaseModel):
    key: str
    value: str
    scope: str = "global"

class AddPolicyRequest(BaseModel):
    policy_id: str
    name: str
    category: str
    description: str
    pattern: str
    decision: str
    risk_level: str = "MEDIUM"
    regulatory_ref: Optional[str] = None


# ── Identity Endpoints ───────────────────────────────────────────────────────

@router.post("/identity/register", response_model=RegisterAgentResponse)
def register_identity(req: RegisterAgentRequest):
    """Registers an AI CLI session and returns an identity token."""
    ident = gate.identity.register(
        cli_name=req.cli_name,
        scopes=req.scopes,
        metadata=req.metadata,
    )
    return RegisterAgentResponse(**ident.to_dict())

@router.get("/identity/active")
def list_active_identities():
    """Returns all registered agent sessions."""
    return [i.to_dict() for i in gate.identity.list_active()]

@router.delete("/identity/{agent_id}")
def revoke_identity(agent_id: str):
    """Revokes an agent identity."""
    success = gate.identity.revoke(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent ID not found")
    return {"status": "revoked", "agent_id": agent_id}


# ── Pipeline Evaluation Gate (For Member 1 Core) ─────────────────────────────

@router.post("/evaluate", response_model=EvaluateOperationResponse)
def evaluate_operation(req: EvaluateOperationRequest):
    """
    Main Security Pipeline Gate.
    Runs Identity, Permission, Sandbox, and Compliance evaluations.
    """
    result = gate.evaluate(
        agent_id=req.agent_id,
        operation=req.operation,
        command=req.command,
        path=req.path,
        context=req.context,
    )
    return EvaluateOperationResponse(
        allowed=result.allowed,
        decision=result.decision,
        risk_level=result.risk_level,
        reason=result.reason,
        warnings=result.warnings,
        audit_event_id=result.audit_event.event_id if result.audit_event else None,
    )


# ── Audit Endpoints (For Member 3 Dashboard) ─────────────────────────────────

@router.get("/audit/events")
def get_audit_events(
    source: Optional[str] = None,
    decision: Optional[str] = None,
    limit: int = Query(default=100, le=500),
):
    """Retrieves recent audit events for timeline / log views."""
    events = gate.audit.get_events(decision=decision, limit=limit)
    if source:
        events = [e for e in events if e.source.value == source.upper()]
    return [e.to_dict() for e in events]

@router.get("/audit/security-alerts")
def get_security_alerts():
    """Returns all blocked / warned security events."""
    return [e.to_dict() for e in gate.audit.get_security_events()]


# ── Governance & Policies ────────────────────────────────────────────────────

@router.get("/governance/policies")
def list_policies(active_only: bool = False):
    """List all machine-readable governance policies."""
    policies = gate.policies.list_active_policies() if active_only else gate.policies.list_policies()
    return [vars(p) for p in policies]

@router.post("/governance/policies")
def create_policy(req: AddPolicyRequest):
    """Add a new custom governance policy rule."""
    p = Policy(
        policy_id=req.policy_id,
        name=req.name,
        category=PolicyCategory(req.category),
        description=req.description,
        pattern=req.pattern,
        decision=PolicyDecision(req.decision),
        risk_level=req.risk_level,
        regulatory_ref=req.regulatory_ref,
    )
    gate.policies.add_policy(p)
    return {"status": "created", "policy": vars(p)}

@router.get("/governance/regulatory-sources")
def list_regulatory_sources():
    """List monitored authoritative regulatory sources (EU AI Act, GDPR, NIST, etc.)."""
    return [vars(s) for s in gate.regulatory.list_sources()]

@router.get("/governance/status")
def governance_status():
    """Returns overview stats of governance sources and updates."""
    return gate.regulatory.status_report()


# ── Secrets Management ───────────────────────────────────────────────────────

@router.post("/secrets")
def store_secret(req: StoreSecretRequest):
    """Store a secret safely (never logged in plaintext)."""
    gate.secrets.store(key=req.key, value=req.value, scope=req.scope)
    return {"status": "stored", "key": req.key}

@router.get("/secrets")
def list_secret_keys():
    """List metadata for all configured secrets (values are excluded)."""
    return [vars(s) for s in gate.secrets.list_keys()]


# ── App wrapper for direct execution ─────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="CLIVERSE Trust & Governance API",
        description="Security, Permission, Regulatory, and Audit infrastructure for AI CLIs",
        version="1.0.0",
    )
    app.include_router(router)
    return app
