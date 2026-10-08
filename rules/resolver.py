"""
Deterministic Rule Resolution Engine — Member 2 (RAG + Rules)

Performs deterministic conflict detection, multi-tier precedence evaluation,
mandatory guardrail enforcement, and explainable decision tracing.
"""

from typing import Dict, List, Optional, Set, Tuple
from .models import ApplicableRule, Rule, RuleConflict, RuleEffect, RuleResolution, RuleScope


class RuleResolver:
    """
    Resolves conflicting rules deterministically according to:
      1. Mandatory Safety Guardrails (mandatory lower-scope rules cannot be overridden)
      2. Scope Precedence: TASK (400) > CLI (300) > PROJECT (200) > GLOBAL (100)
      3. Local Rule Priority: 0 to 99
      4. Effect Safety Ordering: DENY > ASK > REQUIRE/ENFORCE > WARN > ALLOW
      5. Lexical Rule ID Tie-Breaking
    """

    @classmethod
    def resolve(
        cls,
        task: str,
        applicable_rules: List[Rule],
        metadata: Optional[Dict[str, any]] = None,
    ) -> RuleResolution:
        """
        Takes a list of applicable rules and produces a deterministic RuleResolution.
        """
        if not applicable_rules:
            return RuleResolution(
                task=task,
                applicable_rules=[],
                conflicts=[],
                winning_rules=[],
                suppressed_rules=[],
                explanation_trace="No rules apply to this task.",
                constraints_prompt_text="",
                metadata=metadata or {},
            )

        # 1. Group rules by target domain
        target_groups: Dict[str, List[Rule]] = {}
        for r in applicable_rules:
            t = r.target.strip().lower()
            target_groups.setdefault(t, []).append(r)

        all_winning_rules: List[Rule] = []
        all_suppressed_rules: List[Rule] = []
        all_conflicts: List[RuleConflict] = []
        resolution_notes: List[str] = []

        # 2. Resolve each target domain independently
        # Sort targets alphabetically for deterministic evaluation order
        for target in sorted(target_groups.keys()):
            rules_in_target = target_groups[target]

            if len(rules_in_target) == 1:
                # No conflict possible with single rule in target
                all_winning_rules.append(rules_in_target[0])
                continue

            winners, suppressed, conflicts, notes = cls._resolve_target_group(target, rules_in_target)
            all_winning_rules.extend(winners)
            all_suppressed_rules.extend(suppressed)
            all_conflicts.extend(conflicts)
            resolution_notes.extend(notes)

        # 3. Sort winning rules deterministically by effective priority descending, then name
        all_winning_rules.sort(
            key=lambda r: (1 if r.is_mandatory else 0, r.effective_priority, -r.effect.severity_rank, r.rule_id),
            reverse=True,
        )

        # 4. Generate human-readable explanation trace
        trace = cls._build_explanation_trace(
            task=task,
            applicable_rules=applicable_rules,
            winning_rules=all_winning_rules,
            suppressed_rules=all_suppressed_rules,
            conflicts=all_conflicts,
            resolution_notes=resolution_notes,
        )

        # 5. Generate constraints prompt text for Member 1 / Laya
        prompt_text = cls._build_constraints_prompt(
            winning_rules=all_winning_rules,
            conflicts=all_conflicts,
        )

        return RuleResolution(
            task=task,
            applicable_rules=applicable_rules,
            conflicts=all_conflicts,
            winning_rules=all_winning_rules,
            suppressed_rules=all_suppressed_rules,
            explanation_trace=trace,
            constraints_prompt_text=prompt_text,
            metadata=metadata or {},
        )

    @classmethod
    def _resolve_target_group(
        cls,
        target: str,
        rules: List[Rule],
    ) -> Tuple[List[Rule], List[Rule], List[RuleConflict], List[str]]:
        """
        Detects conflicts and determines winning rules within a single target domain.
        """
        # Detect if any pair of rules contradicts
        has_conflict = False
        for i in range(len(rules)):
            for j in range(i + 1, len(rules)):
                if cls._rules_contradict(rules[i], rules[j]):
                    has_conflict = True
                    break
            if has_conflict:
                break

        if not has_conflict:
            # All rules in this target are compatible
            return list(rules), [], [], []

        # Contradictions detected: Determine the single winning rule for this target
        # Sort candidates using the deterministic precedence key
        ranked_rules = sorted(rules, key=cls._rule_precedence_key, reverse=True)
        winner = ranked_rules[0]

        suppressed: List[Rule] = []
        conflicts: List[RuleConflict] = []
        notes: List[str] = []

        for candidate in ranked_rules[1:]:
            if cls._rules_contradict(winner, candidate):
                reason = cls._generate_conflict_reason(winner, candidate)
                suppressed.append(candidate)
                conflicts.append(
                    RuleConflict(
                        winning_rule_id=winner.rule_id,
                        suppressed_rule_id=candidate.rule_id,
                        target=target,
                        reason=reason,
                    )
                )
                notes.append(f"Target '{target}': {winner.rule_id} won over {candidate.rule_id} ({reason})")
            else:
                # Rule is compatible with winner
                pass

        # All compatible rules (including winner) remain active
        compatible_winners = [r for r in rules if r not in suppressed]
        return compatible_winners, suppressed, conflicts, notes

    @classmethod
    def _rules_contradict(cls, r1: Rule, r2: Rule) -> bool:
        """
        Determines whether two rules targeting the same domain contradict each other.
        """
        # Opposing effects always contradict:
        # ALLOW vs DENY
        if (r1.effect == RuleEffect.ALLOW and r2.effect == RuleEffect.DENY) or \
           (r1.effect == RuleEffect.DENY and r2.effect == RuleEffect.ALLOW):
            return True

        # WARN vs DENY
        if (r1.effect == RuleEffect.WARN and r2.effect == RuleEffect.DENY) or \
           (r1.effect == RuleEffect.DENY and r2.effect == RuleEffect.WARN):
            return True

        # ENFORCE/REQUIRE vs DENY
        if (r1.effect in (RuleEffect.ENFORCE, RuleEffect.REQUIRE) and r2.effect == RuleEffect.DENY) or \
           (r1.effect == RuleEffect.DENY and r2.effect in (RuleEffect.ENFORCE, RuleEffect.REQUIRE)):
            return True

        # ALLOW vs ENFORCE/REQUIRE
        if (r1.effect == RuleEffect.ALLOW and r2.effect in (RuleEffect.ENFORCE, RuleEffect.REQUIRE)) or \
           (r1.effect in (RuleEffect.ENFORCE, RuleEffect.REQUIRE) and r2.effect == RuleEffect.ALLOW):
            return True

        # Two ENFORCE / REQUIRE rules on the same target with different instructions
        if r1.effect in (RuleEffect.ENFORCE, RuleEffect.REQUIRE) and \
           r2.effect in (RuleEffect.ENFORCE, RuleEffect.REQUIRE):
            desc1 = r1.description.strip().lower()
            desc2 = r2.description.strip().lower()
            name1 = r1.name.strip().lower()
            name2 = r2.name.strip().lower()
            if desc1 != desc2 and name1 != name2:
                return True

        return False

    @classmethod
    def _rule_precedence_key(cls, rule: Rule) -> Tuple:
        """
        Deterministic ordering key for conflict resolution.
        Higher value wins.

        Components:
          1. is_mandatory: 1 for True, 0 for False (mandatory protection takes absolute precedence)
          2. scope weight: TASK(400) > CLI(300) > PROJECT(200) > GLOBAL(100)
          3. priority: 0 to 99
          4. effect safety: DENY(6) > ASK(5) > REQUIRE/ENFORCE(4) > WARN(2) > ALLOW(1)
          5. lexical tie-break: negative rule_id for deterministic descending order
        """
        return (
            1 if rule.is_mandatory else 0,
            rule.scope.weight,
            rule.priority,
            rule.effect.severity_rank,
            # String inverse ordering for deterministic tie-breaker
            [-ord(c) for c in rule.rule_id],
        )

    @classmethod
    def _generate_conflict_reason(cls, winner: Rule, loser: Rule) -> str:
        """
        Generates an explainable reason for why winner beat loser.
        """
        # Mandatory override
        if winner.is_mandatory and not loser.is_mandatory:
            return (
                f"Mandatory {winner.scope.value} rule '{winner.rule_id}' ({winner.effect.value}) "
                f"cannot be overridden by {loser.scope.value} rule '{loser.rule_id}'."
            )

        # Scope precedence
        if winner.scope.weight > loser.scope.weight:
            return (
                f"Higher-scope {winner.scope.value} rule '{winner.rule_id}' "
                f"(effective priority {winner.effective_priority}) overrides "
                f"{loser.scope.value} rule '{loser.rule_id}' (effective priority {loser.effective_priority})."
            )

        # Priority difference within same scope
        if winner.scope == loser.scope and winner.priority > loser.priority:
            return (
                f"Rule '{winner.rule_id}' has higher priority ({winner.priority} vs {loser.priority}) "
                f"within {winner.scope.value} scope."
            )

        # Effect safety tie-breaker
        if winner.effect.severity_rank > loser.effect.severity_rank:
            return (
                f"Rule '{winner.rule_id}' takes precedence due to safety ordering "
                f"({winner.effect.value} is more protective than {loser.effect.value}) at equal priority."
            )

        # Lexical tie-breaker
        return f"Deterministic tie-breaker: rule '{winner.rule_id}' precedes '{loser.rule_id}' lexically."

    @classmethod
    def _build_explanation_trace(
        cls,
        task: str,
        applicable_rules: List[Rule],
        winning_rules: List[Rule],
        suppressed_rules: List[Rule],
        conflicts: List[RuleConflict],
        resolution_notes: List[str],
    ) -> str:
        """Builds comprehensive markdown explanation trace for Laya and Dashboard."""
        lines: List[str] = [
            "# Rule Resolution Trace",
            f"**Task:** {task}",
            f"**Applicable Rules Count:** {len(applicable_rules)}",
            f"**Winning Active Rules:** {len(winning_rules)}",
            f"**Suppressed Rules:** {len(suppressed_rules)}",
            f"**Detected Conflicts:** {len(conflicts)}",
            "",
        ]

        if conflicts:
            lines.append("## Detected Conflicts & Resolutions")
            for c in conflicts:
                lines.append(f"- **Target Domain:** `{c.target}`")
                lines.append(f"  - **Winning Rule:** `{c.winning_rule_id}`")
                lines.append(f"  - **Suppressed Rule:** `{c.suppressed_rule_id}`")
                lines.append(f"  - **Decision Reason:** {c.reason}")
            lines.append("")

        lines.append("## Active Winning Rules")
        if winning_rules:
            for r in winning_rules:
                mand_tag = " [MANDATORY]" if r.is_mandatory else ""
                lines.append(
                    f"- **[{r.scope.value}]{mand_tag} {r.name}** (`{r.rule_id}`)"
                )
                lines.append(
                    f"  - Effect: `{r.effect.value}`, Target: `{r.target}`, Priority: {r.priority} (Effective: {r.effective_priority})"
                )
                lines.append(f"  - Instruction: {r.description}")
        else:
            lines.append("*(None)*")
        lines.append("")

        if suppressed_rules:
            lines.append("## Suppressed Rules")
            for r in suppressed_rules:
                lines.append(f"- **[{r.scope.value}] {r.name}** (`{r.rule_id}`): {r.description}")
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def _build_constraints_prompt(
        cls,
        winning_rules: List[Rule],
        conflicts: List[RuleConflict],
    ) -> str:
        """
        Builds the structured constraints block to be injected directly
        into prompt planning by Member 1 / Laya.
        """
        if not winning_rules:
            return ""

        mandatory_rules = [r for r in winning_rules if r.is_mandatory]
        project_rules = [r for r in winning_rules if not r.is_mandatory and r.scope == RuleScope.PROJECT]
        cli_rules = [r for r in winning_rules if not r.is_mandatory and r.scope == RuleScope.CLI]
        task_rules = [r for r in winning_rules if not r.is_mandatory and r.scope == RuleScope.TASK]
        global_rules = [r for r in winning_rules if not r.is_mandatory and r.scope == RuleScope.GLOBAL]
        require_rules = [r for r in winning_rules if r.effect in (RuleEffect.REQUIRE, RuleEffect.ENFORCE)]

        lines: List[str] = ["### Applicable Rules", ""]

        if mandatory_rules:
            lines.append("[MANDATORY]")
            for r in mandatory_rules:
                lines.append(f"- {r.description}")
            lines.append("")

        if require_rules:
            lines.append("[REQUIRE]")
            for r in require_rules:
                lines.append(f"- {r.description}")
            lines.append("")

        if global_rules:
            lines.append("[GLOBAL]")
            for r in global_rules:
                lines.append(f"- {r.description}")
            lines.append("")

        if project_rules:
            lines.append("[PROJECT]")
            for r in project_rules:
                lines.append(f"- {r.description}")
            lines.append("")

        if cli_rules:
            lines.append("[CLI]")
            for r in cli_rules:
                lines.append(f"- {r.description}")
            lines.append("")

        if task_rules:
            lines.append("[TASK]")
            for r in task_rules:
                lines.append(f"- {r.description}")
            lines.append("")

        if conflicts:
            lines.append("[RESOLUTION]")
            for c in conflicts:
                lines.append(f"- {c.reason}")
            lines.append("")

        return "\n".join(lines).strip()
