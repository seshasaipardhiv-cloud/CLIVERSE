"""
Unified CLIVERSE Interactive Dashboard Integration Test Suite
=============================================================
Validates end-to-end integration between the React command-center frontend
and the unified FastAPI backend in `api.py`.

Ensures all 8 major dashboard domains function correctly against real subsystems:
  1. System Health & Projects (/api/health, /api/projects, /api/projects/select)
  2. Memory Explorer (/api/memory/stats, /api/memory/search, /api/memory)
  3. Rules Intelligence (/api/rules, /api/rules/resolve)
  4. Laya Workspace Pipeline (/api/laya/intelligence, /api/laya/plan, /api/laya/execute)
  5. Security & Trust Governance (/api/security/summary, /api/security/identities, /api/security/evaluate, /api/security/confirm, /api/security/audit)
  6. Git & Recovery (/api/git/status, /api/git/diff, /api/git/history)
  7. Persistent Sessions (/api/sessions, /api/sessions/{id}, /api/sessions/{id}/finish)
  8. Live Telemetry & SPA Serving (/api/activity, /)
"""

import pytest
from starlette.testclient import TestClient
from api import create_app


@pytest.fixture(scope="module")
def client():
    """Initializes FastAPI test client with seeded backend state."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


# ── Domain 1: System Health & Projects ───────────────────────────────────────

def test_system_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert "subsystems" in data
    assert data["subsystems"]["memory"]["status"] in ("OK_WITH_RESULTS", "OK_EMPTY")
    assert data["subsystems"]["rules"]["status"] in ("OK_WITH_RESULTS", "OK_EMPTY")
    assert data["subsystems"]["security"]["status"] == "ACTIVE"
    assert data["subsystems"]["git"]["status"] in ("CLEAN", "MODIFIED")


def test_projects_list_and_select(client):
    res = client.get("/api/projects")
    assert res.status_code == 200
    data = res.json()
    assert "available_projects" in data
    assert "active_project" in data
    assert len(data["available_projects"]) > 0

    # Select project
    sel_res = client.post("/api/projects/select", json={
        "project_id": "cliverse-core",
        "cli_name": "claude-cli"
    })
    assert sel_res.status_code == 200
    sel_data = sel_res.json()
    assert sel_data["project_id"] == "cliverse-core"
    assert sel_data["cli_name"] == "claude-cli"


# ── Domain 2: Memory Explorer ────────────────────────────────────────────────

def test_memory_stats(client):
    res = client.get("/api/memory/stats?project_id=cliverse-core")
    assert res.status_code == 200
    data = res.json()
    assert "stats" in data
    assert data["stats"]["total_chunks"] >= 0
    assert data["embedding_dimension"] > 0


def test_memory_search(client):
    res = client.get("/api/memory/search", params={
        "query": "architecture memory rules",
        "project_id": "cliverse-core",
        "top_k": 3,
        "min_score": 0.05
    })
    assert res.status_code == 200
    data = res.json()
    assert "results" in data
    assert len(data["results"]) > 0
    first = data["results"][0]
    assert "content" in first
    assert "score" in first
    assert "source_type" in first


def test_memory_store_and_delete(client):
    store_res = client.post("/api/memory", json={
        "content": "Dashboard verification chunk for test_memory_store_and_delete",
        "project_id": "cliverse-core",
        "source_type": "scratchpad"
    })
    assert store_res.status_code == 200
    record_id = store_res.json()["record_id"]
    assert record_id is not None

    # Delete chunk
    del_res = client.delete(f"/api/memory/{record_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"


# ── Domain 3: Rules Intelligence ─────────────────────────────────────────────

def test_rules_list(client):
    res = client.get("/api/rules?project_id=cliverse-core")
    assert res.status_code == 200
    data = res.json()
    assert "rules" in data
    assert data["count"] > 0
    rule_ids = [r["rule_id"] for r in data["rules"]]
    assert any("rule-" in rid for rid in rule_ids)


def test_rules_create_and_delete(client):
    rule_payload = {
        "rule_id": "test-dash-001",
        "name": "Dashboard Test Rule",
        "description": "Ensure no direct database writes without migration scripts",
        "scope": "project",
        "priority": 75,
        "effect": "require",
        "target": "database",
        "is_mandatory": True,
        "project_id": "cliverse-core"
    }
    create_res = client.post("/api/rules", json=rule_payload)
    assert create_res.status_code == 200
    assert create_res.json()["rule_id"] == "test-dash-001"

    # Delete the rule
    del_res = client.delete("/api/rules/test-dash-001")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"


def test_rules_resolution_simulator(client):
    res = client.post("/api/rules/resolve", json={
        "task": "Perform direct database migration without test approval",
        "project_id": "cliverse-core",
        "cli_name": "claude-cli"
    })
    assert res.status_code == 200
    data = res.json()
    assert "winning_decision" in data
    assert "winning_rules" in data
    assert "explanation_trace" in data


# ── Domain 4: Laya Workspace Pipeline ────────────────────────────────────────

def test_laya_intelligence_context(client):
    res = client.post("/api/laya/intelligence", json={
        "task": "Write unit tests for memory storage engine and check architecture",
        "project_id": "cliverse-core",
        "cli_name": "claude-cli",
        "top_k": 3
    })
    assert res.status_code == 200
    data = res.json()
    assert "retrieved_context_items" in data
    assert "applicable_rules" in data
    assert "winning_rules" in data
    assert "combined_laya_context" in data
    assert len(data["retrieved_context_items"]) > 0


def test_laya_plan(client):
    res = client.post("/api/laya/plan", json={
        "task": "Add end-to-end regression tests for CLI session lifecycle",
        "project_id": "cliverse-core",
        "cli_name": "claude-cli"
    })
    assert res.status_code == 200
    data = res.json()
    assert "ready" in data
    assert "applicable_rule_ids" in data
    assert "context_provenance" in data


def test_laya_execute_pipeline_allowed(client):
    res = client.post("/api/laya/execute", json={
        "task": "Inspect repository files and review guidelines",
        "command": "git status",
        "project_id": "cliverse-core",
        "cli_name": "claude-cli"
    })
    assert res.status_code == 200
    data = res.json()
    assert "pipeline" in data
    assert "memory" in data["pipeline"]
    assert "rules" in data["pipeline"]
    assert "trustgate" in data["pipeline"]
    assert "execution" in data["pipeline"]


# ── Domain 5: Security & Trust Governance ────────────────────────────────────

def test_security_summary(client):
    res = client.get("/api/security/summary")
    assert res.status_code == 200
    data = res.json()
    assert "chain_valid" in data
    assert data["chain_valid"] is True
    assert "audit_events_count" in data
    assert data["audit_events_count"] > 0


def test_security_identities(client):
    res = client.get("/api/security/identities")
    assert res.status_code == 200
    identities = res.json()
    assert isinstance(identities, list)
    assert len(identities) > 0
    assert identities[0]["cli_name"] in ("claude-cli", "gemini-cli", "codex-cli", "aider-cli")


def test_security_evaluation_and_audit(client):
    # Get active agent
    id_res = client.get("/api/security/identities")
    agent_id = id_res.json()[0]["agent_id"]

    eval_res = client.post("/api/security/evaluate", json={
        "agent_id": agent_id,
        "operation": "execute",
        "command": "git status"
    })
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert "allowed" in eval_data
    assert "decision" in eval_data

    # Audit trail verification
    audit_res = client.get("/api/security/audit?limit=10")
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert "chain_valid" in audit_data
    assert audit_data["chain_valid"] is True
    assert len(audit_data["events"]) > 0


def test_security_warning_confirmation(client):
    # Force a WARN evaluation by testing an operation with warning
    id_res = client.get("/api/security/identities")
    agent_id = id_res.json()[0]["agent_id"]

    eval_res = client.post("/api/security/evaluate", json={
        "agent_id": agent_id,
        "operation": "execute",
        "command": "git reset --hard HEAD~1"
    })
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    if eval_data.get("requires_user_confirmation") and eval_data.get("confirmation_token"):
        token = eval_data["confirmation_token"]
        conf_res = client.post("/api/security/confirm", json={"confirmation_token": token})
        assert conf_res.status_code == 200
        assert conf_res.json()["decision"] in ("ALLOW", "WARN_CONFIRMED")


# ── Domain 6: Git & Recovery ─────────────────────────────────────────────────

def test_git_status_and_history(client):
    res = client.get("/api/git/status")
    assert res.status_code == 200
    data = res.json()
    assert "branch" in data
    assert "is_clean" in data
    assert "changed_paths" in data

    hist_res = client.get("/api/git/history?limit=5")
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert isinstance(history, list)
    assert len(history) > 0
    assert "commit_id" in history[0]


def test_git_diff(client):
    res = client.get("/api/git/diff")
    assert res.status_code == 200
    data = res.json()
    assert "diff" in data


# ── Domain 7: Persistent Sessions ────────────────────────────────────────────

def test_sessions_lifecycle(client):
    # 1. Create a session
    create_res = client.post("/api/sessions", json={
        "user_request": "Execute dashboard verification automated test flow"
    })
    assert create_res.status_code == 200
    session = create_res.json()
    session_id = session["session_id"]
    assert len(session_id) > 8
    assert session["status"] in ("running", "active")

    # 2. Query session detail
    detail_res = client.get(f"/api/sessions/{session_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["session"]["session_id"] == session_id
    assert "events" in detail

    # 3. Finish session
    finish_res = client.post(f"/api/sessions/{session_id}/finish", json={"status": "completed"})
    assert finish_res.status_code == 200
    assert finish_res.json()["status"] == "completed"


# ── Domain 8: Live Telemetry & SPA Serving ───────────────────────────────────

def test_recent_activity(client):
    res = client.get("/api/activity?limit=20")
    assert res.status_code == 200
    activities = res.json()
    assert isinstance(activities, list)
    assert len(activities) > 0
    assert "event_id" in activities[0]
    assert "source" in activities[0]


def test_spa_serving(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "<div id=\"root\"></div>" in res.text
