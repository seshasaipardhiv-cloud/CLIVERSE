"""
Compliance Checker — Governance Layer

Combines PolicyEngine + RegulatoryMonitor to produce a unified
compliance evaluation for any operation.

This is the final gate in the security pipeline before execution:
    CLI/Operation → Identity → Permission → Security Policy → Regulatory Policy → ALLOW/WARN/BLOCK
"""

from dataclasses import dataclass, field
from typing import Optional

from .policies import PolicyEngine, PolicyDecision, PolicyResult
from .regulatory import RegulatoryMonitor


@dataclass
class ComplianceResult:
    """
    Unified result from the compliance checker.
    Aggregates both policy and regulatory evaluations.
    """
    decision: PolicyDecision
    policy_result: Optional[PolicyResult] = None
    regulatory_warnings: list[str] = field(default_factory=list)
    summary: str = ""
    recommendations: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.decision == PolicyDecision.ALLOW

    @property
    def blocked(self) -> bool:
        return self.decision == PolicyDecision.BLOCK

    def __str__(self) -> str:
        return f"[{self.decision}] {self.summary}"


class ComplianceChecker:
    """
    Unified compliance evaluation combining governance policies
    and regulatory context.

    Usage:
        checker = ComplianceChecker()
        result = checker.check("Store user email addresses in logs")
        if result.blocked:
            raise ComplianceBlockedError(result.summary)
        if result.decision == PolicyDecision.WARN:
            show_warning(result.summary)
    """

    def __init__(
        self,
        policy_engine: Optional[PolicyEngine] = None,
        regulatory_monitor: Optional[RegulatoryMonitor] = None,
        custom_policies_path: Optional[str] = None,
    ):
        self.policy_engine = policy_engine or PolicyEngine(
            custom_policies_path=custom_policies_path
        )
        self.regulatory_monitor = regulatory_monitor or RegulatoryMonitor()

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def check(
        self,
        operation_text: str,
        context: Optional[dict] = None,
    ) -> ComplianceResult:
        """
        Run the full compliance evaluation pipeline.

        1. Evaluate against governance policies.
        2. Check regulatory context for matched policy categories.
        3. Return unified ComplianceResult.
        """
        # 1. Policy evaluation
        policy_result = self.policy_engine.evaluate(operation_text, context)

        # 2. Gather regulatory references from matched policies
        reg_warnings: list[str] = []
        recommendations: list[str] = []

        for policy in policy_result.matched_policies:
            if policy.regulatory_ref:
                source_id = self._extract_source_id(policy.regulatory_ref)
                source = self.regulatory_monitor.get_source(source_id) if source_id else None
                if source:
                    reg_warnings.append(
                        f"Relevant regulation: {source.name} ({source.jurisdiction}) — "
                        f"Ref: {policy.regulatory_ref}"
                    )
                    recommendations.append(
                        f"Review {policy.regulatory_ref} at: {source.url}"
                    )

        # 3. Build summary
        if policy_result.decision == PolicyDecision.BLOCK:
            summary = f"Operation blocked: {policy_result.reason}"
        elif policy_result.decision == PolicyDecision.WARN:
            summary = f"Operation permitted with warnings: {policy_result.reason}"
            if reg_warnings:
                summary += f" | Regulatory context: {reg_warnings[0]}"
        else:
            summary = "Operation passed all compliance checks"

        return ComplianceResult(
            decision=policy_result.decision,
            policy_result=policy_result,
            regulatory_warnings=reg_warnings,
            summary=summary,
            recommendations=recommendations,
        )

    def quick_check(self, operation_text: str) -> PolicyDecision:
        """Fast path: returns only the decision enum."""
        return self.check(operation_text).decision

    def check_batch(self, operations: list[str]) -> list[ComplianceResult]:
        """Check multiple operations at once."""
        return [self.check(op) for op in operations]

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _extract_source_id(self, regulatory_ref: str) -> Optional[str]:
        """
        Map a regulatory reference string to a known source ID.
        e.g., "GDPR Art. 25" → "GDPR"
        """
        mapping = {
            "GDPR": "GDPR",
            "EU AI Act": "EU-AI-ACT",
            "CCPA": "CCPA",
            "NIST": "NIST-AI-RMF",
            "OWASP": "OWASP-LLM",
            "HIPAA": None,   # Not yet in source catalogue
            "PCI-DSS": None, # Not yet in source catalogue
        }
        for key, source_id in mapping.items():
            if key.lower() in regulatory_ref.lower():
                return source_id
        return None
