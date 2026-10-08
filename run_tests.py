"""
CLIVERSE Member 4 Standalone Test Runner (Standard Library unittest compatible)
"""

import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import shutil
import tempfile
import unittest

from security.identity import IdentityManager
from security.permissions import PermissionEngine, Decision
from security.sandbox import Sandbox, SandboxPolicy
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

    def test_identity_lifecycle(self):
        mgr = IdentityManager(storage_path=str(self.temp_env / "identities"))
        ident = mgr.register("claude-cli", scopes=["read", "write"])
        self.assertIsNotNone(ident.agent_id)
        self.assertEqual(ident.cli_name, "claude-cli")
        self.assertTrue(ident.is_trusted)
        
        val = mgr.validate(ident.agent_id)
        self.assertIsNotNone(val)
        self.assertEqual(val.fingerprint, ident.fingerprint)

        self.assertTrue(mgr.revoke(ident.agent_id))
        self.assertIsNone(mgr.validate(ident.agent_id))

    def test_permissions(self):
        engine = PermissionEngine(project_root=str(self.temp_env))
        mgr = IdentityManager(storage_path=str(self.temp_env / "identities"))
        
        readonly_ident = mgr.register("untrusted-cli", scopes=["read"])
        res = engine.check(readonly_ident, operation="write")
        self.assertEqual(res.decision, Decision.BLOCK)

        writer_ident = mgr.register("claude-cli", scopes=["write", "execute"])
        res = engine.check(writer_ident, operation="write")
        self.assertEqual(res.decision, Decision.ALLOW)

        res_danger = engine.check(writer_ident, operation="execute", command="rm -rf /")
        self.assertEqual(res_danger.decision, Decision.BLOCK)

    def test_secrets_and_redaction(self):
        sm = SecretsManager(storage_path=str(self.temp_env / "secrets"))
        sm.store("API_TOKEN", "sk-proj-super-secret-token-12345")
        self.assertTrue(sm.exists("API_TOKEN"))
        self.assertEqual(sm.get("API_TOKEN"), "sk-proj-super-secret-token-12345")

        raw_log = "Making request with key sk-proj-super-secret-token-12345"
        self.assertIn("[REDACTED]", sm.redact(raw_log))

    def test_governance_and_compliance(self):
        checker = ComplianceChecker()
        res_secret = checker.check("api_key = 'sk-1234567890abcdef'")
        self.assertEqual(res_secret.decision, PolicyDecision.BLOCK)

        res_pii = checker.check("System analyzing biometric facial recognition data")
        self.assertEqual(res_pii.decision, PolicyDecision.WARN)
        self.assertTrue(len(res_pii.regulatory_warnings) > 0)

    def test_audit_logger(self):
        logger = AuditLogger(log_dir=str(self.temp_env / "audit"))
        ev = logger.log(
            source=EventSource.USER,
            event_type=EventType.REQUEST,
            summary="Test event",
        )
        self.assertIsNotNone(ev.chain_hash)
        events = logger.get_events()
        self.assertGreaterEqual(len(events), 2)

    def test_trust_gate_pipeline(self):
        gate = TrustGate(project_root=str(self.temp_env), storage_dir=str(self.temp_env / ".envcore"))
        ident = gate.identity.register(cli_name="claude-cli", scopes=["read", "write", "execute"])

        res_safe = gate.evaluate(agent_id=ident.agent_id, operation="write", path=str(self.temp_env / "app.py"))
        self.assertTrue(res_safe.allowed)
        self.assertEqual(res_safe.decision, "ALLOW")

        res_block = gate.evaluate(agent_id=ident.agent_id, operation="execute", command="rm -rf /")
        self.assertFalse(res_block.allowed)
        self.assertEqual(res_block.decision, "BLOCK")


if __name__ == "__main__":
    unittest.main(verbosity=2)
