# CLIVERSE — Render Cloud Deployment Guide

This guide details the deployment of the unified CLIVERSE AI Intelligence & Control Center application onto Render.

---

## 1. Quick Deploy with Render Blueprint (`render.yaml`)

CLIVERSE includes a turnkey `render.yaml` specification at the repository root.

1. Connect your GitHub repository to Render.
2. Select **Blueprints** → **New Blueprint Instance**.
3. Select the `CLIVERSE` repository.
4. Render automatically parses `render.yaml`, provisions the persistent disk, installs Python & Node.js dependencies, builds the frontend, and launches the service.

---

## 2. Environment Variables Specification

| Variable | Required? | Default | Description |
| :--- | :---: | :---: | :--- |
| `RENDER` | **Yes** | `true` | Tells CLIVERSE it is operating in the Render cloud container. Automatically provided by Render. |
| `PORT` | **Yes** | `8000` | Port for the HTTP server to bind. Render automatically injects this (typically `10000`). |
| `CLIVERSE_DATA_ROOT` | **Yes** | `/var/data` | Directory where persistent SQLite databases, rules, audit logs, and identities reside. Must match the mounted Persistent Disk path. |
| `CLIVERSE_ADMIN_SECRET` | Recommended | *Auto-generated* | Secret authentication token used by Member 4 TrustGate to administer agent identities. |
| `PYTHON_VERSION` | **Yes** | `3.11.9` | Python runtime version. |
| `NODE_VERSION` | **Yes** | `20.18.0` | Node.js runtime for building the React frontend during deploy. |

---

## 3. Persistent Disk Configuration

Render Web Services are stateless by default. To persist CLIVERSE memory, SQLite sessions, audit logs, and rules across deploys and restarts, attach a **Persistent Disk**:

- **Disk Name:** `cliverse-persistent-storage`
- **Mount Path:** `/var/data`
- **Size:** 1 GB (Starter tier)

### Directory Structure Created Automatically on `/var/data`:
```
/var/data/
├── memory/
│   └── cliverse_memory.db     # Vector embeddings & document chunks
├── sessions/
│   └── sessions.db            # Audit & user execution sessions
├── rules/
│   └── global/                # Active global governance rules
├── identities/                # Agent cryptographic identities
├── audit/                     # Cryptographic audit hash chains
├── secrets/                   # Scrubbed encrypted secrets storage
└── governance/                # Regulatory sync cache
```

---

## 4. Build and Start Commands

### Build Command:
```bash
pip install -e . && cd frontend && npm install && npm run build && cd ..
```
*Installs the core Python wheel, installs frontend dependencies, and compiles the production React bundle into `frontend/dist`.*

### Start Command:
```bash
uvicorn api:create_app --factory --host 0.0.0.0 --port $PORT
```
*Starts the ASGI FastAPI application using the zero-argument factory `api:create_app`, listening on all interfaces at the dynamically assigned Render port.*

### Production Health Check:
- **Path:** `/api/health`
- **HTTP Method:** `GET`
- **Expected Status:** `200 OK`
- Returns verified status of all 5 subsystems, persistent storage writability, and data root path.

---

## 5. Local CLI vs. Cloud Architecture

CLIVERSE strictly enforces truthful reporting:
- **Local Workstation:** Invoking `cliverse <provider>` executes host binaries (`claude.cmd`, `aider.exe`, `agy.exe`) locally.
- **Render Cloud:** Cloud containers cannot access the developer's local desktop binaries. When `RENDER=true`:
  - The dashboard surfaces: `LOCAL CLI EXECUTION AVAILABLE only on the user's local CLIVERSE machine.`
  - The API truthfully reports `status: "NOT_INSTALLED"` for host-only tools and never fabricates fake responses.
