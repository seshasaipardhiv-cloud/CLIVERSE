# Member 2 — Rules Intelligence Engine Specification & Documentation

**Subsystem:** CLIVERSE — Member 2 (RAG & Rules Intelligence)  
**Stage:** 4 (Rules Intelligence Engine)  
**Date:** 2026-10-08  
**Status:** Complete & Verified  

---

## 1. Overview & Purpose

The **Rules Intelligence Engine** is the deterministic guardrail and constraint evaluation subsystem of CLIVERSE. While the Memory/RAG subsystem answers *"What relevant project knowledge exists?"*, the Rules Engine answers:

1. **"What engineering and architectural rules apply to this task?"**
2. **"When applicable rules conflict, which rule wins, and why?"**

It ensures that AI CLIs operate under consistent developer and project guardrails, respecting mandatory corporate/security protections while allowing task-level overrides where permitted.

---

## 2. Rule Model & Schema

Every rule is represented by the [`Rule`](file:///A:/CLIVERSE/rules/models.py) Pydantic v2 model:

```python
class Rule(BaseModel):
    rule_id: str                      # Unique identifier slug (e.g. 'protect-prod-env')
    name: str                         # Human-readable title
    scope: RuleScope                  # GLOBAL | PROJECT | CLI | TASK
    scope_id: Optional[str] = None    # Identifier of project, CLI, or task
    description: str                  # Core constraint or instruction
    target: str = "general"           # Domain/domain property (e.g. 'database', 'git', 'packages')
    effect: RuleEffect                # ALLOW | DENY | WARN | ENFORCE | REQUIRE | ASK
    priority: int = 50                # Local priority score (0 to 99)
    is_mandatory: bool = False        # Fail-safe flag; cannot be overridden if True
    cli_filter: Optional[str] = None  # Specific CLI restriction (e.g. 'claude-cli', 'aider')
    project_id: Optional[str] = None  # Project isolation key
    enabled: bool = True              # Active status
    version: int = 1                  # Version counter (incremented on updates)
    conditions: List[RuleCondition]   # Granular path/task/command matching patterns
    created_at: str                   # ISO 8601 UTC timestamp
    updated_at: Optional[str] = None  # ISO 8601 UTC timestamp on mutation
    metadata: Dict[str, Any] = {}     # Freeform metadata for dashboard inspection
```

---

## 3. Canonical Rule Effects

The engine enforces canonical semantics across six effect tiers:

| Effect | Semantic Definition | Severity Rank |
|---|---|---|
| `DENY` | **Hard Prohibition:** The matching action or target is forbidden. | 6 (Highest) |
| `ASK` | **Interactive Confirmation:** Requires explicit human user approval before proceeding. | 5 |
| `REQUIRE` | **Prerequisite / Mandatory Instruction:** Prerequisite must be met (synonym for ENFORCE). | 4 |
| `ENFORCE` | **Mandatory Positive Constraint:** System must adopt this standard (e.g., 'Use TypeScript'). | 4 |
| `WARN` | **Advisory Notice:** Action is permitted, but an advisory warning is raised. | 2 |
| `ALLOW` | **Explicit Permission:** Permits matching action/condition. | 1 (Lowest) |

In conflict tie-breaking, more protective effects take precedence over more permissive ones (`DENY > ASK > REQUIRE/ENFORCE > WARN > ALLOW`).

---

## 4. Four-Level Scope Hierarchy

Rules are organized into four distinct scopes with fixed weights:

$$\text{TASK (Weight 400, Specificity 4)} \succ \text{CLI (Weight 300, Specificity 3)} \succ \text{PROJECT (Weight 200, Specificity 2)} \succ \text{GLOBAL (Weight 100, Specificity 1)}$$

- **`GLOBAL` (Weight 100):** System-wide conventions (e.g., "Never expose secrets"). Stored in `.envcore/rules/global/`.
- **`PROJECT` (Weight 200):** Repository standards (e.g., "Use PostgreSQL"). Stored in `.cliverse/rules/`.
- **`CLI` (Weight 300):** CLI adapter-specific instructions (e.g., "Ask before installing packages with claude-cli").
- **`TASK` (Weight 400):** Ephemeral instructions attached to a specific invocation or task.

### Effective Priority Calculation:
$$\text{effective\_priority} = \text{scope.weight} + \text{priority (0--99)}$$
- Task rule: $400 + 50 = 450$
- CLI rule: $300 + 50 = 350$
- Project rule: $200 + 50 = 250$
- Global rule: $100 + 50 = 150$

---

## 5. Applicability Evaluation

The [`RuleApplicabilityChecker`](file:///A:/CLIVERSE/rules/applicability.py) matches rules against invocation context:

1. **Enabled Gate:** If `rule.enabled is False`, rule is skipped.
2. **Project Isolation:**
   - If `scope == PROJECT`, `rule.project_id` must match the active `project_id`. A Project Alpha rule **never** matches Project Beta.
3. **CLI Filter:**
   - If `rule.cli_filter` is specified, it must match the active CLI name (case-insensitive).
4. **Conditions Evaluation:**
   - Evaluates each [`RuleCondition`](file:///A:/CLIVERSE/rules/models.py). Supported operators:
     - `contains`: Substring match.
     - `equals`: Exact match.
     - `starts_with`: Prefix match.
     - `regex`: Regular expression pattern matching.
     - `glob`: Unix glob pattern matching (e.g., `config/production/**`).
     - `in`: Value presence in target string or list.
   - If all conditions match, rule is marked applicable.

---

## 6. Mandatory Guardrails (Fail-Safe Protection)

Normal scope precedence dictates that higher-scope rules override lower-scope rules ($\text{TASK} \succ \text{PROJECT} \succ \text{GLOBAL}$).

**Exception — Mandatory Protection Override:**
If a lower-scope rule (e.g. `GLOBAL` or `PROJECT`) has `is_mandatory=True` and `effect in (DENY, REQUIRE, ENFORCE)`:
- A higher-scope rule (e.g. `CLI` or `TASK`) with an opposing effect (such as `ALLOW`) **CANNOT** override it.
- The mandatory protection rule **always wins**.
- Reason recorded:
  ```
  "Mandatory GLOBAL rule 'global-no-secrets' (DENY) cannot be overridden by TASK rule 'task-print-env'."
  ```

---

## 7. Conflict Detection Algorithm

1. **Target Domain Partitioning:**
   Rules are grouped by `rule.target` (e.g. `database`, `security`, `git`, `production_config`).
   **Rules with different targets never conflict.** For example:
   - Rule A: `target="database"`, `Use PostgreSQL`
   - Rule B: `target="language"`, `Use TypeScript`
   These rules do not conflict and both remain active.

2. **Contradiction Criteria within the Same Target:**
   Two rules contradict if:
   - Opposing effects: `ALLOW` vs `DENY`, `WARN` vs `DENY`, `ALLOW` vs `ENFORCE/REQUIRE`, `DENY` vs `ENFORCE/REQUIRE`.
   - Incompatible instructions: Two `ENFORCE` / `REQUIRE` rules on the same target with different instructions (e.g., `target="database"`, Rule A: "Use PostgreSQL" vs Rule B: "Use MongoDB").

---

## 8. Deterministic Resolution Algorithm

For any conflicting set of rules targeting the same domain:

1. **Check for Mandatory Rule:** If a mandatory protection rule exists against non-mandatory overrides, the mandatory rule wins.
2. **Precedence Ranking Key:** If no mandatory rule dictates the outcome, sort candidates descending by:
   - `is_mandatory` (1 vs 0)
   - `scope.weight` (TASK 400 > CLI 300 > PROJECT 200 > GLOBAL 100)
   - `priority` (99 down to 0)
   - `effect.severity_rank` (DENY 6 > ASK 5 > REQUIRE 4 > WARN 2 > ALLOW 1)
   - Lexical tie-breaker on `rule_id` (deterministic string comparison)
3. The top candidate **wins**.
4. Contradictory candidates are **suppressed** and recorded as [`RuleConflict`](file:///A:/CLIVERSE/rules/models.py) entries with human-readable reasons.

---

## 9. Outputs & Trace Generation

The [`RuleResolver`](file:///A:/CLIVERSE/rules/resolver.py) produces a [`RuleResolution`](file:///A:/CLIVERSE/rules/models.py) object containing:

1. `winning_rules`: Final active rules.
2. `suppressed_rules`: Rules overridden by higher-precedence or mandatory rules.
3. `conflicts`: Detected conflicts with winning and suppressed rule IDs.
4. `explanation_trace`: Human-readable Markdown report explaining every decision.
5. `constraints_prompt_text`: Formatted prompt block ready for Laya injection.

### Sample Constraints Prompt Block:
```markdown
### Applicable Rules

[MANDATORY]
- Never expose secrets or API keys.
- Production configuration files must not be altered.

[PROJECT]
- Use PostgreSQL for application data persistence.

[CLI]
- Ask user confirmation before installing packages.

[TASK]
- Use MongoDB for this specific analytics feature.

[RESOLUTION]
- Higher-scope TASK rule 'task-mongo' (effective priority 450) overrides PROJECT rule 'proj-pg' (effective priority 250).
```

---

## 10. Persistent Storage Design

Rules are stored as human-readable, version-controlled YAML files:

- **Project Rules:** Stored in `.cliverse/rules/{rule_id}.yaml`. Git-friendly and committed alongside project code.
- **Global Rules:** Stored in `.envcore/rules/global/{rule_id}.yaml`. Workstation-wide runtime rules.

### Storage Operations:
- `create_rule(rule: Rule) -> Rule`
- `get_rule(rule_id: str) -> Optional[Rule]`
- `update_rule(rule: Rule) -> Rule` (increments `version`, updates timestamp)
- `delete_rule(rule_id: str) -> bool`
- `list_rules(scope, project_id) -> List[Rule]`
- `find_candidate_rules(project_id, cli_name) -> List[Rule]`

---

## 11. Public API Usage

```python
from rules.engine import RulesEngine
from rules.models import Rule, RuleScope, RuleEffect

# Initialize engine
engine = RulesEngine()

# 1. Create a project rule
engine.create_rule(
    Rule(
        rule_id="proj-db-postgres",
        name="PostgreSQL Standard",
        scope=RuleScope.PROJECT,
        project_id="my-service",
        target="database",
        effect=RuleEffect.ENFORCE,
        priority=60,
        description="All persistent models must use PostgreSQL.",
    )
)

# 2. Get applicable rules for a task
applicable = engine.get_applicable_rules(
    task="Create user account table",
    project_id="my-service",
    cli_name="claude-cli",
)

# 3. Resolve conflicts and get prompt constraints
resolution = engine.resolve_rules(
    task="Create user account table",
    project_id="my-service",
    cli_name="claude-cli",
)

print(resolution.constraints_prompt_text)
print(resolution.explanation_trace)
```

---

## 12. Known Limitations & Future Enhancements

1. **Multi-condition logic:** Currently conditions in a rule are combined via logical `AND`. Future enhancement: allow explicit `OR` groups.
2. **Dynamic target discovery:** Target strings are currently normalized text identifiers (e.g., `database`, `security`). Future enhancement: hierarchical targets (e.g. `tech_stack:database:orm`).
3. **No automatic rule generation:** Rules are authored by developers or loaded from configuration; rule synthesis via LLM is intentionally out of scope for Stage 4.
