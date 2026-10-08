# Member Integration Contracts

**Status:** proposed by Member 1; Member 2 and Member 4 confirmation is pending.
These contracts are implemented as Python protocols in
[`src/cliverse/contracts.py`](../src/cliverse/contracts.py). No other member's
implementation is imported directly.

## Member 2 — memory and rules

```python
retrieve_context(task: StructuredTask) -> ContextBundle
get_applicable_rules(task: StructuredTask) -> list[Rule]
store_memory(data: dict[str, object]) -> MemoryRef
search_memory(query: str) -> list[MemoryHit]
```

`ContextBundle` includes retrieval provenance and timestamp. An empty bundle
must explain why it is empty; provider failures must be raised, not converted
to empty context. `Rule` contains a stable ID, scope, priority and source.

## Member 4 — authorization

```python
authorize(request: AuthorizationRequest) -> AuthorizationDecision
```

The request identifies the agent, operation, project root, affected paths and
an executable plus argument vector. The result is `ALLOW`, `WARN` or `BLOCK`
with a reason. Member 1 requires explicit user confirmation for `WARN`; an
unknown decision, provider exception or missing authorizer cannot authorize
execution.

## Laya — typed decisions

`LayaDecisionAdapter` accepts an already configured object implementing
Laya's public `Router.predict(state, questions)` method. CLIVERSE does not
construct the router: Laya may fetch checkpoint weights on first use, and
neither the model nor its local availability is verified. Prompt generation
and the `ROLE/CONTEXT/TASK/REQUIREMENTS/CONSTRAINTS/OUTPUT` structure remain
separate CLIVERSE responsibilities.

## Current integration gate

The pre-existing Member 4 code remains untouched. The baseline inspection in
[`repository-baseline.md`](repository-baseline.md) found that its REST API has
no authentication and the default TrustGate is permissive. Members 1 and 4
must agree on an authenticated, scoped integration before real external CLI
execution is enabled.

The current guarded process API is library-only and requires an injected
authorizer. The CLI does not expose an external execution command while the
Member 4 integration gate remains unresolved.
