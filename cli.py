"""
CLIVERSE Member 4 CLI Tool

Provides terminal commands to inspect security policies, test operations,
audit logs, view regulatory feeds, verify cryptographic integrity, and manage identities.
"""

import sys
import argparse

try:
    from .trust_gate import TrustGate
    from .security.sandbox import SandboxMode
    from .security.identity import ScopeViolationError
except (ImportError, ValueError):
    from trust_gate import TrustGate
    from security.sandbox import SandboxMode
    from security.identity import ScopeViolationError


def main():
    parser = argparse.ArgumentParser(
        prog="cliverse-security",
        description="CLIVERSE Trust & Governance Layer (Member 4)",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Audit command
    subparsers.add_parser("audit", help="Display recent audit trail")

    # Audit verification command
    subparsers.add_parser("audit-verify", help="Cryptographically verify audit trail SHA-256 chain")

    # Check operation command
    check_parser = subparsers.add_parser("check", help="Evaluate an operation through the trust gate")
    check_parser.add_argument("op", help="Command or operation description to check")
    check_parser.add_argument("--agent-id", default=None, help="Agent identity ID")
    check_parser.add_argument("--path", default=None, help="File path if checking filesystem access")
    check_parser.add_argument("--confirm", action="store_true", help="Explicitly approve warned operations")

    # Confirm token command
    conf_parser = subparsers.add_parser("confirm", help="Confirm a pending warned operation token")
    conf_parser.add_argument("token", help="Confirmation token")

    # Policies command
    subparsers.add_parser("policies", help="List active governance policies")

    # Regulatory command
    subparsers.add_parser("regulatory", help="List monitored regulatory sources")

    # Sync regulatory sources command
    subparsers.add_parser("sync-regulatory", help="Actively check and sync monitored regulatory sources")

    # Register agent command
    reg_parser = subparsers.add_parser("register-agent", help="Register a new CLI agent session")
    reg_parser.add_argument("cli_name", help="Name of CLI (e.g. claude-cli, aider, custom)")
    reg_parser.add_argument("--scopes", nargs="*", help="Requested scopes (e.g. read write execute)")
    reg_parser.add_argument("--admin-token", default=None, help="Administrative token for privileged scopes")

    # Alerts command
    subparsers.add_parser("alerts", help="View blocked/warned security alerts")

    args = parser.parse_args()
    gate = TrustGate(sandbox_mode=SandboxMode.STRICT)

    if args.command == "audit":
        gate.audit.print_timeline()

    elif args.command == "audit-verify":
        valid, msg = gate.audit.verify_chain_integrity()
        status_badge = "[VERIFIED]" if valid else "[TAMPERED]"
        print(f"\n{status_badge} {msg}\n")

    elif args.command == "check":
        agent_id = args.agent_id
        if not agent_id:
            ident = gate.identity.register(cli_name="claude-cli")
            agent_id = ident.agent_id
            print(f"[+] Using active identity: {ident.cli_name} ({agent_id[:8]})")

        res = gate.evaluate(
            agent_id=agent_id,
            operation="execute",
            command=args.op,
            path=args.path,
            user_confirmed=args.confirm,
        )
        print(f"\nEvaluation Result:")
        print(f"  Decision   : {res.decision}")
        print(f"  Risk Level : {res.risk_level}")
        print(f"  Allowed    : {res.allowed}")
        print(f"  Reason     : {res.reason}")
        if res.requires_user_confirmation:
            print(f"  Confirmation Token: {res.confirmation_token}")
            print(f"  -> Run 'python cli.py confirm {res.confirmation_token}' to approve.")
        if res.warnings:
            print("  Warnings   :")
            for w in res.warnings:
                print(f"    - {w}")
        print()

    elif args.command == "confirm":
        try:
            res = gate.confirm_warning(args.token)
            print(f"\n[+] Operation Approved & Executed:")
            print(f"  Decision   : {res.decision}")
            print(f"  Risk Level : {res.risk_level}")
            print(f"  Allowed    : {res.allowed}\n")
        except Exception as e:
            print(f"\n[-] Confirmation Error: {str(e)}\n")

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
            print(f"    Category: {s.category} | Version: {s.version} | Status: {s.status}")
            print(f"    URL: {s.url}\n")
        print(f"{'-'*70}\n")

    elif args.command == "sync-regulatory":
        print("\n[+] Syncing regulatory feeds...")
        res = gate.regulatory.sync_regulatory_sources()
        print(f"  Synced Sources : {res['synced_sources']}")
        print(f"  Cached/Offline : {res['cached_or_offline']}")
        print(f"  Timestamp      : {res['timestamp']}\n")

    elif args.command == "register-agent":
        try:
            ident = gate.identity.register(
                cli_name=args.cli_name,
                scopes=args.scopes,
                admin_token=args.admin_token,
            )
            print(f"\n[+] Registered Agent Session:")
            print(f"  Agent ID   : {ident.agent_id}")
            print(f"  Session ID : {ident.session_id}")
            print(f"  CLI Name   : {ident.cli_name}")
            print(f"  Scopes     : {', '.join(ident.scopes)}")
            print(f"  Trusted    : {ident.is_trusted}\n")
        except ScopeViolationError as e:
            print(f"\n[-] Registration Rejected: {str(e)}\n")

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
