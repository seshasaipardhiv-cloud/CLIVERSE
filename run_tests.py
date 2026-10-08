"""
CLIVERSE Member 4 Comprehensive Test Suite (unittest runner)
Tests all 6 core security, governance, and audit pillars.
"""

import sys
import shutil
import tempfile
import unittest
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from security.identity import IdentityManager, ScopeViolationError
from security.permissions import PermissionEngine, Decision
from security.sandbox import Sandbox, SandboxPolicy, SandboxMode
from security.secrets import SecretsManager
from governance.policies import PolicyEngine, PolicyDecision
from governance.regulatory import RegulatoryMonitor
from governance.compliance import ComplianceChecker
from audit.events import AuditLogger, EventSource, EventType
from trust_gate import TrustGate


class TestMember4(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cliverse_test_")
        self.temp_env = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. Identity & Scope Escalation Prevention
    def test_identity_scope_protection(self):
        mgr = IdentityManager(storage_path=str(self.temp_env / "identities"), admin_secret="test-admin-secret")
        
        # Untrusted CLI requesting privileged scope must be rejected
        with self.assertRaises(ScopeViolationError):
            mgr.register("untrusted-random-agent", scopes=["admin", "execute"])

        # Trusted CLI can receive privileged scopes
        trusted = mgr.register("claude-cli", scopes=["write", "execute"])
        self.assertIn("write", trusted.scopes)
        self.assertTrue(trusted.is_trusted)

        # Untrusted with admin token can be granted privileged scopes
        authorized = mgr.register("custom-agent", scopes=["write"], admin_token="test-admin-secret")
        self.assertIn("write", authorized.scopes)

    # 2. Strict Sandbox & Process Containment
    def test_strict_sandbox_and_env_scrubbing(self):
        policy = SandboxPolicy(mode=SandboxMode.STRICT, allowed_root=str(self.temp_env))
        sandbox = Sandbox(policy=policy, project_root=str(self.temp_env))

        # Allowed command in allowlist
        allowed, violation = sandbox.check_operation("execute", command="python -V")
        self.assertTrue(allowed)
        self.assertIsNone(violation)

        # Disallowed command binary blocked in STRICT mode
        allowed_disallowed, violation = sandbox.check_operation("execute", command="nmap localhost")
        self.assertFalse(allowed_disallowed)
        self.assertIsNotNone(violation)
        self.assertEqual(violation.severity, "HIGH")

    # 3. User Confirmation on Warnings
    def test_warning_requires_explicit_user_confirmation(self):
        gate = TrustGate(
            project_root=str(self.temp_env),
            storage_dir=str(self.temp_env / ".envcore"),
            sandbox_mode=SandboxMode.PERMISSIVE,
        )
        ident = gate.identity.register(cli_name="claude-cli", scopes=["read", "write", "execute"])

        # Operation triggering a warning without prior confirmation must be BLOCKED
        res = gate.evaluate(
            agent_id=ident.agent_id,
            operation="execute",
            command="Processing credit card and user biometrics",
            user_confirmed=False,
        )
        self.assertFalse(res.allowed)
        self.assertEqual(res.decision, "WARN")
        self.assertTrue(res.requires_user_confirmation)
        self.assertIsNotNone(res.confirmation_token)

        # Confirming with the generated token approves the operation
        confirmed_res = gate.confirm_warning(res.confirmation_token)
        self.assertTrue(confirmed_res.allowed)
        self.assertEqual(confirmed_res.decision, "WARN_CONFIRMED")

    # 4. Cryptographic Full-Field Chain Integrity Verification
    def test_audit_cryptographic_chain_verification(self):
        logger = AuditLogger(log_dir=str(self.temp_env / "audit"))
        logger.log(
            source=EventSource.USER,
            event_type=EventType.REQUEST,
            summary="Initial task",
        )
        logger.log(
            source=EventSource.SECURITY,
            event_type=EventType.PERMISSION_ALLOWED,
            summary="Permitted execution",
        )

        # Valid chain
        valid, msg = logger.verify_chain_integrity()
        self.assertTrue(valid)

        # Simulate tampering on disk
        log_file = logger._log_file
        content = log_file.read_text(encoding="utf-8")
        tampered_content = content.replace("Initial task", "TAMPERED task")
        log_file.write_text(tampered_content, encoding="utf-8")

        # Integrity verification must catch tampering
        valid_tampered, tampered_msg = logger.verify_chain_integrity()
        self.assertFalse(valid_tampered)
        self.assertIn("Tampering detected", tampered_msg)

    # 5. Regulatory Automated Monitoring Sync
    def test_regulatory_sources_sync(self):
        monitor = RegulatoryMonitor(db_path=str(self.temp_env / "regulatory.json"))
        sync_result = monitor.sync_regulatory_sources(timeout_seconds=2)
        self.assertGreaterEqual(sync_result["total"], 5)
        self.assertIn("synced_sources", sync_result)

    # 6. Full TrustGate Integration
    def test_full_trustgate_flow(self):
        gate = TrustGate(
            project_root=str(self.temp_env),
            storage_dir=str(self.temp_env / ".envcore"),
            sandbox_mode=SandboxMode.PERMISSIVE,
        )
        ident = gate.identity.register(cli_name="claude-cli", scopes=["read", "write", "execute"])

        # Safe command -> ALLOW
        res_safe = gate.evaluate(agent_id=ident.agent_id, operation="execute", command="git status")
        self.assertTrue(res_safe.allowed)
        self.assertEqual(res_safe.decision, "ALLOW")

        # Critical danger command -> BLOCK
        res_block = gate.evaluate(agent_id=ident.agent_id, operation="execute", command="rm -rf /")
        self.assertFalse(res_block.allowed)
        self.assertEqual(res_block.decision, "BLOCK")


if __name__ == "__main__":
    unittest.main(verbosity=2)
