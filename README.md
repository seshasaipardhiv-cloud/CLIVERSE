# CLIVERSE — AI CLI Intelligence Environment

> **A local-first AI development environment that sits above existing AI CLIs, giving them persistent memory, structured reasoning, user-defined rules, Git-based version control, recoverability, security, governance, and a unified dashboard.**

---

## 🏛️ System Architecture & Four-Member Structure

```
                  USER
                    │
                    ▼
             ┌─────────────┐
             │  MEMBER 3   │
             │  Dashboard  │
             └──────┬──────┘
                    │
                    ▼
             ┌─────────────┐
             │  MEMBER 1   │
             │ Core + Laya │
             └──────┬──────┘
                    │
           ┌────────┴────────┐
           ▼                 ▼
     ┌───────────┐      ┌───────────┐
     │ MEMBER 2  │      │ MEMBER 4  │
     │ RAG+Rules │      │ Security  │
     └─────┬─────┘      │ Governance│
           │            └─────┬─────┘
           └──────────┬───────┘
                      ▼
                 AI CLI (Claude, Gemini, Copilot, Aider, etc.)
                      │
                      ▼
                     Git (Versioned changes & recovery)
                      │
                      ▼
                    Audit (Tamper-evident trail)
```

---

## 🛡️ Member 4: Security + Governance + Audit Layer

Member 4 owns the **trust, control, compliance, and auditability layer** of CLIVERSE.

Every operation requested by a user, planned by Laya, or executed by an AI CLI must pass through the **Trust Gate Pipeline**:

```
CLI / Operation
      ↓
  Identity             (IdentityManager: session tokens, scopes, trusted flags)
      ↓
 Permission            (PermissionEngine: scopes, filesystem boundaries, dangerous patterns)
      ↓
Sandbox Policy         (Sandbox: strict/permissive isolation, rate limits, extensions)
      ↓
Regulatory Compliance  (PolicyEngine + RegulatoryMonitor: GDPR, EU AI Act, NIST, OWASP, PCI-DSS)
      ↓
ALLOW / WARN / BLOCK
      ↓
Audit Logged           (AuditLogger: cryptographic chain hash, secrets redaction, JSONL)
      ↓
  Execution
```

---

## 📁 Repository Structure

```
CLIVERSE/
├── security/                      # Security subsystem
│   ├── __init__.py
│   ├── identity.py               # Agent/CLI identity lifecycle & fingerprinting
│   ├── permissions.py            # Scope, command, & filesystem permission checks
│   ├── sandbox.py                # Strict/permissive sandbox boundary enforcement
│   └── secrets.py                # In-memory secrets vault with auto-redaction
│
├── governance/                    # Governance & Regulatory subsystem
│   ├── __init__.py
│   ├── policies.py               # Machine-readable policy engine (14+ built-in policies)
│   ├── regulatory.py             # Regulatory monitor (EU AI Act, GDPR, NIST, OWASP, CCPA)
│   └── compliance.py             # Unified compliance evaluation & recommendations
│
├── audit/                         # Audit subsystem
│   ├── __init__.py
│   └── events.py                 # Tamper-evident, chain-hashed event logger
│
├── trust_gate.py                 # Unified Trust Gate orchestrator for all checks
├── api.py                        # FastAPI REST API endpoints (For Dashboard & Core)
├── cli.py                        # Terminal CLI tool (`cliverse-security`)
├── run_tests.py                  # Standalone test runner (unittest compatible)
├── requirements.txt              # Dependencies
└── tests/
    └── test_security_governance_audit.py   # Full unit & integration test suite
```

---

## 🚀 Quickstart & Usage

### 1. Run the Test Suite
```bash
python run_tests.py
```

### 2. Use the CLI Tool

**Inspect active governance policies:**
```bash
python cli.py policies
```

**Inspect monitored regulatory sources:**
```bash
python cli.py regulatory
```

**Register a CLI agent session:**
```bash
python cli.py register-agent claude-cli
```

**Evaluate an operation before execution:**
```bash
# Test dangerous operation (Blocked)
python cli.py check "rm -rf /"

# Test safe operation (Allowed)
python cli.py check "git status"
```

**View the tamper-evident audit timeline:**
```bash
python cli.py audit
```

---

## 🔌 Integration Contracts for Team Members

### For Member 1 (Core + Laya):
```python
from trust_gate import TrustGate

gate = TrustGate(project_root=".")

# 1. Register CLI agent at session start
ident = gate.identity.register(cli_name="claude-cli")

# 2. Before executing any command or modifying files:
eval_result = gate.evaluate(
    agent_id=ident.agent_id,
    operation="execute",
    command="python app.py",
    path="src/app.py",
    context={"task": "Build login form"}
)

if not eval_result.allowed:
    print(f"Blocked: {eval_result.reason}")
else:
    if eval_result.decision == "WARN":
        print(f"Proceeding with warnings: {eval_result.warnings}")
    # Run the operation...
```

### For Member 3 (Dashboard):
- **REST Endpoints** (`api.py`):
  - `POST /api/v1/security/identity/register` — Register new sessions
  - `GET /api/v1/security/identity/active` — Active CLI sessions
  - `POST /api/v1/security/evaluate` — Test operations
  - `GET /api/v1/security/audit/events` — Retrieve structured audit trail
  - `GET /api/v1/security/audit/security-alerts` — Security WARN/BLOCK incidents
  - `GET /api/v1/security/governance/policies` — Active governance policies
  - `GET /api/v1/security/governance/regulatory-sources` — Authoritative regulatory feeds

---

## 🔒 Security Guarantees
- **No plaintext secrets logged**: Automatic scanning and redaction across all audit logs.
- **Fail-closed**: Any unrecognized identity or unhandled exception defaults to `BLOCK`.
- **Chain-hashed logs**: Every audit event includes a SHA-256 hash chaining to the previous event for tamper-evidence.
- **Regulatory tracking**: Maps operations to specific articles of GDPR, EU AI Act, OWASP Top 10, PCI-DSS, and HIPAA.
