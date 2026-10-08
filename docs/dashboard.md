# CLIVERSE AI Command Center — Interactive Dashboard (Member 3)

## 1. Overview & Architectural Philosophy

The **CLIVERSE AI Command Center** is a high-density, real-time developer operating system for AI CLI agents. Built as the unifying frontend and visualization layer (Member 3), it connects directly to the underlying CLIVERSE subsystem engines without any mocked data or synthetic stubs:

* **Member 1 (Core CLI & Flow):** Request planning, session history (`sessions.db`), Git inspection & rollback recovery.
* **Member 2 (Persistent Memory & Rules Intelligence - FROZEN):** SQLite vector/keyword hybrid retrieval, local baseline embeddings (64-dim), hierarchical rule conflict resolution (`rules_store`), and Laya unified intelligence context assembly.
* **Member 4 (Security & Governance):** TrustGate sandbox policy enforcement, scoped agent credentials, warning confirmation gate, and SHA-256 tamper-evident cryptographic audit ledger.

---

## 2. Design System & Visual Language

Inspired by **Linear**, **Vercel**, and **Raycast**, the dashboard is crafted as a dark-mode military/engineering mission control:
* **Background Neutrals:** `#070b14` (root foundation), `#0d1322` (surface panels), `#162035` (borders & interactive states).
* **Semantic Accents:**
  * **Emerald Green (`#10b981` / `#059669`):** Safe, operational, verified, allowed, low risk.
  * **Rose Red (`#f43f5e` / `#e11d48`):** Denied, blocked, high-risk security violation, tampered ledger.
  * **Amber Yellow (`#f59e0b`):** Warning, pending human confirmation, medium risk, advisory constraint.
  * **Sky Blue (`#0ea5e9`):** Information, active sessions, Member 1 flow telemetry.
  * **Purple (`#a855f7`):** Cognitive AI, Laya planning, structured prompt generation.

---

## 3. Screen-by-Screen Capabilities

### 3.1 Overview (Control Center Matrix)
* **Live System Health:** Real-time pulse monitoring for all 4 subsystems (Memory RAG, Rules Intelligence, Security TrustGate, and Git Inspection).
* **Quick-Commander Pipeline:** Allows immediate testing of user prompts through the 5-stage CLIVERSE engine directly from the home view.
* **Subsystem Status Cards:** One-click drill-downs into Memory, Rules, Security, and Git.
* **Live Telemetry Stream:** Real-time event log powered by Server-Sent Events (SSE).

### 3.2 Laya Workspace (Cognitive Pipeline Inspector)
* **5-Stage Step Visualizer:**
  1. `TASK INPUT` (Task text, role, constraints, budget).
  2. `MEMBER 2 MEMORY RAG` (Ranked snippet retrieval with provenance links).
  3. `MEMBER 2 RULES ENGINE` (Winning engineering rules & precedence explanation).
  4. `MEMBER 1 PLANNING` (Structured task assembly & prompt synthesis).
  5. `MEMBER 4 TRUSTGATE` (Security decision: ALLOW, WARN, or BLOCK).
* **Interactive Warning Confirmation Gate:** When an operation requires human confirmation (e.g. destructive commands or policy warnings), a confirmation modal pops up allowing the operator to authorize with a cryptographic token.
* **Ready-to-Inject Prompt Viewer:** Full view of the exact markdown prompt prepared for the downstream LLM.

### 3.3 Memory Explorer (RAG & Knowledge Lake)
* **Semantic Search:** Interactive search with `top_k`, `min_score`, and `source_type` filters.
* **Provenance Inspector:** Displays exact file origins (`source_path`), line ranges (`start_line`-`end_line`), and relevance scores.
* **Ingest Knowledge Modal:** Direct document and note ingestion into the project memory database (`cliverse_memory.db`).
* **Chunk Lifecycle:** Ability to inspect chunk details and delete obsolete records.

### 3.4 Rules Intelligence (Engineering Governance)
* **Hierarchical Rule Browser:** Displays all Global, Project, and CLI-scoped rules.
* **Priority & Effect Badges:** Distinct visual representations for `DENY (6)`, `ASK (5)`, `REQUIRE (4)`, `ENFORCE (3)`, `WARN (2)`, `ALLOW (1)`.
* **Rule Conflict Resolution Simulator:** Live testbench to evaluate prompt text against active rules and view the complete deterministic resolution explanation trace.
* **Rule Authoring Modal:** Form for creating structured engineering rules with conditions, targets, and mandatory enforcement flags.

### 3.5 Security & Trust (TrustGate Operations)
* **Boundary Banner:** Clearly displays the technical distinction between **Member 2 Rule Semantics** (developer engineering guidelines) and **Member 4 Security Governance** (untrusted CLI isolation and cryptographic verification).
* **Agent Identity Manager:** Lists fingerprinted CLI identities (`claude-cli`, `gemini-cli`) with authorized capability scopes (`read`, `write`, `git`, `execute`).
* **Interactive TrustGate Playground:** Tests arbitrary operations and commands against the security policy in real-time.
* **Tamper-Evident SHA-256 Audit Trail:** Full ledger of every executed security decision with forward-chain hash integrity validation.

### 3.6 Git & Rollback Recovery
* **Repository Health:** Live git status showing current branch, clean/dirty state, and staged/unstaged file list.
* **Unified Diff Viewer:** Monospace syntax-highlighted diff of uncommitted changes.
* **Commit History:** Recent commit log with hash, subject line, and associated session tags.
* **Session Rollback (Undo):** Reverts all changes made by a target session via Member 1's `GitRecovery` engine.

### 3.7 Persistent Sessions & Lifecycle
* **SessionStore Inspector:** Live queries against SQLite `.envcore/sessions/sessions.db`.
* **Session Detail & Event Timeline:** Inspects every lifecycle event (`TASK_PLANNED`, `EXECUTION_ATTEMPTED`, `RULE_EVALUATED`) recorded for a session.
* **Session Lifecycle Control:** Ability to start new CLI sessions and mark existing sessions as `completed` or `failed`.

### 3.8 Live Activity Stream
* **Full-Fidelity SSE Telemetry:** Subscribes to `/api/activity/stream` for sub-millisecond event streaming.
* **Source & Status Filtering:** Filter by source (`LAYA`, `MEMORY`, `RULES`, `TRUSTGATE`, `GIT`, `SESSION`) and status (`success`, `warn`, `denied`).

---

## 4. Launching the System

### 4.1 Production Mode (Single-Port Unified Server)

The FastAPI server automatically serves the compiled production build from `frontend/dist`:

```powershell
# 1. Build the React frontend
cd A:\CLIVERSE\frontend
npm run build

# 2. Start the unified backend
cd A:\CLIVERSE
python api.py
```
Open **`http://127.0.0.1:8000`** in your browser. Both the complete interactive UI and all API endpoints are served on port 8000.

### 4.2 Development Mode (Hot-Reloading)

```powershell
# Terminal 1 — Backend API
cd A:\CLIVERSE
python -m uvicorn api:create_app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — Frontend Dev Server
cd A:\CLIVERSE\frontend
npm run dev
```
Open **`http://localhost:5173`** (Vite proxies all `/api` requests to port 8000).

---

## 5. Verification & Testing

The dashboard is verified by a 20-test automated integration suite covering every endpoint:

```powershell
python -m pytest tests/test_dashboard_integration.py -v
```

All 20 tests validate schema compliance, HTTP status codes, and cross-subsystem orchestration with 100% green results.
