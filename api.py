"""
FastAPI Router / REST API for Member 4 (Security + Governance + Audit)

Implements secure authentication & role-based authorization for sensitive
endpoints (secrets, policy administration, privileged scope assignment).
"""

import os
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import FastAPI, APIRouter, HTTPException, Query, Depends, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

try:
    from .trust_gate import TrustGate, PipelineEvaluation
    from .governance.policies import Policy, PolicyCategory, PolicyDecision
    from .governance.regulatory import RegulatorySource, RegulatoryUpdate
    from .security.identity import ScopeViolationError
except (ImportError, ValueError):
    from trust_gate import TrustGate, PipelineEvaluation
    from governance.policies import Policy, PolicyCategory, PolicyDecision
    from governance.regulatory import RegulatorySource, RegulatoryUpdate
    from security.identity import ScopeViolationError


router = APIRouter(prefix="/api/v1/security", tags=["Security, Governance & Audit"])
gate = TrustGate()
security_scheme = HTTPBearer(auto_error=False)

# Configurable master administrative token
ADMIN_API_KEY = os.environ.get("CLIVERSE_ADMIN_API_KEY", "cliverse-admin-default-key")


# ── Authentication & Authorization Dependency ────────────────────────────────

def verify_admin_auth(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
):
    """
    Guards sensitive administrative endpoints (secrets, policy management, scope elevation).
    """
    token = x_api_key or (auth.credentials if auth else None)
    if not token or token != ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Valid administrative API key or Bearer token required for sensitive operations.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


# ── Request / Response Schemas ───────────────────────────────────────────────

class RegisterAgentRequest(BaseModel):
    cli_name: str
    scopes: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    admin_token: Optional[str] = None

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
    user_confirmed: bool = False

class EvaluateOperationResponse(BaseModel):
    allowed: bool
    decision: str
    risk_level: str
    reason: str
    requires_user_confirmation: bool = False
    confirmation_token: Optional[str] = None
    warnings: List[str]
    audit_event_id: Optional[str] = None

class ConfirmWarningRequest(BaseModel):
    confirmation_token: str

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
    """
    Registers an AI CLI session. Privilege scopes require admin authorization.
    """
    try:
        ident = gate.identity.register(
            cli_name=req.cli_name,
            scopes=req.scopes,
            metadata=req.metadata,
            admin_token=req.admin_token,
        )
        return RegisterAgentResponse(**ident.to_dict())
    except ScopeViolationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

@router.get("/identity/active")
def list_active_identities():
    """Returns all registered agent sessions."""
    return [i.to_dict() for i in gate.identity.list_active()]

@router.delete("/identity/{agent_id}", dependencies=[Depends(verify_admin_auth)])
def revoke_identity(agent_id: str):
    """Revokes an agent identity (Protected Route)."""
    success = gate.identity.revoke(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent ID not found")
    return {"status": "revoked", "agent_id": agent_id}


# ── Pipeline Evaluation Gate ─────────────────────────────────────────────────

@router.post("/evaluate", response_model=EvaluateOperationResponse)
def evaluate_operation(req: EvaluateOperationRequest):
    """
    Main Security Pipeline Gate.
    Requires user confirmation token if operation results in a WARN state.
    """
    result = gate.evaluate(
        agent_id=req.agent_id,
        operation=req.operation,
        command=req.command,
        path=req.path,
        context=req.context,
        user_confirmed=req.user_confirmed,
    )
    return EvaluateOperationResponse(
        allowed=result.allowed,
        decision=result.decision,
        risk_level=result.risk_level,
        reason=result.reason,
        requires_user_confirmation=result.requires_user_confirmation,
        confirmation_token=result.confirmation_token,
        warnings=result.warnings,
        audit_event_id=result.audit_event.event_id if result.audit_event else None,
    )

@router.post("/evaluate/confirm", response_model=EvaluateOperationResponse)
def confirm_warning(req: ConfirmWarningRequest):
    """Confirms and unblocks a previously warned operation."""
    try:
        result = gate.confirm_warning(req.confirmation_token)
        return EvaluateOperationResponse(
            allowed=result.allowed,
            decision=result.decision,
            risk_level=result.risk_level,
            reason=result.reason,
            requires_user_confirmation=result.requires_user_confirmation,
            confirmation_token=result.confirmation_token,
            warnings=result.warnings,
            audit_event_id=result.audit_event.event_id if result.audit_event else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ── Audit Endpoints (With Integrity Verification) ────────────────────────────

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

@router.get("/audit/verify-integrity")
def verify_audit_integrity():
    """Cryptographically verifies the SHA-256 chain integrity of the entire audit log."""
    valid, message = gate.audit.verify_chain_integrity()
    return {"valid": valid, "status": "VERIFIED" if valid else "TAMPERED", "message": message}

@router.get("/audit/security-alerts")
def get_security_alerts():
    """Returns all blocked / warned security events."""
    return [e.to_dict() for e in gate.audit.get_security_events()]


# ── Governance & Policies (Protected Routes) ─────────────────────────────────

@router.get("/governance/policies")
def list_policies(active_only: bool = False):
    policies = gate.policies.list_active_policies() if active_only else gate.policies.list_policies()
    return [vars(p) for p in policies]

@router.post("/governance/policies", dependencies=[Depends(verify_admin_auth)])
def create_policy(req: AddPolicyRequest):
    """Add a new custom governance policy rule (Protected Route)."""
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

@router.post("/governance/sync-sources")
def sync_regulatory_sources():
    """Triggers an active sync and reachability check for monitored regulatory sources."""
    return gate.regulatory.sync_regulatory_sources()

@router.get("/governance/regulatory-sources")
def list_regulatory_sources():
    return [vars(s) for s in gate.regulatory.list_sources()]

@router.get("/governance/status")
def governance_status():
    return gate.regulatory.status_report()


# ── Secrets Management (Protected Routes) ───────────────────────────────────

@router.post("/secrets", dependencies=[Depends(verify_admin_auth)])
def store_secret(req: StoreSecretRequest):
    """Store a secret safely (Protected Route)."""
    gate.secrets.store(key=req.key, value=req.value, scope=req.scope)
    return {"status": "stored", "key": req.key}

@router.get("/secrets", dependencies=[Depends(verify_admin_auth)])
def list_secret_keys():
    """List metadata for all configured secrets without exposing values (Protected Route)."""
    return [vars(s) for s in gate.secrets.list_keys()]


# ── App wrapper ──────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="CLIVERSE Trust & Governance API",
        description="Authenticated Security, Regulatory, and Audit infrastructure for AI CLIs",
        version="1.1.0",
    )
    app.include_router(router)
    return app
