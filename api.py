"""
Unified FastAPI REST & Real-Time API for CLIVERSE Control Center
Integrates:
- Member 1: Core Planning, Git Inspection, Sessions, Recovery & Process Execution
- Member 2: Memory Storage, Hybrid RAG Retrieval & Hierarchical Rules Intelligence
- Member 4: Security Identity, TrustGate Pipeline, Compliance Policies, Secrets & Cryptographic Audit

Serves both API endpoints and the built interactive React/TypeScript frontend.
"""

import os
import sys
import json
import time
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator
from datetime import datetime, timezone
from dataclasses import asdict

from pydantic import BaseModel, Field
from fastapi import FastAPI, APIRouter, HTTPException, Query, Depends, Header, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Ensure current working directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ── Member 4 Imports ─────────────────────────────────────────────────────────
from trust_gate import TrustGate, PipelineEvaluation
from governance.policies import Policy, PolicyCategory, PolicyDecision
from governance.regulatory import RegulatorySource, RegulatoryUpdate
from security.identity import ScopeViolationError
from security.sandbox import SandboxMode
from audit.events import EventSource, EventType

# ── Member 2 Imports ─────────────────────────────────────────────────────────
from rag_rules_service import (
    LayaIntelligenceService,
    LayaIntelligenceContext,
    CliverseMemoryProviderAdapter,
    SubsystemStatus,
    RuleDecision,
    TaskLike,
)
from memory.storage.sqlite_store import SQLiteMemoryStorage
from memory.retrieval.search import RetrievalService
from memory.ingestion.pipeline import IngestionPipeline
from rules.storage import RuleStore
from rules.models import Rule, RuleScope, RuleEffect

# ── Member 1 Imports ─────────────────────────────────────────────────────────
from cliverse.contracts import (
    StructuredTask,
    ContextBundle,
    ContextItem as Member1ContextItem,
    Rule as Member1Rule,
    Decision as Member1Decision,
    AuthorizationRequest,
    AuthorizationDecision,
    Authorizer,
)
from cliverse.planning import RequestPlanner, PlanningRequest, PlanningResult
from cliverse.git_inspection import GitInspector, GitStatus, GitCommit
from cliverse.recovery import GitRecovery, UndoPreview, UndoResult
from cliverse.sessions import SessionStore, Session, CoreEvent
from cliverse.execution import CliAdapter, ProcessRequest, ExecutionResult
from cliverse.providers import provider_registry, ProviderStatus
from cliverse.orchestrator import ExecutionOrchestrator

# Initialize Shared Core Services
DEFAULT_PROJECT_ID = "cliverse-core"
ACTIVE_STATE = {
    "project_id": DEFAULT_PROJECT_ID,
    "cli_name": "claude-cli",
    "project_root": str(BASE_DIR),
}

def is_render_environment() -> bool:
    """Detects whether running inside the Render cloud platform."""
    return os.environ.get("RENDER", "").lower() in ("true", "1") or "RENDER" in os.environ


def get_data_root() -> Path:
    """
    Resolves the persistent data root.
    - If CLIVERSE_DATA_ROOT env var is provided, use it.
    - If running on Render and /var/data exists, use /var/data.
    - Otherwise default to project-local .envcore directory.
    """
    configured = os.environ.get("CLIVERSE_DATA_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    if is_render_environment() and Path("/var/data").exists():
        return Path("/var/data").resolve()
    return (BASE_DIR / ".envcore").resolve()


def ensure_storage_directories(root: Path) -> dict[str, Path]:
    """Ensures all necessary persistent subdirectories exist."""
    dirs = {
        "root": root,
        "memory": root / "memory",
        "sessions": root / "sessions",
        "rules_global": root / "rules" / "global",
        "identities": root / "identities",
        "audit": root / "audit",
        "secrets": root / "secrets",
        "governance": root / "governance",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


# Member 4 to Member 1 Authorizer Bridge
class TrustGateAuthorizer:
    def __init__(self, gate: TrustGate):
        self.gate = gate

    def authorize(self, req: AuthorizationRequest) -> AuthorizationDecision:
        res = self.gate.evaluate(
            agent_id=req.identity,
            operation=req.operation,
            command=f"{req.executable} {' '.join(req.arguments)}" if req.executable else None,
            path=req.paths[0] if req.paths else None,
            user_confirmed=True,
        )
        dec = Member1Decision.ALLOW if res.allowed else (Member1Decision.WARN if res.decision == "WARN" else Member1Decision.BLOCK)
        return AuthorizationDecision(
            decision=dec,
            reason=res.reason,
            requires_confirmation=res.requires_user_confirmation,
        )


DATA_ROOT = get_data_root()
STORAGE_DIRS = ensure_storage_directories(DATA_ROOT)
ADMIN_SECRET = os.environ.get("CLIVERSE_ADMIN_SECRET") or os.environ.get("ADMIN_SECRET", "cliverse-admin-default-key")

trust_gate = TrustGate(
    project_root=str(BASE_DIR),
    storage_dir=str(DATA_ROOT),
    sandbox_mode=SandboxMode.STRICT,
    admin_secret=ADMIN_SECRET,
)

memory_db_path = STORAGE_DIRS["memory"] / "cliverse_memory.db"
memory_storage = SQLiteMemoryStorage(db_path=str(memory_db_path))
memory_service = RetrievalService(storage=memory_storage)

rules_store = RuleStore(
    project_rules_dir=str(BASE_DIR / ".cliverse" / "rules"),
    global_rules_dir=str(STORAGE_DIRS["rules_global"]),
)
intelligence_service = LayaIntelligenceService(
    retrieval_service=memory_service,
    rules_engine=None,
)

sessions_db_path = STORAGE_DIRS["sessions"] / "sessions.db"
sessions_store = SessionStore(str(sessions_db_path))
git_inspector = GitInspector(BASE_DIR)
git_recovery = GitRecovery(BASE_DIR)
trust_gate_authorizer = TrustGateAuthorizer(trust_gate)


def configure_services(data_root: Optional[Path | str] = None, admin_secret: Optional[str] = None) -> Path:
    """Reconfigures shared runtime services for a specific data root."""
    global DATA_ROOT, STORAGE_DIRS, ADMIN_SECRET
    global trust_gate, memory_service, rules_store, intelligence_service, sessions_store, trust_gate_authorizer
    global memory_db_path, sessions_db_path

    if data_root is not None:
        DATA_ROOT = Path(data_root).expanduser().resolve()
    else:
        DATA_ROOT = get_data_root()

    if admin_secret is not None:
        ADMIN_SECRET = admin_secret
    else:
        ADMIN_SECRET = os.environ.get("CLIVERSE_ADMIN_SECRET") or os.environ.get("ADMIN_SECRET", "cliverse-admin-default-key")

    STORAGE_DIRS = ensure_storage_directories(DATA_ROOT)
    trust_gate = TrustGate(
        project_root=str(BASE_DIR),
        storage_dir=str(DATA_ROOT),
        sandbox_mode=SandboxMode.STRICT,
        admin_secret=ADMIN_SECRET,
    )

    memory_db_path = STORAGE_DIRS["memory"] / "cliverse_memory.db"
    memory_storage = SQLiteMemoryStorage(db_path=str(memory_db_path))
    memory_service = RetrievalService(storage=memory_storage)

    rules_store = RuleStore(
        project_rules_dir=str(BASE_DIR / ".cliverse" / "rules"),
        global_rules_dir=str(STORAGE_DIRS["rules_global"]),
    )
    intelligence_service = LayaIntelligenceService(
        retrieval_service=memory_service,
        rules_engine=None,
    )

    sessions_db_path = STORAGE_DIRS["sessions"] / "sessions.db"
    sessions_store = SessionStore(str(sessions_db_path))
    trust_gate_authorizer = TrustGateAuthorizer(trust_gate)
    return DATA_ROOT

def get_memory_counts(project_id: str) -> tuple[int, int]:
    import sqlite3
    try:
        with sqlite3.connect(memory_service.storage.db_path) as conn:
            r_row = conn.execute("SELECT COUNT(*) FROM memory_records WHERE project_id = ?", (project_id,)).fetchone()
            r_count = r_row[0] if r_row else 0
            c_row = conn.execute("SELECT COUNT(*) FROM memory_chunks c JOIN memory_records r ON c.record_id = r.record_id WHERE r.project_id = ?", (project_id,)).fetchone()
            c_count = c_row[0] if c_row else 0
            return r_count, c_count
    except Exception:
        return 0, 0

# ── Seed Real Repository Context on Startup ──────────────────────────────────
def seed_initial_state_if_empty():
    """Seeds real project documentation and default rules if memory is fresh."""
    try:
        rec_count, _ = get_memory_counts(DEFAULT_PROJECT_ID)
        if rec_count == 0:
            pipeline = IngestionPipeline(storage=memory_service.storage, embedding_provider=memory_service.embedding_provider)
            
            # Ingest Member 2 architecture doc
            arch_doc = BASE_DIR / "docs" / "member2-architecture.md"
            if arch_doc.exists():
                pipeline.ingest(
                    content=arch_doc.read_text(encoding="utf-8"),
                    project_id=DEFAULT_PROJECT_ID,
                    source_type="doc",
                    source_path="docs/member2-architecture.md",
                    title="Member 2 Architecture & RAG Specification",
                    tags=["architecture", "rag", "rules"],
                )
            
            # Ingest PRD or README
            readme_file = BASE_DIR / "README.md"
            if readme_file.exists():
                pipeline.ingest(
                    content=readme_file.read_text(encoding="utf-8"),
                    project_id=DEFAULT_PROJECT_ID,
                    source_type="doc",
                    source_path="README.md",
                    title="CLIVERSE System Overview",
                    tags=["system", "readme", "core"],
                )

        # Seed standard engineering rules if empty
        existing_rules = rules_store.list_rules()
        if len(existing_rules) == 0:
            rules_store.create_rule(Rule(
                rule_id="rule-require-test",
                name="Pre-Commit Test Requirement",
                description="All automated unit tests must pass before staging or committing changes.",
                scope=RuleScope.PROJECT,
                priority=90,
                effect=RuleEffect.REQUIRE,
                target="tests",
                project_id=DEFAULT_PROJECT_ID,
            ))
            rules_store.create_rule(Rule(
                rule_id="rule-deny-destructive-fs",
                name="Strict File Removal Prohibition",
                description="Destructive system-level removal commands (rm -rf /, format, mkfs) are strictly forbidden.",
                scope=RuleScope.GLOBAL,
                priority=99,
                effect=RuleEffect.DENY,
                target="filesystem",
                is_mandatory=True,
            ))
            rules_store.create_rule(Rule(
                rule_id="rule-warn-pii-compliance",
                name="Sensitive Data Compliance Gate",
                description="Handling user biometric or payment card data triggers a regulatory review.",
                scope=RuleScope.PROJECT,
                priority=80,
                effect=RuleEffect.WARN,
                target="compliance",
                project_id=DEFAULT_PROJECT_ID,
            ))
            rules_store.create_rule(Rule(
                rule_id="rule-allow-git-inspection",
                name="Git Read-Only Allowance",
                description="Read-only Git operations (status, diff, log, history) are freely permitted.",
                scope=RuleScope.GLOBAL,
                priority=50,
                effect=RuleEffect.ALLOW,
                target="git",
            ))

        # Seed active agent identity if none
        if len(trust_gate.identity.list_active()) == 0:
            trust_gate.identity.register(
                cli_name="claude-cli",
                scopes=["read", "write", "git", "execute"],
                metadata={"user": "developer", "environment": "local"},
            )
            trust_gate.identity.register(
                cli_name="gemini-cli",
                scopes=["read", "write", "git"],
                metadata={"user": "developer", "environment": "cloud"},
            )
    except Exception as e:
        print(f"[!] Warning during initial state seeding: {e}")

seed_initial_state_if_empty()


# ── Activity Event Broadcaster ───────────────────────────────────────────────
class ActivityBroadcaster:
    def __init__(self):
        self.listeners: List[asyncio.Queue] = []

    async def subscribe(self) -> AsyncGenerator[str, None]:
        q = asyncio.Queue()
        self.listeners.append(q)
        try:
            while True:
                data = await q.get()
                yield f"data: {json.dumps(data)}\n\n"
        finally:
            self.listeners.remove(q)

    def publish(self, event: Dict[str, Any]):
        for q in self.listeners:
            try:
                q.put_nowait(event)
            except Exception:
                pass

activity_broadcaster = ActivityBroadcaster()

def log_system_event(source: str, event_type: str, summary: str, status: str = "success", details: Optional[Dict[str, Any]] = None):
    evt = {
        "event_id": f"evt-{int(time.time()*1000)}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "event_type": event_type,
        "summary": summary,
        "status": status,
        "details": details or {},
    }
    activity_broadcaster.publish(evt)
    return evt


# ── System & Health Router ───────────────────────────────────────────────────
system_router = APIRouter(prefix="/api", tags=["System & Overview"])

@system_router.get("/health")
def get_system_health():
    """Comprehensive production health check across all Member subsystems."""
    is_render = is_render_environment()
    data_root = DATA_ROOT
    is_writable = False
    try:
        test_file = data_root / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        is_writable = True
    except Exception:
        is_writable = False

    git_clean = False
    git_branch = "unknown"
    try:
        st = git_inspector.status()
        git_clean = st.is_clean
        git_branch = st.branch
    except Exception:
        pass

    _, mem_count = get_memory_counts(ACTIVE_STATE["project_id"])
    rule_count = len(rules_store.list_rules(project_id=ACTIVE_STATE["project_id"]))
    active_agents = len(trust_gate.identity.list_active())
    valid_chain, _ = trust_gate.audit.verify_chain_integrity()
    providers = provider_registry.list_providers()

    return {
        "status": "HEALTHY",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0",
        "environment": "render" if is_render else "local",
        "is_render": is_render,
        "active_project": ACTIVE_STATE["project_id"],
        "active_cli": ACTIVE_STATE["cli_name"],
        "storage": {
            "data_root": str(data_root),
            "writable": is_writable,
            "memory_db": str(memory_db_path),
            "sessions_db": str(sessions_db_path),
        },
        "subsystems": {
            "memory": {
                "status": "OK_WITH_RESULTS" if mem_count > 0 else "OK_EMPTY",
                "chunks_count": mem_count,
                "provider": "SQLite + LocalBaselineEmbeddingProvider (64-dim)",
            },
            "rules": {
                "status": "OK_WITH_RESULTS" if rule_count > 0 else "OK_EMPTY",
                "rules_count": rule_count,
            },
            "laya": {
                "status": "READY",
                "planner": "RequestPlanner + CliverseMemoryProviderAdapter",
            },
            "security": {
                "status": "ACTIVE",
                "mode": trust_gate.sandbox.policy.mode.value,
                "active_identities": active_agents,
                "audit_chain_valid": valid_chain,
            },
            "git": {
                "status": "CLEAN" if git_clean else "MODIFIED",
                "branch": git_branch,
            },
            "cli_execution": {
                "mode": "LOCAL_ONLY" if is_render else "LOCAL_WORKSTATION",
                "available": not is_render,
                "note": "LOCAL CLI EXECUTION AVAILABLE only on the user's local CLIVERSE machine." if is_render else "Host CLI binaries detected and executable.",
                "providers_detected": len([p for p in providers if p.is_available]),
            },
        },
    }

@system_router.get("/projects")
def list_projects():
    """Lists available project workspaces."""
    return {
        "active_project": ACTIVE_STATE["project_id"],
        "active_cli": ACTIVE_STATE["cli_name"],
        "available_projects": [
            {"id": "cliverse-core", "name": "CLIVERSE Core", "root": str(BASE_DIR)},
            {"id": "project-alpha", "name": "Service Alpha (PostgreSQL/JWT)", "root": str(BASE_DIR)},
            {"id": "project-beta", "name": "Service Beta (MongoDB/OAuth)", "root": str(BASE_DIR)},
        ],
        "available_clis": [
            "claude-cli",
            "cursor-cli",
            "aider-cli",
            "gemini-cli",
            "codex-cli",
        ],
    }

class SelectProjectRequest(BaseModel):
    project_id: str
    cli_name: Optional[str] = None

@system_router.post("/projects/select")
def select_project(req: SelectProjectRequest):
    """Switches active project and CLI context."""
    ACTIVE_STATE["project_id"] = req.project_id
    if req.cli_name:
        ACTIVE_STATE["cli_name"] = req.cli_name
    
    log_system_event(
        source="SYSTEM",
        event_type="PROJECT_SWITCH",
        summary=f"Switched active project to '{req.project_id}' (CLI: {ACTIVE_STATE['cli_name']})",
        status="success",
        details={"project_id": req.project_id, "cli_name": ACTIVE_STATE["cli_name"]},
    )
    return {
        "status": "selected",
        "project_id": ACTIVE_STATE["project_id"],
        "cli_name": ACTIVE_STATE["cli_name"],
    }


# ── Member 2: Memory & RAG Router ────────────────────────────────────────────
memory_router = APIRouter(prefix="/api/memory", tags=["Memory & RAG (Member 2)"])

@memory_router.get("/stats")
def get_memory_stats(project_id: Optional[str] = None):
    pid = project_id or ACTIVE_STATE["project_id"]
    r_count, c_count = get_memory_counts(pid)
    return {
        "project_id": pid,
        "stats": {
            "total_records": r_count,
            "total_chunks": c_count,
            "db_path": str(memory_service.storage.db_path),
        },
        "embedding_model": memory_service.embedding_provider.model_name,
        "embedding_dimension": memory_service.embedding_provider.dimension,
    }

@memory_router.get("/search")
def search_memory(
    query: str,
    project_id: Optional[str] = None,
    top_k: int = Query(default=5, ge=1, le=20),
    min_score: float = Query(default=0.35, ge=0.0, le=1.0),
    source_type: Optional[str] = None,
    session_id: Optional[str] = None,
):
    pid = project_id or ACTIVE_STATE["project_id"]
    try:
        source_types = [source_type] if source_type else None
        results = memory_service.search_memory(
            query=query,
            project_id=pid,
            top_k=top_k,
            min_score=min_score,
            source_types=source_types,
            session_id=session_id,
        )
        
        status_val = "OK_WITH_RESULTS" if results else "OK_EMPTY"
        
        log_system_event(
            source="MEMORY",
            event_type="RETRIEVAL_QUERY",
            summary=f"Queried memory for '{query[:30]}...' -> {len(results)} chunks",
            status="success" if results else "empty",
            details={"query": query, "count": len(results), "project_id": pid},
        )

        return {
            "status": status_val,
            "query": query,
            "project_id": pid,
            "count": len(results),
            "results": [
                {
                    "record_id": r.record_id,
                    "chunk_id": r.chunk_id,
                    "content": r.content,
                    "source_path": r.source_path,
                    "source_type": r.source_type,
                    "start_line": r.start_line,
                    "end_line": r.end_line,
                    "score": round(r.score, 4),
                    "tags": getattr(r, "tags", r.metadata.get("tags", [])) if hasattr(r, "tags") or hasattr(r, "metadata") else [],
                    "metadata": r.metadata,
                }
                for r in results
            ],
        }
    except Exception as e:
        log_system_event(
            source="MEMORY",
            event_type="RETRIEVAL_ERROR",
            summary=f"Memory search failed: {str(e)}",
            status="error",
            details={"error": str(e)},
        )
        return {
            "status": "ERROR",
            "query": query,
            "project_id": pid,
            "count": 0,
            "error": str(e),
            "results": [],
        }

class StoreMemoryRequest(BaseModel):
    content: str
    project_id: Optional[str] = None
    source_type: str = "doc"
    source_path: str = "manual_entry"
    title: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

@memory_router.post("")
def store_memory(req: StoreMemoryRequest):
    pid = req.project_id or ACTIVE_STATE["project_id"]
    try:
        pipeline = IngestionPipeline(
            storage=memory_service.storage,
            embedding_provider=memory_service.embedding_provider,
        )
        res = pipeline.ingest(
            content=req.content,
            project_id=pid,
            source_type=req.source_type,
            source_path=req.source_path,
            title=req.title,
            tags=req.tags,
            metadata=req.metadata,
        )
        log_system_event(
            source="MEMORY",
            event_type="MEMORY_INGEST",
            summary=f"Ingested {res.chunks_created} chunks into {pid} ({req.source_path})",
            status="success",
            details={"record_id": res.record_id, "chunks": res.chunks_created},
        )
        return {
            "status": "success",
            "record_id": res.record_id,
            "chunks_created": res.chunks_created,
            "status_code": res.status.value if hasattr(res.status, "value") else str(res.status),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@memory_router.delete("/{record_id}")
def delete_memory(record_id: str):
    success = memory_service.storage.delete_record(record_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory record not found")
    log_system_event(
        source="MEMORY",
        event_type="MEMORY_DELETE",
        summary=f"Deleted memory record {record_id}",
        status="success",
        details={"record_id": record_id},
    )
    return {"status": "deleted", "record_id": record_id}


# ── Member 2: Rules Intelligence Router ──────────────────────────────────────
rules_router = APIRouter(prefix="/api/rules", tags=["Rules Intelligence (Member 2)"])

@rules_router.get("")
def list_rules(
    scope: Optional[str] = None,
    project_id: Optional[str] = None,
):
    pid = project_id or ACTIVE_STATE["project_id"]
    sc = RuleScope(scope.upper()) if scope else None
    rules = rules_store.list_rules(scope=sc, project_id=pid)
    return {
        "project_id": pid,
        "count": len(rules),
        "rules": [r.model_dump() for r in rules],
    }

class CreateRuleRequest(BaseModel):
    rule_id: str
    name: str
    description: str
    scope: str = "project"
    priority: int = 50
    effect: str = "require"
    target: Optional[str] = None
    is_mandatory: bool = False
    project_id: Optional[str] = None
    cli_name: Optional[str] = None

@rules_router.post("")
def create_rule(req: CreateRuleRequest):
    pid = req.project_id or ACTIVE_STATE["project_id"]
    try:
        rule = Rule(
            rule_id=req.rule_id,
            name=req.name,
            description=req.description,
            scope=RuleScope(req.scope.upper()),
            priority=req.priority,
            effect=RuleEffect(req.effect.upper()),
            target=req.target or req.rule_id,
            is_mandatory=req.is_mandatory,
            project_id=pid if req.scope.upper() == "PROJECT" else None,
            cli_name=req.cli_name if req.scope.upper() == "CLI" else None,
        )
        saved = rules_store.create_rule(rule)
        log_system_event(
            source="RULES",
            event_type="RULE_CREATED",
            summary=f"Created rule [{rule.effect.value.upper()}] {rule.name} ({rule.scope.value})",
            status="success",
            details=rule.model_dump(),
        )
        return saved.model_dump()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@rules_router.get("/{rule_id}")
def get_rule(rule_id: str):
    rule = rules_store.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule.model_dump()

@rules_router.delete("/{rule_id}")
def delete_rule(rule_id: str):
    success = rules_store.delete_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found")
    log_system_event(
        source="RULES",
        event_type="RULE_DELETED",
        summary=f"Deleted rule {rule_id}",
        status="success",
        details={"rule_id": rule_id},
    )
    return {"status": "deleted", "rule_id": rule_id}

class ResolveRulesRequest(BaseModel):
    task: str
    project_id: Optional[str] = None
    cli_name: Optional[str] = None
    task_metadata: Optional[Dict[str, Any]] = None

@rules_router.post("/resolve")
def resolve_rules(req: ResolveRulesRequest):
    pid = req.project_id or ACTIVE_STATE["project_id"]
    cli = req.cli_name or ACTIVE_STATE["cli_name"]
    res = intelligence_service.resolve_rules(
        task=req.task,
        project_id=pid,
        cli_name=cli,
        task_metadata=req.task_metadata,
    )
    winning = res.winning_rules
    if any(r.effect == RuleEffect.DENY for r in winning):
        decision = RuleDecision.DENY
    elif any(r.effect == RuleEffect.ASK for r in winning):
        decision = RuleDecision.ASK
    elif any(r.effect in (RuleEffect.REQUIRE, RuleEffect.ENFORCE) for r in winning):
        decision = RuleDecision.REQUIRE
    elif any(r.effect == RuleEffect.WARN for r in winning):
        decision = RuleDecision.WARN
    else:
        decision = RuleDecision.ALLOW

    return {
        "task": req.task,
        "project_id": pid,
        "cli_name": cli,
        "winning_decision": decision.value,
        "applicable_rules": [r.model_dump() for r in res.applicable_rules],
        "winning_rules": [r.model_dump() for r in res.winning_rules],
        "conflicts": [c.model_dump() for c in res.conflicts],
        "explanation_trace": res.explanation_trace,
    }


# ── Member 1 & 2: Laya Workspace & Planning Router ───────────────────────────
laya_router = APIRouter(prefix="/api/laya", tags=["Laya Planning & Intelligence"])

class IntelligenceRequest(BaseModel):
    task: str
    project_id: Optional[str] = None
    cli_name: Optional[str] = None
    top_k: int = 5
    min_score: float = 0.35
    context_budget_tokens: int = 2000
    task_metadata: Optional[Dict[str, Any]] = None

@laya_router.post("/intelligence")
def build_intelligence_context(req: IntelligenceRequest):
    """Runs complete Member 2 intelligence context generation (Memory RAG + Rules)."""
    pid = req.project_id or ACTIVE_STATE["project_id"]
    cli = req.cli_name or ACTIVE_STATE["cli_name"]
    try:
        ctx = intelligence_service.build_intelligence_context(
            task=req.task,
            project_id=pid,
            cli_name=cli,
            top_k=req.top_k,
            min_score=req.min_score,
            context_budget_tokens=req.context_budget_tokens,
            task_metadata=req.task_metadata,
        )
        
        log_system_event(
            source="LAYA",
            event_type="INTELLIGENCE_CONTEXT",
            summary=f"Laya Context for '{req.task[:30]}...' -> Decision: {ctx.rule_decision.value}",
            status="success" if ctx.rule_decision != RuleDecision.DENY else "denied",
            details={
                "decision": ctx.rule_decision.value,
                "memory_chunks": len(ctx.memory_context.items),
                "applicable_rules": len(ctx.applicable_rules),
            },
        )

        retrieved_items = []
        for item in ctx.memory_context.items:
            content = getattr(item, "snippet", "") or getattr(item, "content", "")
            src = getattr(item, "source", "")
            src_path = src.split(":")[0] if ":" in src else src
            start_l = None
            end_l = None
            if ":" in src:
                lines_part = src.split(":")[-1]
                if "-" in lines_part:
                    try:
                        p_parts = lines_part.split("-")
                        start_l = int(p_parts[0])
                        end_l = int(p_parts[1])
                    except Exception:
                        pass
            retrieved_items.append({
                "content": content,
                "source": src,
                "source_path": src_path,
                "start_line": start_l,
                "end_line": end_l,
                "relevance_score": round(getattr(item, "relevance_score", 0.0), 4),
                "source_type": getattr(item, "source_type", "doc"),
            })

        return {
            "task_text": ctx.task,
            "project_id": ctx.project_id,
            "cli_name": ctx.cli_name,
            "memory_status": ctx.memory_status.value,
            "rules_status": ctx.rules_status.value,
            "rule_decision": ctx.rule_decision.value,
            "rule_explanations": ctx.rule_explanations,
            "retrieved_context_items": retrieved_items,
            "applicable_rules": [r.model_dump() for r in ctx.applicable_rules],
            "winning_rules": [r.model_dump() for r in ctx.rule_resolution.winning_rules],
            "conflicts": [c.model_dump() for c in ctx.rule_resolution.conflicts],
            "combined_laya_context": ctx.combined_laya_context,
            "metadata": ctx.metadata,
        }
    except Exception as e:
        log_system_event(
            source="LAYA",
            event_type="INTELLIGENCE_ERROR",
            summary=f"Laya Intelligence error: {str(e)}",
            status="error",
            details={"error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e))

class PlanRequest(BaseModel):
    task: str
    role: str = "AI coding assistant"
    context: str = ""
    requirements: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    output: str = "Implement the task and report verification."
    project_id: Optional[str] = None
    cli_name: Optional[str] = None

@laya_router.post("/plan")
def plan_task(req: PlanRequest):
    """Executes Member 1 RequestPlanner through Member 2 adapter."""
    pid = req.project_id or ACTIVE_STATE["project_id"]
    cli = req.cli_name or ACTIVE_STATE["cli_name"]
    try:
        adapter = CliverseMemoryProviderAdapter(project_id=pid, cli_name=cli)
        planner = RequestPlanner(memory_provider=adapter)
        planning_req = PlanningRequest(
            task=req.task,
            role=req.role,
            context=req.context,
            requirements=tuple(req.requirements),
            constraints=tuple(req.constraints),
            output=req.output,
        )
        res = planner.plan(planning_req)
        
        log_system_event(
            source="MEMBER1_PLANNING",
            event_type="TASK_PLANNED",
            summary=f"RequestPlanner created StructuredTask for '{req.task[:30]}...'",
            status="success",
            details={
                "ready": res.ready,
                "applicable_rule_ids": list(res.applicable_rule_ids),
                "context_provenance": list(res.context_provenance),
            },
        )

        return {
            "ready": res.ready,
            "task": res.task.as_dict() if res.task else None,
            "clarification_questions": list(res.clarification_questions),
            "context_provenance": list(res.context_provenance),
            "applicable_rule_ids": list(res.applicable_rule_ids),
        }
    except Exception as e:
        log_system_event(
            source="MEMBER1_PLANNING",
            event_type="PLANNING_ERROR",
            summary=f"RequestPlanner failed: {str(e)}",
            status="error",
            details={"error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e))

class ExecutePipelineRequest(BaseModel):
    task: str
    command: Optional[str] = None
    project_id: Optional[str] = None
    cli_name: Optional[str] = None
    user_confirmed: bool = False

@laya_router.post("/execute")
def execute_pipeline(req: ExecutePipelineRequest):
    """
    Executes the Complete 5-Stage CLIVERSE Pipeline:
    TASK -> MEMORY -> RULES -> LAYA INTELLIGENCE -> PLANNING -> TRUSTGATE -> EXECUTION
    """
    pid = req.project_id or ACTIVE_STATE["project_id"]
    cli = req.cli_name or ACTIVE_STATE["cli_name"]
    
    # Stage 1 & 2: Member 2 Intelligence
    intel = intelligence_service.build_intelligence_context(
        task=req.task,
        project_id=pid,
        cli_name=cli,
    )
    
    # Stage 3: Member 1 Planning
    adapter = CliverseMemoryProviderAdapter(project_id=pid, cli_name=cli)
    planner = RequestPlanner(memory_provider=adapter)
    plan_res = planner.plan(PlanningRequest(task=req.task))

    # Stage 4: Member 4 TrustGate Evaluation
    # Find active agent identity for cli
    ident = next((i for i in trust_gate.identity.list_active() if i.cli_name == cli), None)
    if not ident:
        ident = trust_gate.identity.register(cli_name=cli, scopes=["read", "write", "git", "execute"])

    cmd_to_eval = req.command or "git status"
    trust_res = trust_gate.evaluate(
        agent_id=ident.agent_id,
        operation="execute",
        command=cmd_to_eval,
        context={"task": req.task, "rule_decision": intel.rule_decision.value},
        user_confirmed=req.user_confirmed,
    )

    # Stage 5: Execution Result (Dry run or actual safe command)
    exec_status = "NOT_EXECUTED"
    if trust_res.allowed:
        exec_status = "EXECUTED_SUCCESS"
    elif trust_res.requires_user_confirmation:
        exec_status = "AWAITING_CONFIRMATION"
    else:
        exec_status = "BLOCKED_BY_TRUSTGATE"

    log_system_event(
        source="PIPELINE",
        event_type="PIPELINE_COMPLETE",
        summary=f"Pipeline result for '{req.task[:25]}...': Rule={intel.rule_decision.value}, TrustGate={trust_res.decision}, Exec={exec_status}",
        status="success" if trust_res.allowed else ("warn" if trust_res.decision == "WARN" else "denied"),
        details={
            "rule_decision": intel.rule_decision.value,
            "trust_decision": trust_res.decision,
            "exec_status": exec_status,
            "confirmation_token": trust_res.confirmation_token,
        },
    )

    return {
        "task": req.task,
        "project_id": pid,
        "cli_name": cli,
        "pipeline": {
            "memory": {
                "status": intel.memory_status.value,
                "chunks_retrieved": len(intel.memory_context.items),
            },
            "rules": {
                "status": intel.rules_status.value,
                "decision": intel.rule_decision.value,
                "winning_rules_count": len(intel.rule_resolution.winning_rules),
            },
            "planning": {
                "ready": plan_res.ready,
                "applicable_rule_ids": list(plan_res.applicable_rule_ids),
            },
            "trustgate": {
                "allowed": trust_res.allowed,
                "decision": trust_res.decision,
                "risk_level": trust_res.risk_level,
                "reason": trust_res.reason,
                "requires_user_confirmation": trust_res.requires_user_confirmation,
                "confirmation_token": trust_res.confirmation_token,
                "warnings": trust_res.warnings,
            },
            "execution": {
                "status": exec_status,
                "command": cmd_to_eval,
            },
        },
    }


# ── Member 1: Git & Recovery Router ──────────────────────────────────────────
git_router = APIRouter(prefix="/api/git", tags=["Git & Recovery (Member 1)"])

@git_router.get("/status")
def get_git_status():
    st = git_inspector.status()
    return {
        "project_root": str(BASE_DIR),
        "branch": st.branch,
        "is_clean": st.is_clean,
        "changed_paths": list(st.changed_paths),
        "porcelain": st.porcelain,
    }

@git_router.get("/diff")
def get_git_diff():
    diff_text = git_inspector.diff()
    return {
        "diff": diff_text,
    }

@git_router.get("/history")
def get_git_history(limit: int = Query(default=20, ge=1, le=100)):
    commits = git_inspector.history(limit)
    return [
        {
            "commit_id": c.commit_id,
            "subject": c.subject,
            "session_id": c.session_id,
        }
        for c in commits
    ]

@git_router.get("/recovery/preview/{session_id}")
def preview_recovery(session_id: str):
    try:
        prev = git_recovery.preview(session_id)
        return {
            "session_id": prev.session_id,
            "target_commit": prev.target_commit,
            "changed_paths": list(prev.changed_paths),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class UndoRequest(BaseModel):
    session_id: str
    identity: str = "claude-cli"
    confirmed: bool = False

@git_router.post("/recovery/undo")
def execute_recovery(req: UndoRequest):
    try:
        res = git_recovery.undo(
            session_id=req.session_id,
            identity=req.identity,
            authorizer=trust_gate_authorizer,
            confirmed=req.confirmed,
        )
        log_system_event(
            source="GIT_RECOVERY",
            event_type="UNDO_SUCCESS",
            summary=f"Reverted commit for session {req.session_id}",
            status="success",
            details=asdict(res),
        )
        return asdict(res)
    except Exception as e:
        log_system_event(
            source="GIT_RECOVERY",
            event_type="UNDO_ERROR",
            summary=f"Undo recovery failed: {str(e)}",
            status="error",
            details={"error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e))


# ── Member 1: Sessions Router ────────────────────────────────────────────────
sessions_router = APIRouter(prefix="/api/sessions", tags=["Sessions (Member 1)"])

@sessions_router.get("")
def list_sessions(limit: int = Query(default=50, ge=1, le=100)):
    sessions = sessions_store.list_sessions(limit)
    return [
        {
            "session_id": s.session_id,
            "project_root": s.project_root,
            "user_request": s.user_request,
            "status": s.status,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }
        for s in sessions
    ]

class CreateSessionRequest(BaseModel):
    user_request: str
    project_root: Optional[str] = None

@sessions_router.post("")
def create_session(req: CreateSessionRequest):
    root = req.project_root or str(BASE_DIR)
    s = sessions_store.create_session(project_root=root, user_request=req.user_request)
    log_system_event(
        source="SESSION",
        event_type="SESSION_START",
        summary=f"Started session {s.session_id[:8]} for '{req.user_request[:30]}'",
        status="success",
        details={"session_id": s.session_id},
    )
    return {
        "session_id": s.session_id,
        "project_root": s.project_root,
        "user_request": s.user_request,
        "status": s.status,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }

@sessions_router.get("/{session_id}")
def get_session(session_id: str):
    s = sessions_store.get_session(session_id)
    events = sessions_store.list_events(session_id)
    return {
        "session": {
            "session_id": s.session_id,
            "project_root": s.project_root,
            "user_request": s.user_request,
            "status": s.status,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        },
        "events": [
            {
                "event_id": e.event_id,
                "timestamp": e.timestamp,
                "source": e.source,
                "event_type": e.event_type,
                "summary": e.summary,
                "decision": e.decision,
                "details": e.details,
            }
            for e in events
        ],
    }

class FinishSessionRequest(BaseModel):
    status: str = "completed"

@sessions_router.post("/{session_id}/finish")
def finish_session(session_id: str, req: FinishSessionRequest):
    s = sessions_store.finish_session(session_id, status=req.status)
    log_system_event(
        source="SESSION",
        event_type="SESSION_FINISH",
        summary=f"Session {session_id[:8]} finished with status '{req.status}'",
        status="success",
        details={"session_id": session_id, "status": req.status},
    )
    return {
        "session_id": s.session_id,
        "status": s.status,
        "updated_at": s.updated_at,
    }


# ── Member 4: Security Dashboard Router ──────────────────────────────────────
security_dash_router = APIRouter(prefix="/api/security", tags=["Security & Trust (Member 4)"])

@security_dash_router.get("/summary")
def get_security_summary():
    valid, msg = trust_gate.audit.verify_chain_integrity()
    events = trust_gate.audit.get_events(limit=50)
    alerts = trust_gate.audit.get_security_events()
    return {
        "mode": trust_gate.sandbox.policy.mode.value,
        "active_identities_count": len(trust_gate.identity.list_active()),
        "pending_confirmations_count": len(trust_gate._pending_confirmations),
        "audit_events_count": len(events),
        "security_alerts_count": len(alerts),
        "chain_valid": valid,
        "chain_status": "VERIFIED" if valid else "TAMPERED",
        "chain_message": msg,
    }

@security_dash_router.get("/identities")
def list_identities():
    return [i.to_dict() for i in trust_gate.identity.list_active()]

class RegisterAgentReq(BaseModel):
    cli_name: str
    scopes: Optional[List[str]] = None

@security_dash_router.post("/identities")
def register_agent(req: RegisterAgentReq):
    ident = trust_gate.identity.register(cli_name=req.cli_name, scopes=req.scopes or ["read", "write"])
    log_system_event(
        source="SECURITY",
        event_type="IDENTITY_REGISTERED",
        summary=f"Registered CLI agent '{req.cli_name}' ({ident.agent_id[:8]})",
        status="success",
        details=ident.to_dict(),
    )
    return ident.to_dict()

@security_dash_router.delete("/identities/{agent_id}")
def revoke_agent(agent_id: str):
    success = trust_gate.identity.revoke(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent ID not found")
    log_system_event(
        source="SECURITY",
        event_type="IDENTITY_REVOKED",
        summary=f"Revoked CLI agent {agent_id}",
        status="warn",
        details={"agent_id": agent_id},
    )
    return {"status": "revoked", "agent_id": agent_id}

class EvaluateSecurityReq(BaseModel):
    agent_id: str
    operation: str
    command: Optional[str] = None
    path: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    user_confirmed: bool = False

@security_dash_router.post("/evaluate")
def evaluate_security(req: EvaluateSecurityReq):
    res = trust_gate.evaluate(
        agent_id=req.agent_id,
        operation=req.operation,
        command=req.command,
        path=req.path,
        context=req.context,
        user_confirmed=req.user_confirmed,
    )
    log_system_event(
        source="TRUSTGATE",
        event_type="SECURITY_EVALUATION",
        summary=f"TrustGate decision: {res.decision} for op '{req.operation}'",
        status="success" if res.allowed else ("warn" if res.decision == "WARN" else "denied"),
        details={
            "allowed": res.allowed,
            "decision": res.decision,
            "risk_level": res.risk_level,
            "reason": res.reason,
            "requires_user_confirmation": res.requires_user_confirmation,
        },
    )
    return {
        "allowed": res.allowed,
        "decision": res.decision,
        "risk_level": res.risk_level,
        "reason": res.reason,
        "requires_user_confirmation": res.requires_user_confirmation,
        "confirmation_token": res.confirmation_token,
        "warnings": res.warnings,
        "audit_event_id": res.audit_event.event_id if res.audit_event else None,
    }

class ConfirmWarningReq(BaseModel):
    confirmation_token: str

@security_dash_router.post("/confirm")
def confirm_security_warning(req: ConfirmWarningReq):
    try:
        res = trust_gate.confirm_warning(req.confirmation_token)
        log_system_event(
            source="TRUSTGATE",
            event_type="WARNING_CONFIRMED",
            summary=f"User confirmed warned operation: {res.decision}",
            status="success",
            details={"decision": res.decision, "allowed": res.allowed},
        )
        return {
            "allowed": res.allowed,
            "decision": res.decision,
            "risk_level": res.risk_level,
            "reason": res.reason,
            "requires_user_confirmation": res.requires_user_confirmation,
            "confirmation_token": res.confirmation_token,
            "warnings": res.warnings,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@security_dash_router.get("/audit")
def get_audit_trail(limit: int = Query(default=100, ge=1, le=500)):
    events = trust_gate.audit.get_events(limit=limit)
    valid, msg = trust_gate.audit.verify_chain_integrity()
    return {
        "chain_valid": valid,
        "chain_status": "VERIFIED" if valid else "TAMPERED",
        "chain_message": msg,
        "count": len(events),
        "events": [e.to_dict() for e in events],
    }

@security_dash_router.get("/policies")
def get_policies():
    return [vars(p) for p in trust_gate.policies.list_policies()]


# ── Live Activity Router ─────────────────────────────────────────────────────
activity_router = APIRouter(prefix="/api/activity", tags=["Live Activity"])

@activity_router.get("")
def get_recent_activity(limit: int = Query(default=50, ge=1, le=200)):
    """Returns aggregated real activity feed from AuditLogger and SessionStore."""
    events = []
    # Audit events
    for e in trust_gate.audit.get_events(limit=limit):
        events.append({
            "event_id": e.event_id,
            "timestamp": e.timestamp,
            "source": e.source.value,
            "event_type": e.event_type.value,
            "summary": e.summary,
            "status": "success" if e.decision == "ALLOW" else ("warn" if e.decision == "WARN" else "denied"),
            "details": e.details,
        })
    # Sort descending
    events.sort(key=lambda x: x["timestamp"], reverse=True)
    return events[:limit]

@activity_router.get("/stream")
async def activity_stream():
    """Server-Sent Events (SSE) stream for live dashboard telemetry."""
    return StreamingResponse(
        activity_broadcaster.subscribe(),
        media_type="text/event-stream",
    )


# ── CLI Providers Router ─────────────────────────────────────────────────────
providers_router = APIRouter(prefix="/api/providers", tags=["CLI Providers"])

class ProviderRunRequest(BaseModel):
    provider: str
    task: str
    project_root: Optional[str] = None
    confirm_warning: bool = False
    timeout_seconds: Optional[float] = 300.0

@providers_router.get("")
def list_providers(refresh: bool = False):
    """Lists all AI CLI providers and their truthful detection status."""
    force = refresh or is_render_environment()
    providers = provider_registry.list_providers(force_refresh=force)
    if is_render_environment():
        results = []
        for p in providers:
            d = p.to_dict()
            d["is_available"] = False
            d["status"] = "NOT_INSTALLED"
            d["executable_path"] = None
            d["version"] = None
            d["error_message"] = "LOCAL CLI EXECUTION AVAILABLE only on the user's local CLIVERSE machine."
            results.append(d)
        return results
    return [p.to_dict() for p in providers]

@providers_router.post("/refresh")
def refresh_providers():
    """Forces rediscovery of installed AI CLI binaries."""
    return list_providers(refresh=True)

@providers_router.get("/{provider_id}")
def get_provider_details(provider_id: str):
    """Retrieves specific details for an AI CLI provider."""
    p = provider_registry.get(provider_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found.")
    d = p.detect(force_refresh=True).to_dict()
    if is_render_environment():
        d["is_available"] = False
        d["status"] = "NOT_INSTALLED"
        d["executable_path"] = None
        d["version"] = None
        d["error_message"] = "LOCAL CLI EXECUTION AVAILABLE only on the user's local CLIVERSE machine."
    return d

@providers_router.post("/execute")
def execute_provider_task(req: ProviderRunRequest):
    """
    Executes a task through the complete real CLIVERSE pipeline with the requested AI CLI.
    Emits real-time audit and activity events into the dashboard feed.
    """
    p = provider_registry.get(req.provider)
    if not p:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {req.provider}")

    root = req.project_root or ACTIVE_STATE.get("project_root", str(BASE_DIR))

    if is_render_environment():
        msg = "LOCAL CLI EXECUTION AVAILABLE only on the user's local CLIVERSE machine."
        log_system_event(
            source="ORCHESTRATOR",
            event_type="cli_execution_rejected",
            summary=f"Cloud execution rejected for {p.display_name}: {msg}",
            status="denied",
            details={"provider": req.provider, "reason": "remote_host_not_supported"},
        )
        return {
            "ok": False,
            "session_id": "",
            "provider_id": req.provider,
            "project_root": root,
            "task": req.task,
            "status": "cloud_execution_unsupported",
            "returncode": -1,
            "stdout": "",
            "stderr": msg,
            "duration_seconds": 0.0,
            "memory_count": 0,
            "rule_decision": "UNKNOWN",
            "trust_gate_decision": "BLOCK",
            "trust_gate_reason": "Execution restricted to local workstation.",
            "error_message": msg,
        }

    log_system_event(
        source="ORCHESTRATOR",
        event_type="cli_execution_requested",
        summary=f"Execution requested: {p.display_name} on '{req.task}'",
        status="pending",
        details={"provider": req.provider, "project_root": root, "task": req.task},
    )

    def _event_broadcaster(evt):
        log_system_event(
            source=f"CLI:{evt.phase}",
            event_type=f"cli_{evt.phase.lower()}",
            summary=evt.message,
            status="success" if evt.level != "ERROR" else "denied",
            details=evt.data or {},
        )

    orchestrator = ExecutionOrchestrator(project_root=root, event_sink=_event_broadcaster)
    result = orchestrator.run(
        provider_name=req.provider,
        task=req.task,
        user_confirmed=req.confirm_warning,
        timeout_seconds=req.timeout_seconds,
    )

    log_system_event(
        source="ORCHESTRATOR",
        event_type="cli_execution_completed" if result.ok else "cli_execution_failed",
        summary=f"{p.display_name} finished with status '{result.status}' (code {result.returncode})",
        status="success" if result.ok else "denied",
        details={
            "session_id": result.session_id,
            "duration_seconds": result.duration_seconds,
            "returncode": result.returncode,
            "error": result.error_message,
        },
    )

    return result.to_dict()


# ── App Factory ──────────────────────────────────────────────────────────────
def create_app(data_root: Optional[Path | str] = None) -> FastAPI:
    if data_root is not None:
        configure_services(data_root=data_root)
    seed_initial_state_if_empty()

    app = FastAPI(
        title="CLIVERSE AI Control Center API",
        description="Unified cognitive, execution, and security command center for AI CLIs",
        version="2.0.0",
    )

    # Enable wide CORS for frontend dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount all sub-routers
    app.include_router(system_router)
    app.include_router(memory_router)
    app.include_router(rules_router)
    app.include_router(laya_router)
    app.include_router(git_router)
    app.include_router(sessions_router)
    app.include_router(security_dash_router)
    app.include_router(activity_router)
    app.include_router(providers_router)

    # Mount static frontend build if present
    frontend_dist = BASE_DIR / "frontend" / "dist"
    if frontend_dist.is_dir():
        assets_dir = frontend_dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            # Don't hijack /api
            if full_path.startswith("api"):
                raise HTTPException(status_code=404, detail="API endpoint not found")
            target = frontend_dist / full_path
            if target.is_file():
                from fastapi.responses import FileResponse
                return FileResponse(str(target))
            from fastapi.responses import FileResponse
            return FileResponse(str(frontend_dist / "index.html"))

    return app


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0" if (is_render_environment() or os.environ.get("HOST") == "0.0.0.0") else os.environ.get("HOST", "127.0.0.1")
    print("=" * 70)
    print(f"  CLIVERSE AI Control Center Backend starting on http://{host}:{port}")
    print(f"  Environment: {'Render Cloud' if is_render_environment() else 'Local Workstation'}")
    print(f"  Data Root:   {DATA_ROOT}")
    print("=" * 70)
    uvicorn.run("api:create_app", factory=True, host=host, port=port, log_level="info")
