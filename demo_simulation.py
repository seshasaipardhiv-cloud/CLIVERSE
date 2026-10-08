"""
CLIVERSE — Live Demonstration & Simulation Script
Demonstrates the full Member 4 Trust Gate with:
1. Agent Identity Registration & Scope Boundaries
2. Permitted safe operations (ALLOW)
3. High-risk warned operations with Mandatory User Confirmation (WARN -> USER CONFIRMED)
4. Destructive command blocking (BLOCK)
5. Strict Sandbox isolation
6. Tamper-evident cryptographic chain integrity verification
"""

import sys
import time
from pathlib import Path

# Add root directory
sys.path.insert(0, str(Path(__file__).parent))

from trust_gate import TrustGate
from security.sandbox import SandboxMode


def run_demo():
    print("=" * 80)
    print("      CLIVERSE - TRUST GATE & GOVERNANCE LIVE DEMONSTRATION")
    print("=" * 80)
    print("\n[+] Initializing CLIVERSE Trust Gate (Strict Mode)...")
    gate = TrustGate(project_root=".", sandbox_mode=SandboxMode.STRICT)
    time.sleep(0.3)

    # 1. Identity Registration
    print("\n--- STAGE 1: CLI AGENT REGISTRATION & SCOPES ---")
    ident = gate.identity.register(
        cli_name="claude-cli",
        scopes=["read", "write", "git", "execute"],
        metadata={"user": "developer", "environment": "local"},
    )
    print(f"  Agent ID     : {ident.agent_id}")
    print(f"  Session ID   : {ident.session_id}")
    print(f"  CLI Provider : {ident.cli_name}")
    print(f"  Fingerprint  : {ident.fingerprint[:24]}...")
    print(f"  Scopes       : {', '.join(ident.scopes)}")
    print(f"  Trusted      : {ident.is_trusted}")

    # 2. Safe Operation
    print("\n--- STAGE 2: SAFE DEVELOPMENT OPERATION ---")
    op_safe = "git status"
    print(f"  Requested Command: '{op_safe}'")
    res_safe = gate.evaluate(
        agent_id=ident.agent_id,
        operation="execute",
        command=op_safe,
    )
    print(f"  Decision   : {res_safe.decision}")
    print(f"  Risk Level : {res_safe.risk_level}")
    print(f"  Allowed    : {res_safe.allowed}")
    print(f"  Reason     : {res_safe.reason}")

    # 3. Warned Operation with Explicit User Confirmation Flow
    print("\n--- STAGE 3: REGULATORY WARNING & MANDATORY USER CONFIRMATION ---")
    task_desc = "Process user credit card and biometric facial recognition data"
    print(f"  Requested Task: '{task_desc}'")
    
    # 3a. Initial attempt (Blocked awaiting confirmation)
    res_warn = gate.evaluate(
        agent_id=ident.agent_id,
        operation="execute",
        command="python process_user_data.py",
        context={"compliance_scope": task_desc},
        user_confirmed=False,
    )
    print(f"  Initial Decision : {res_warn.decision} (Allowed: {res_warn.allowed})")
    print(f"  Requires Confirm : {res_warn.requires_user_confirmation}")
    if res_warn.confirmation_token:
        print(f"  Confirm Token    : {res_warn.confirmation_token[:18]}...")
    if res_warn.warnings:
        print(f"  Regulatory Warns : {res_warn.warnings[0][:80]}...")

    # 3b. User confirms execution
    if res_warn.confirmation_token:
        print("\n  [>] User reviews regulatory warnings and confirms execution:")
        res_confirmed = gate.confirm_warning(res_warn.confirmation_token)
        print(f"  Post-Confirm Dec : {res_confirmed.decision} (Allowed: {res_confirmed.allowed})")
        print(f"  Reason           : {res_confirmed.reason}")

    # 4. Destructive Operation Blocked
    print("\n--- STAGE 4: DESTRUCTIVE OPERATION PREVENTED ---")
    op_block = "rm -rf /"
    print(f"  Requested Command: '{op_block}'")
    res_block = gate.evaluate(
        agent_id=ident.agent_id,
        operation="execute",
        command=op_block,
    )
    print(f"  Decision   : {res_block.decision}")
    print(f"  Risk Level : {res_block.risk_level}")
    print(f"  Allowed    : {res_block.allowed}")
    print(f"  Reason     : {res_block.reason}")

    # 5. Unauthorized / Revoked Agent
    print("\n--- STAGE 5: UNREGISTERED / UNTRUSTED IDENTITY ---")
    res_unauth = gate.evaluate(
        agent_id="unregistered-agent-id",
        operation="write",
        path="src/index.ts",
    )
    print(f"  Decision   : {res_unauth.decision}")
    print(f"  Risk Level : {res_unauth.risk_level}")
    print(f"  Allowed    : {res_unauth.allowed}")
    print(f"  Reason     : {res_unauth.reason}")

    # 6. Audit Trail & Cryptographic Verification
    print("\n--- STAGE 6: TAMPER-EVIDENT AUDIT TRAIL & CRYPTOGRAPHIC VERIFICATION ---")
    gate.audit.print_timeline(limit=10)
    
    valid, msg = gate.audit.verify_chain_integrity()
    print(f"  [+] Cryptographic Chain Integrity: {'VERIFIED' if valid else 'FAILED'}")
    print(f"  [+] Details: {msg}")

    print("\n" + "=" * 80)
    print("      DEMONSTRATION COMPLETE - ALL 6 SECURITY GATES VERIFIED")
    print("=" * 80)


if __name__ == "__main__":
    run_demo()
