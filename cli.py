"""
CLIVERSE Member 4 CLI Tool

Provides terminal commands to inspect security policies, test operations,
audit logs, view regulatory feeds, and manage agent identities.

Usage:
    python -m cli audit
    python -m cli check "rm -rf /"
    python -m cli policies
    python -m cli regulatory
    python -m cli register-agent claude-cli
"""

import sys
import argparse
try:
    from .trust_gate import TrustGate
    from .security.sandbox import SandboxMode
except (ImportError, ValueError):
    from trust_gate import TrustGate
    from security.sandbox import SandboxMode


def main():
    parser = argparse.ArgumentParser(
        prog="cliverse-security",
        description="CLIVERSE Trust & Governance Layer (Member 4)",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Audit command
    subparsers.add_parser("audit", help="Display recent audit trail")

    # Check operation command
    check_parser = subparsers.add_parser("check", help="Evaluate an operation through the trust gate")
    check_parser.add_argument("op", help="Command or operation description to check")
    check_parser.add_argument("--agent-id", default=None, help="Agent identity ID")
    check_parser.add_argument("--path", default=None, help="File path if checking filesystem access")

    # Policies command
    subparsers.add_parser("policies", help="List active governance policies")

    # Regulatory command
    subparsers.add_parser("regulatory", help="List monitored regulatory sources")

    # Register agent command
    reg_parser = subparsers.add_parser("register-agent", help="Register a new CLI agent session")
    reg_parser.add_argument("cli_name", help="Name of CLI (e.g. claude-cli, aider, custom)")

    # Alerts command
    subparsers.add_parser("alerts", help="View blocked/warned security alerts")

    args = parser.parse_args()
    gate = TrustGate()

    if args.command == "audit":
        gate.audit.print_timeline()

    elif args.command == "check":
        agent_id = args.agent_id
        if not agent_id:
            # Auto-register an ad-hoc session for testing
            ident = gate.identity.register(cli_name="test-cli")
            agent_id = ident.agent_id
            print(f"[+] Created temporary identity: {ident.cli_name} ({agent_id[:8]})")

        res = gate.evaluate(
            agent_id=agent_id,
            operation="execute",
            command=args.op,
            path=args.path,
        )
        print(f"\nEvaluation Result:")
        print(f"  Decision   : {res.decision}")
        print(f"  Risk Level : {res.risk_level}")
        print(f"  Reason     : {res.reason}")
        if res.warnings:
            print("  Warnings   :")
            for w in res.warnings:
                print(f"    - {w}")
        print()

    elif args.command == "policies":
        print(f"\n{'-'*70}")
        print("  ACTIVE GOVERNANCE POLICIES")
        print(f"{'-'*70}")
        for p in gate.policies.list_policies():
            status = "ENABLED" if p.enabled else "DISABLED"
            print(f"  [{p.policy_id}] {p.name:<30} | {p.decision.value:<6} | {p.risk_level:<8} ({status})")
            if p.regulatory_ref:
                print(f"         Ref: {p.regulatory_ref}")
        print(f"{'-'*70}\n")

    elif args.command == "regulatory":
        print(f"\n{'-'*70}")
        print("  MONITORED REGULATORY SOURCES")
        print(f"{'-'*70}")
        for s in gate.regulatory.list_sources():
            print(f"  [{s.source_id}] {s.name} ({s.jurisdiction})")
            print(f"    Category: {s.category} | Version: {s.version}")
            print(f"    URL: {s.url}\n")
        print(f"{'-'*70}\n")

    elif args.command == "register-agent":
        ident = gate.identity.register(cli_name=args.cli_name)
        print(f"\n[+] Registered Agent Session:")
        print(f"  Agent ID   : {ident.agent_id}")
        print(f"  Session ID : {ident.session_id}")
        print(f"  CLI Name   : {ident.cli_name}")
        print(f"  Scopes     : {', '.join(ident.scopes)}")
        print(f"  Trusted    : {ident.is_trusted}\n")

    elif args.command == "alerts":
        alerts = gate.audit.get_security_events()
        print(f"\n{'-'*70}")
        print(f"  SECURITY ALERTS ({len(alerts)} events)")
        print(f"{'-'*70}")
        for a in alerts:
            print(f"  {a.display()}")
        print(f"{'-'*70}\n")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
