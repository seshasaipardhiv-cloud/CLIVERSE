"""
Regulatory Monitor — Governance Layer

Monitors authoritative AI/data regulatory sources and maintains
a local policy database of relevant rules and updates.

Sources monitored:
- EU AI Act (European Parliament)
- GDPR (EUR-Lex)
- NIST AI RMF
- OWASP Top 10
- UK ICO guidance

This module ASSISTS with compliance awareness. It does NOT guarantee
legal compliance. Always consult qualified legal counsel.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from typing import Optional


@dataclass
class RegulatorySource:
    """Definition of a monitored regulatory source."""
    source_id: str
    name: str
    jurisdiction: str
    url: str
    category: str          # AI_REGULATION | DATA_PRIVACY | SECURITY | ETHICS
    description: str
    last_checked: Optional[str] = None
    version: Optional[str] = None


@dataclass
class RegulatoryUpdate:
    """A logged regulatory update or notice."""
    update_id: str
    source_id: str
    title: str
    summary: str
    effective_date: Optional[str]
    severity: str               # INFO | IMPORTANT | CRITICAL
    logged_at: str
    url: Optional[str] = None
    tags: list[str] = field(default_factory=list)


class RegulatoryMonitor:
    """
    Maintains awareness of relevant AI and data regulations.

    The monitor maintains:
    - A catalogue of authoritative regulatory sources
    - A local database of regulatory updates
    - Status of each monitored source

    In a production deployment, this would schedule periodic checks
    against the source URLs. In the current implementation, it maintains
    a static catalogue with the ability to log updates manually or
    via integration with a regulatory feed service.

    Usage:
        monitor = RegulatoryMonitor(db_path=".envcore/governance/regulatory.json")
        sources = monitor.list_sources()
        monitor.log_update(source_id="EU-AI-ACT", title="...", summary="...")
        updates = monitor.get_updates(severity="CRITICAL")
    """

    def __init__(self, db_path: str = ".envcore/governance/regulatory.json"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._sources: dict[str, RegulatorySource] = {}
        self._updates: list[RegulatoryUpdate] = []
        self._load_builtin_sources()
        self._load_db()

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def list_sources(self) -> list[RegulatorySource]:
        """Return all monitored regulatory sources."""
        return list(self._sources.values())

    def get_source(self, source_id: str) -> Optional[RegulatorySource]:
        return self._sources.get(source_id)

    def log_update(
        self,
        source_id: str,
        title: str,
        summary: str,
        effective_date: Optional[str] = None,
        severity: str = "INFO",
        url: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> RegulatoryUpdate:
        """Record a new regulatory update."""
        import uuid
        update = RegulatoryUpdate(
            update_id=str(uuid.uuid4()),
            source_id=source_id,
            title=title,
            summary=summary,
            effective_date=effective_date,
            severity=severity,
            logged_at=datetime.now(timezone.utc).isoformat(),
            url=url,
            tags=tags or [],
        )
        self._updates.append(update)
        self._save_db()
        return update

    def get_updates(
        self,
        source_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> list[RegulatoryUpdate]:
        """Query regulatory updates with optional filters."""
        results = self._updates
        if source_id:
            results = [u for u in results if u.source_id == source_id]
        if severity:
            results = [u for u in results if u.severity == severity]
        return results[-limit:]

    def status_report(self) -> dict:
        """Return a summary status of all monitored sources."""
        return {
            "total_sources": len(self._sources),
            "total_updates": len(self._updates),
            "critical_updates": len([u for u in self._updates if u.severity == "CRITICAL"]),
            "sources": [
                {
                    "id": s.source_id,
                    "name": s.name,
                    "jurisdiction": s.jurisdiction,
                    "last_checked": s.last_checked,
                    "version": s.version,
                }
                for s in self._sources.values()
            ],
        }

    # ------------------------------------------------------------------ #
    #  Built-in regulatory source catalogue                               #
    # ------------------------------------------------------------------ #

    def _load_builtin_sources(self) -> None:
        sources = [
            RegulatorySource(
                source_id="EU-AI-ACT",
                name="EU Artificial Intelligence Act",
                jurisdiction="European Union",
                url="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689",
                category="AI_REGULATION",
                description=(
                    "The world's first comprehensive AI regulation. Establishes risk-based "
                    "classification of AI systems (Unacceptable, High, Limited, Minimal risk) "
                    "and mandates conformity assessments, transparency, and human oversight "
                    "for high-risk AI applications."
                ),
                version="2024/1689",
                last_checked="2026-08-01",
            ),
            RegulatorySource(
                source_id="GDPR",
                name="General Data Protection Regulation",
                jurisdiction="European Union",
                url="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679",
                category="DATA_PRIVACY",
                description=(
                    "EU regulation governing personal data processing. Key articles for AI: "
                    "Art. 22 (automated decision-making), Art. 25 (data protection by design), "
                    "Art. 35 (DPIA), Art. 9 (special categories including biometrics)."
                ),
                version="2016/679",
                last_checked="2026-08-01",
            ),
            RegulatorySource(
                source_id="NIST-AI-RMF",
                name="NIST AI Risk Management Framework",
                jurisdiction="United States",
                url="https://www.nist.gov/system/files/documents/2023/01/26/AI RMF 1.0.pdf",
                category="AI_REGULATION",
                description=(
                    "Voluntary framework for managing AI risks across four functions: "
                    "GOVERN, MAP, MEASURE, MANAGE. Widely adopted as a baseline for "
                    "trustworthy AI development in the US."
                ),
                version="1.0",
                last_checked="2026-08-01",
            ),
            RegulatorySource(
                source_id="OWASP-LLM",
                name="OWASP LLM AI Security Top 10",
                jurisdiction="Global",
                url="https://owasp.org/www-project-top-10-for-large-language-model-applications/",
                category="SECURITY",
                description=(
                    "Top 10 security risks for LLM applications: Prompt Injection, "
                    "Insecure Output Handling, Training Data Poisoning, Model DoS, "
                    "Supply Chain Vulnerabilities, Sensitive Information Disclosure, etc."
                ),
                version="2025",
                last_checked="2026-08-01",
            ),
            RegulatorySource(
                source_id="UK-AI-FRAMEWORK",
                name="UK AI Regulatory Framework",
                jurisdiction="United Kingdom",
                url="https://www.gov.uk/government/publications/ai-regulation-a-pro-innovation-approach",
                category="AI_REGULATION",
                description=(
                    "UK's principles-based approach to AI regulation across existing regulators. "
                    "Five cross-sector principles: safety, transparency, fairness, "
                    "accountability, contestability."
                ),
                version="2023",
                last_checked="2026-08-01",
            ),
            RegulatorySource(
                source_id="CCPA",
                name="California Consumer Privacy Act",
                jurisdiction="United States (California)",
                url="https://oag.ca.gov/privacy/ccpa",
                category="DATA_PRIVACY",
                description=(
                    "California's comprehensive data privacy law. Grants consumers rights "
                    "to know, delete, opt-out, and non-discrimination. "
                    "Amended by CPRA (Prop 24) in 2020."
                ),
                version="CPRA 2020",
                last_checked="2026-08-01",
            ),
        ]
        for s in sources:
            self._sources[s.source_id] = s

    # ------------------------------------------------------------------ #
    #  Persistence                                                         #
    # ------------------------------------------------------------------ #

    def _load_db(self) -> None:
        if not self.db_path.exists():
            return
        try:
            data = json.loads(self.db_path.read_text())
            for u in data.get("updates", []):
                self._updates.append(RegulatoryUpdate(**u))
        except Exception:
            pass

    def _save_db(self) -> None:
        data = {"updates": [asdict(u) for u in self._updates]}
        self.db_path.write_text(json.dumps(data, indent=2))
