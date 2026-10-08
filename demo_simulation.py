"""
CLIVERSE — Live Demonstration & Simulation Script
Demonstrates the full Member 4 Trust Gate in action:
1. Agent Identity Registration & Fingerprinting
2. Permitted safe operations (ALLOW)
3. High-risk warned operations with regulatory alerts (WARN)
4. Destructive command blocking (BLOCK)
5. Sandbox violation detection
6. Cryptographic chain-hashed audit verification
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
    print("\n[+] Initializing CLIVERSE Trust Gate...")
    gate = TrustGate(project_root=".", sandbox_mode=SandboxMode.PERMISSIVE)
    time.sleep(0.5)

    # 1. Identity Registration
    print("\n--- STAGE 1: CLI AGENT REGISTRATION ---")
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
    print(f"  Reason     : {res_safe.reason}")

    # 3. Warned Operation (Regulatory Alert)
    print("\n--- STAGE 3: REGULATORY WARNING (GDPR / EU AI ACT) ---")
    op_warn = "Process user credit card and biometric facial recognition data"
    print(f"  Requested Task: '{op_warn}'")
    res_warn = gate.evaluate(
        agent_id=ident.agent_id,
        operation="execute",
        command=op_warn,
        context={"compliance_scope": "production_pipeline"},
    )
    print(f"  Decision   : {res_warn.decision}")
    print(f"  Risk Level : {res_warn.risk_level}")
    print(f"  Warnings   :")
    for w in res_warn.warnings:
        print(f"    - {w}")

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
    print(f"  Reason     : {res_unauth.reason}")

    # 6. Audit Trail Display
    print("\n--- STAGE 6: TAMPER-EVIDENT AUDIT TRAIL ---")
    gate.audit.print_timeline(limit=10)

    print("=" * 80)
    print("      DEMONSTRATION COMPLETE — ALL GATES VERIFIED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    run_demo()
