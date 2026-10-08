"""
Policy Engine — Governance Layer

Evaluates operations against machine-readable governance policies.
Produces ALLOW / WARN / BLOCK decisions based on configured rules.

This is the governance counterpart to the security PermissionEngine.
Security handles identity/scope/filesystem.
Policy handles business rules, regulatory constraints, and risk thresholds.
"""

import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    BLOCK = "BLOCK"


class PolicyCategory(str, Enum):
    DATA_PRIVACY = "DATA_PRIVACY"
    SECURITY = "SECURITY"
    COMPLIANCE = "COMPLIANCE"
    OPERATIONAL = "OPERATIONAL"
    ETHICAL_AI = "ETHICAL_AI"


@dataclass
class Policy:
    """A single governance policy rule."""
    policy_id: str
    name: str
    category: PolicyCategory
    description: str
    pattern: str                         # Regex to match against operation text
    decision: PolicyDecision             # What to do when matched
    risk_level: str = "MEDIUM"           # LOW | MEDIUM | HIGH | CRITICAL
    enabled: bool = True
    regulatory_ref: Optional[str] = None # e.g., "GDPR Art. 25", "EU AI Act Art. 10"


@dataclass
class PolicyResult:
    decision: PolicyDecision
    matched_policies: list[Policy] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision == PolicyDecision.ALLOW

    def __str__(self) -> str:
        return f"[{self.decision}] {self.reason}"


class PolicyEngine:
    """
    Governance policy evaluation engine.

    Loads policies from the built-in set and optional custom policy files.
    Evaluates operations against all active policies and returns
    the most restrictive decision (BLOCK > WARN > ALLOW).

    Usage:
        engine = PolicyEngine()
        result = engine.evaluate("DELETE user data", context={"agent": "claude-cli"})
        if result.decision == PolicyDecision.BLOCK:
            raise OperationBlockedError(result.reason)
    """

    def __init__(self, custom_policies_path: Optional[str] = None):
        self._policies: list[Policy] = []
        self._load_builtin_policies()
        if custom_policies_path:
            self._load_custom_policies(custom_policies_path)

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def evaluate(self, operation_text: str, context: Optional[dict] = None) -> PolicyResult:
        """
        Evaluate an operation against all active policies.
        Returns the most restrictive decision found.
        """
        matched: list[Policy] = []
        warnings: list[str] = []
        blocks: list[str] = []

        for policy in self._policies:
            if not policy.enabled:
                continue
            if re.search(policy.pattern, operation_text, re.IGNORECASE):
                matched.append(policy)
                if policy.decision == PolicyDecision.BLOCK:
                    blocks.append(f"[{policy.policy_id}] {policy.name}: {policy.description}")
                elif policy.decision == PolicyDecision.WARN:
                    warnings.append(f"[{policy.policy_id}] {policy.name}: {policy.description}")

        if blocks:
            return PolicyResult(
                decision=PolicyDecision.BLOCK,
                matched_policies=matched,
                warnings=warnings,
                blocks=blocks,
                reason=f"Blocked by {len(blocks)} policy rule(s): {blocks[0]}",
            )
        if warnings:
            return PolicyResult(
                decision=PolicyDecision.WARN,
                matched_policies=matched,
                warnings=warnings,
                blocks=blocks,
                reason=f"Warning from {len(warnings)} policy rule(s): {warnings[0]}",
            )

        return PolicyResult(
            decision=PolicyDecision.ALLOW,
            matched_policies=matched,
            reason="No policy violations found",
        )

    def add_policy(self, policy: Policy) -> None:
        """Add a policy at runtime."""
        self._policies.append(policy)

    def disable_policy(self, policy_id: str) -> bool:
        """Disable a policy by ID."""
        for p in self._policies:
            if p.policy_id == policy_id:
                p.enabled = False
                return True
        return False

    def list_policies(self) -> list[Policy]:
        """Return all policies."""
        return list(self._policies)

    def list_active_policies(self) -> list[Policy]:
        """Return only enabled policies."""
        return [p for p in self._policies if p.enabled]

    # ------------------------------------------------------------------ #
    #  Built-in policy set                                                 #
    # ------------------------------------------------------------------ #

    def _load_builtin_policies(self) -> None:
        builtin: list[Policy] = [

            # ── Data Privacy ───────────────────────────────────────────
            Policy(
                policy_id="DP-001",
                name="PII Exposure Risk",
                category=PolicyCategory.DATA_PRIVACY,
                description="Operation may expose Personally Identifiable Information",
                pattern=r"(email|phone|ssn|social.?security|passport|national.?id|date.?of.?birth|credit.?card)",
                decision=PolicyDecision.WARN,
                risk_level="HIGH",
                regulatory_ref="GDPR Art. 4, CCPA Sec. 1798.140",
            ),
            Policy(
                policy_id="DP-002",
                name="Bulk Data Export",
                category=PolicyCategory.DATA_PRIVACY,
                description="Bulk export of user data may violate privacy regulations",
                pattern=r"(export|dump|extract).{0,30}(users|customers|patients|members)",
                decision=PolicyDecision.WARN,
                risk_level="HIGH",
                regulatory_ref="GDPR Art. 25",
            ),
            Policy(
                policy_id="DP-003",
                name="Hardcoded PII in Code",
                category=PolicyCategory.DATA_PRIVACY,
                description="Hardcoding personal data in source code is prohibited",
                pattern=r'(name|email|phone)\s*=\s*["\'][^"\']{5,}["\']',
                decision=PolicyDecision.WARN,
                risk_level="MEDIUM",
                regulatory_ref="GDPR Art. 25",
            ),

            # ── Security ───────────────────────────────────────────────
            Policy(
                policy_id="SEC-001",
                name="Hardcoded Credentials",
                category=PolicyCategory.SECURITY,
                description="Hardcoded API keys or passwords detected",
                pattern=r'(api[_-]?key|password|secret|token)\s*=\s*["\'][^"\']{8,}["\']',
                decision=PolicyDecision.BLOCK,
                risk_level="CRITICAL",
                regulatory_ref="OWASP A07:2021",
            ),
            Policy(
                policy_id="SEC-002",
                name="SQL Injection Pattern",
                category=PolicyCategory.SECURITY,
                description="Possible SQL injection vulnerability",
                pattern=r"(SELECT|INSERT|UPDATE|DELETE).{0,50}(\$\{|f[\"']|%s|format\()",
                decision=PolicyDecision.WARN,
                risk_level="HIGH",
                regulatory_ref="OWASP A03:2021",
            ),
            Policy(
                policy_id="SEC-003",
                name="Insecure HTTP Usage",
                category=PolicyCategory.SECURITY,
                description="Use of HTTP instead of HTTPS for external requests",
                pattern=r'http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)',
                decision=PolicyDecision.WARN,
                risk_level="MEDIUM",
                regulatory_ref="OWASP A02:2021",
            ),
            Policy(
                policy_id="SEC-004",
                name="Production Config Modification",
                category=PolicyCategory.SECURITY,
                description="Modification of production configuration detected",
                pattern=r"(production|prod).*config|config.*(production|prod)",
                decision=PolicyDecision.BLOCK,
                risk_level="CRITICAL",
            ),

            # ── Ethical AI ─────────────────────────────────────────────
            Policy(
                policy_id="AI-001",
                name="Biometric Data Processing",
                category=PolicyCategory.ETHICAL_AI,
                description="Processing biometric data requires explicit governance approval",
                pattern=r"(facial.?recognition|fingerprint|biometric|voice.?print|iris.?scan)",
                decision=PolicyDecision.WARN,
                risk_level="HIGH",
                regulatory_ref="EU AI Act Art. 10, GDPR Art. 9",
            ),
            Policy(
                policy_id="AI-002",
                name="High-Risk AI System",
                category=PolicyCategory.ETHICAL_AI,
                description="High-risk AI system category detected — requires compliance review",
                pattern=r"(credit.?scor|loan.?approv|hiring|recruitment|medical.?diagnos|criminal)",
                decision=PolicyDecision.WARN,
                risk_level="HIGH",
                regulatory_ref="EU AI Act Annex III",
            ),
            Policy(
                policy_id="AI-003",
                name="Automated Decision Making",
                category=PolicyCategory.ETHICAL_AI,
                description="Automated decisions affecting individuals require human oversight",
                pattern=r"(auto.?decis|automated.?(approv|reject|ban|suspend))",
                decision=PolicyDecision.WARN,
                risk_level="MEDIUM",
                regulatory_ref="GDPR Art. 22",
            ),

            # ── Compliance ─────────────────────────────────────────────
            Policy(
                policy_id="COMP-001",
                name="Financial Data Handling",
                category=PolicyCategory.COMPLIANCE,
                description="Operations involving financial data require PCI-DSS compliance",
                pattern=r"(credit.?card|card.?number|cvv|cardholder|payment.?data)",
                decision=PolicyDecision.WARN,
                risk_level="CRITICAL",
                regulatory_ref="PCI-DSS v4.0",
            ),
            Policy(
                policy_id="COMP-002",
                name="Health Data Processing",
                category=PolicyCategory.COMPLIANCE,
                description="Health data processing requires HIPAA compliance",
                pattern=r"(patient|medical.?record|health.?data|phi|diagnosis|treatment.?plan)",
                decision=PolicyDecision.WARN,
                risk_level="CRITICAL",
                regulatory_ref="HIPAA Sec. 164",
            ),

            # ── Operational ────────────────────────────────────────────
            Policy(
                policy_id="OPS-001",
                name="Direct Database Mutation",
                category=PolicyCategory.OPERATIONAL,
                description="Direct DROP/TRUNCATE statements require explicit approval",
                pattern=r"\b(DROP\s+TABLE|TRUNCATE\s+TABLE|DROP\s+DATABASE)\b",
                decision=PolicyDecision.BLOCK,
                risk_level="CRITICAL",
            ),
            Policy(
                policy_id="OPS-002",
                name="Unreviewed External Dependency",
                category=PolicyCategory.OPERATIONAL,
                description="Installing external packages without review",
                pattern=r"(pip install|npm install|yarn add|cargo add|go get)\s+[^\s]+",
                decision=PolicyDecision.WARN,
                risk_level="MEDIUM",
            ),
        ]
        self._policies.extend(builtin)

    def _load_custom_policies(self, path: str) -> None:
        """Load additional policies from a JSON file."""
        p = Path(path)
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text())
            for item in data.get("policies", []):
                self._policies.append(
                    Policy(
                        policy_id=item["policy_id"],
                        name=item["name"],
                        category=PolicyCategory(item.get("category", "OPERATIONAL")),
                        description=item.get("description", ""),
                        pattern=item["pattern"],
                        decision=PolicyDecision(item.get("decision", "WARN")),
                        risk_level=item.get("risk_level", "MEDIUM"),
                        enabled=item.get("enabled", True),
                        regulatory_ref=item.get("regulatory_ref"),
                    )
                )
        except Exception as e:
            print(f"[PolicyEngine] Warning: could not load custom policies: {e}")
