"""
CLIVERSE Audit Layer
Member 4: Security + Governance + Audit

Provides complete, tamper-evident event logging for all
operations passing through the CLIVERSE pipeline.
"""

from .events import AuditLogger, AuditEvent

__all__ = ["AuditLogger", "AuditEvent"]
