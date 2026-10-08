"""Structured request planning with explicit context and clarification gates."""

from dataclasses import dataclass

from .contracts import ContextBundle, MemoryProvider, Rule, StructuredTask
from .errors import CliverseError


class MemoryProviderUnavailable(CliverseError):
    code = "MEMORY_PROVIDER_UNAVAILABLE"
    suggestion = "Connect Member 2's provider or explicitly pass --without-memory."


class PlanningError(CliverseError):
    code = "PLANNING_ERROR"
    suggestion = "Check the request and provider response against the documented contracts."


@dataclass(frozen=True)
class PlanningRequest:
    task: str
    role: str = "AI coding assistant"
    context: str = ""
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    output: str = "Implement the task and report verification."
    clarification_questions: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanningResult:
    task: StructuredTask | None
    clarification_questions: tuple[str, ...]
    context_provenance: tuple[str, ...]
    applicable_rule_ids: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.task is not None and not self.clarification_questions


class RequestPlanner:
    """Build a structured prompt; never infer answers to unresolved questions."""

    def __init__(
        self,
        memory_provider: MemoryProvider | None = None,
        *,
        allow_context_free: bool = False,
    ) -> None:
        self._memory_provider = memory_provider
        self._allow_context_free = allow_context_free

    def plan(self, request: PlanningRequest) -> PlanningResult:
        task_text = request.task.strip()
        questions = tuple(
            question.strip()
            for question in request.clarification_questions
            if question.strip()
        )
        if not task_text:
            questions = ("What task should CLIVERSE plan?", *questions)
            return PlanningResult(None, questions, (), ())
        if questions:
            return PlanningResult(None, questions, (), ())

        draft = StructuredTask(
            role=request.role.strip() or "AI coding assistant",
            context=request.context.strip(),
            task=task_text,
            requirements=tuple(value.strip() for value in request.requirements if value.strip()),
            constraints=tuple(value.strip() for value in request.constraints if value.strip()),
            output=request.output.strip() or "Implement the task and report verification.",
        )

        if self._memory_provider is None:
            if not self._allow_context_free:
                raise MemoryProviderUnavailable(
                    "No Member 2 memory/rules provider is configured."
                )
            context_bundle = ContextBundle.empty(
                "Context-free mode explicitly selected; no RAG context or rules were retrieved."
            )
            rules: list[Rule] = []
        else:
            context_bundle = self._memory_provider.retrieve_context(draft)
            rules = self._memory_provider.get_applicable_rules(draft)
            if not isinstance(context_bundle, ContextBundle):
                raise PlanningError("Memory provider returned an invalid context bundle.")
            if not context_bundle.provenance:
                raise PlanningError("Memory provider omitted context provenance.")
            if not isinstance(rules, list) or any(not isinstance(rule, Rule) for rule in rules):
                raise PlanningError("Memory provider returned invalid applicable rules.")

        retrieved_context = tuple(
            f"[{item.source}#{item.item_id}] {item.content}"
            for item in context_bundle.items
        )
        context_parts = tuple(
            item for item in (draft.context, *retrieved_context) if item.strip()
        )
        constraints = (
            *draft.constraints,
            *(
                f"Project rule [{rule.rule_id}; scope={rule.scope}; source={rule.source}]: "
                f"{rule.content}"
                for rule in rules
            ),
        )
        structured_task = StructuredTask(
            role=draft.role,
            context="\n\n".join(context_parts),
            task=draft.task,
            requirements=draft.requirements,
            constraints=constraints,
            output=draft.output,
        )

        provenance = tuple(context_bundle.provenance) + tuple(
            f"Retrieved from {item.source}#{item.item_id}" for item in context_bundle.items
        )
        if draft.context:
            provenance = ("User-supplied project context", *provenance)
        return PlanningResult(
            task=structured_task,
            clarification_questions=(),
            context_provenance=provenance,
            applicable_rule_ids=tuple(rule.rule_id for rule in rules),
        )
