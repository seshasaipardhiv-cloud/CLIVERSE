"""Adapter for an explicitly configured instance of the public Laya Router API."""

from collections.abc import Mapping
from typing import Any, Protocol

from .errors import CliverseError


class LayaAdapterError(CliverseError):
    code = "LAYA_ADAPTER_ERROR"
    suggestion = "Check the configured Laya router and its typed question schema."


class LayaRouter(Protocol):
    def predict(
        self,
        state: Any,
        questions: Mapping[str, Any],
        **kwargs: Any,
    ) -> Mapping[str, Any]: ...


class LayaDecisionAdapter:
    """Adapt an injected Laya router without creating it or downloading weights."""

    def __init__(self, router: LayaRouter | None) -> None:
        if router is None:
            raise LayaAdapterError(
                "No local Laya Router is configured; inference is disabled."
            )
        self._router = router

    def predict(
        self,
        state: Any,
        questions: Mapping[str, Any],
        **kwargs: Any,
    ) -> Mapping[str, Any]:
        result = self._router.predict(state, questions, **kwargs)
        if not isinstance(result, Mapping):
            raise LayaAdapterError("Laya returned a non-mapping response.")
        answers = result.get("answers")
        if not isinstance(answers, Mapping):
            raise LayaAdapterError("Laya response is missing its typed 'answers' mapping.")
        return result
