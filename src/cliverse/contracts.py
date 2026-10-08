"""Typed boundaries between core, memory/rules and trust modules."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from .errors import CliverseError


class AuthorizationDenied(CliverseError):
    code = "AUTHORIZATION_DENIED"
    suggestion = "Review the decision with the project security owner."


class InvalidAuthorizationDecision(CliverseError):
    code = "INVALID_AUTHORIZATION_DECISION"
    suggestion = "The authorizer must return ALLOW, WARN or BLOCK with a reason."


class Decision(str, Enum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class StructuredTask:
    role: str
    context: str
    task: str
    requirements: tuple[str, ...]
    constraints: tuple[str, ...]
    output: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "context": self.context,
            "task": self.task,
            "requirements": list(self.requirements),
            "constraints": list(self.constraints),
            "output": self.output,
        }


@dataclass(frozen=True)
class ContextItem:
    item_id: str
    content: str
    source: str
    score: float | None = None


@dataclass(frozen=True)
class ContextBundle:
    items: tuple[ContextItem, ...]
    provenance: tuple[str, ...]
    retrieved_at: str

    @classmethod
    def empty(cls, reason: str) -> "ContextBundle":
        if not reason.strip():
            raise ValueError("An empty context bundle must explain why it is empty.")
        return cls(
            items=(),
            provenance=(reason,),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )


@dataclass(frozen=True)
class Rule:
    rule_id: str
    content: str
    scope: str
    priority: int
    source: str


@dataclass(frozen=True)
class MemoryRef:
    memory_id: str
    source: str
    stored_at: str


@dataclass(frozen=True)
class MemoryHit:
    memory_id: str
    content: str
    source: str
    score: float | None = None


class MemoryProvider(Protocol):
    def retrieve_context(self, task: StructuredTask) -> ContextBundle: ...

    def get_applicable_rules(self, task: StructuredTask) -> list[Rule]: ...

    def store_memory(self, data: dict[str, Any]) -> MemoryRef: ...

    def search_memory(self, query: str) -> list[MemoryHit]: ...


@dataclass(frozen=True)
class AuthorizationRequest:
    identity: str
    operation: str
    project_root: str
    paths: tuple[str, ...] = ()
    executable: str | None = None
    arguments: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuthorizationDecision:
    decision: Decision
    reason: str
    requires_confirmation: bool = False


class Authorizer(Protocol):
    def authorize(self, request: AuthorizationRequest) -> AuthorizationDecision: ...


def require_authorized(
    decision: AuthorizationDecision,
    *,
    warning_confirmed: bool = False,
) -> None:
    """Fail closed; WARN requires an explicit confirmation from the caller."""
    if (
        not isinstance(decision, AuthorizationDecision)
        or not isinstance(decision.decision, Decision)
        or not decision.reason.strip()
    ):
        raise InvalidAuthorizationDecision("Authorizer returned an invalid decision.")
    if decision.decision == Decision.ALLOW:
        return
    if decision.decision == Decision.WARN and warning_confirmed:
        return
    raise AuthorizationDenied(
        f"Authorization decision {decision.decision.value}: {decision.reason}"
    )
