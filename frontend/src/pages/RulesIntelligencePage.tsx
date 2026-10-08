import React, { useState, useEffect } from "react";
import { useApp } from "../context/AppContext";
import { Card } from "../components/Card";
import { StatusBadge } from "../components/StatusBadge";
import { Modal } from "../components/Modal";
import { rulesApi } from "../api/rules";
import type { CreateRulePayload } from "../api/rules";
import type { RuleItem, RuleResolutionResponse, RuleScopeType, RuleEffectType } from "../types";
import {
  Layers,
  Plus,
  Trash2,
  Search,
  Sparkles,
} from "lucide-react";

export const RulesIntelligencePage: React.FC = () => {
  const { currentProject, currentCli, showToast } = useApp();
  const [rules, setRules] = useState<RuleItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [scopeFilter, setScopeFilter] = useState<string>("");
  const [effectFilter, setEffectFilter] = useState<string>("");

  // Create Modal state
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [ruleId, setRuleId] = useState("");
  const [ruleName, setRuleName] = useState("");
  const [ruleDesc, setRuleDesc] = useState("");
  const [ruleScope, setRuleScope] = useState<RuleScopeType>("project");
  const [rulePriority, setRulePriority] = useState<number>(50);
  const [ruleEffect, setRuleEffect] = useState<RuleEffectType>("require");
  const [ruleTarget, setRuleTarget] = useState("");
  const [isMandatory, setIsMandatory] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Simulator state
  const [simTask, setSimTask] = useState("Run database migration without testing");
  const [isSimulating, setIsSimulating] = useState(false);
  const [simResult, setSimResult] = useState<RuleResolutionResponse | null>(null);

  const fetchRules = async () => {
    setIsLoading(true);
    try {
      const res = await rulesApi.list(undefined, currentProject);
      setRules(res.rules);
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Failed to Fetch Rules",
        message: err instanceof Error ? err.message : "Error listing rules",
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchRules();
  }, [currentProject]);

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ruleId.trim() || !ruleName.trim()) return;

    setIsSubmitting(true);
    try {
      const payload: CreateRulePayload = {
        rule_id: ruleId.trim(),
        name: ruleName.trim(),
        description: ruleDesc.trim(),
        scope: ruleScope,
        priority: Number(rulePriority),
        effect: ruleEffect,
        target: ruleTarget.trim() || undefined,
        is_mandatory: isMandatory,
        project_id: ruleScope === "project" ? currentProject : null,
        cli_name: ruleScope === "cli" ? currentCli : null,
      };

      await rulesApi.create(payload);
      showToast({
        type: "success",
        title: "Rule Created",
        message: `Saved rule [${ruleEffect.toUpperCase()}] ${ruleName}`,
      });

      setCreateModalOpen(false);
      setRuleId("");
      setRuleName("");
      setRuleDesc("");
      fetchRules();
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Creation Failed",
        message: err instanceof Error ? err.message : "Error creating rule",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteRule = async (id: string) => {
    if (!confirm(`Are you sure you want to delete rule '${id}'?`)) return;

    try {
      await rulesApi.delete(id);
      showToast({
        type: "success",
        title: "Rule Deleted",
        message: `Rule ${id} removed from RuleStore`,
      });
      fetchRules();
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Deletion Failed",
        message: err instanceof Error ? err.message : "Error deleting rule",
      });
    }
  };

  const handleSimulate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!simTask.trim()) return;

    setIsSimulating(true);
    setSimResult(null);
    try {
      const res = await rulesApi.resolve({
        task: simTask.trim(),
        project_id: currentProject,
        cli_name: currentCli,
      });
      setSimResult(res);
      showToast({
        type: res.winning_decision === "DENY" ? "warn" : "info",
        title: "Resolution Complete",
        message: `Winning Decision: ${res.winning_decision}`,
      });
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Simulation Failed",
        message: err instanceof Error ? err.message : "Error resolving rules",
      });
    } finally {
      setIsSimulating(false);
    }
  };

  const filteredRules = rules.filter((r) => {
    if (scopeFilter && r.scope.toLowerCase() !== scopeFilter.toLowerCase()) return false;
    if (effectFilter && r.effect.toLowerCase() !== effectFilter.toLowerCase()) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        r.name.toLowerCase().includes(q) ||
        r.rule_id.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        (r.target && r.target.toLowerCase().includes(q))
      );
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#1b253b] pb-5">
        <div>
          <div className="flex items-center gap-2">
            <Layers className="w-6 h-6 text-emerald-400" />
            <h1 className="text-xl font-bold tracking-tight text-slate-100">
              Rules Intelligence & Conflict Resolution Center
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Hierarchical constraint governance across Global, Project, CLI, and Task scopes
          </p>
        </div>

        <button
          onClick={() => setCreateModalOpen(true)}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-xs rounded-xl flex items-center gap-2 shadow-[0_0_15px_rgba(16,185,129,0.3)] transition-all"
        >
          <Plus className="w-4 h-4" />
          <span>Create Engineering Rule</span>
        </button>
      </div>

      {/* ── Hierarchy & Priority Reference ──────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Scope Precedence Hierarchy" subtitle="Effective priority = Scope weight + Rule priority (0-99)">
          <div className="grid grid-cols-4 gap-2 text-center text-xs font-mono">
            <div className="p-2.5 rounded-lg bg-[#0d1e16] border border-emerald-500/40">
              <span className="text-[10px] text-slate-500 block">WEIGHT: 400</span>
              <span className="font-bold text-emerald-300">TASK</span>
            </div>
            <div className="p-2.5 rounded-lg bg-[#0d1e16] border border-emerald-500/30">
              <span className="text-[10px] text-slate-500 block">WEIGHT: 300</span>
              <span className="font-bold text-emerald-400">CLI</span>
            </div>
            <div className="p-2.5 rounded-lg bg-[#0d1e16] border border-emerald-500/20">
              <span className="text-[10px] text-slate-500 block">WEIGHT: 200</span>
              <span className="font-bold text-emerald-500">PROJECT</span>
            </div>
            <div className="p-2.5 rounded-lg bg-[#0a101d] border border-slate-800">
              <span className="text-[10px] text-slate-500 block">WEIGHT: 100</span>
              <span className="font-bold text-slate-400">GLOBAL</span>
            </div>
          </div>
        </Card>

        <Card title="Severity Tie-Breaking Matrix" subtitle="Applied when effective priorities are tied">
          <div className="grid grid-cols-5 gap-1.5 text-center text-[11px] font-mono">
            <div className="p-2 rounded bg-red-950/60 border border-red-500/40 text-red-300 font-bold">
              DENY (6)
            </div>
            <div className="p-2 rounded bg-amber-950/50 border border-amber-500/40 text-amber-300 font-bold">
              ASK (5)
            </div>
            <div className="p-2 rounded bg-rose-950/50 border border-rose-500/40 text-rose-300 font-bold">
              REQUIRE (4)
            </div>
            <div className="p-2 rounded bg-amber-950/30 border border-amber-500/30 text-amber-400 font-bold">
              WARN (2)
            </div>
            <div className="p-2 rounded bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 font-bold">
              ALLOW (1)
            </div>
          </div>
        </Card>
      </div>

      {/* ── Interactive Resolution Simulator ────────────────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-emerald-400" />
            <span>Interactive Rule Conflict Resolution Simulator</span>
          </div>
        }
        subtitle="Test task prompts against active rules to inspect resolution explanations"
      >
        <form onSubmit={handleSimulate} className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="text"
              value={simTask}
              onChange={(e) => setSimTask(e.target.value)}
              placeholder="Enter a task to test rule applicability..."
              className="flex-1 bg-[#0a0f1d] border border-[#22304d] rounded-xl px-4 py-2.5 text-xs text-slate-100 placeholder-slate-500 font-mono focus:outline-none focus:border-emerald-500"
            />
            <button
              type="submit"
              disabled={isSimulating || !simTask.trim()}
              className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-xs rounded-xl flex items-center justify-center gap-2 shadow-[0_0_15px_rgba(16,185,129,0.3)] disabled:opacity-50"
            >
              <span>{isSimulating ? "Simulating..." : "Simulate Resolution"}</span>
            </button>
          </div>
        </form>

        {simResult && (
          <div className="mt-4 pt-4 border-t border-[#1a253c] space-y-3 animate-in fade-in duration-200">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-mono">WINNING DECISION:</span>
                <StatusBadge status={simResult.winning_decision} size="md" />
              </div>
              <span className="text-xs font-mono text-slate-500">
                {simResult.applicable_rules.length} matched / {simResult.winning_rules.length} won
              </span>
            </div>

            {simResult.explanation_trace.length > 0 && (
              <div className="p-3 bg-[#080d19] border border-[#18233a] rounded-lg">
                <span className="text-[10px] font-mono uppercase text-slate-500 block mb-1">
                  EXPLANATION TRACE
                </span>
                <ul className="text-xs font-mono text-slate-300 space-y-1 list-disc list-inside">
                  {simResult.explanation_trace.map((step, idx) => (
                    <li key={idx}>{step}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* ── Active Rules Management ─────────────────────────────────────── */}
      <div className="space-y-4">
        {/* Filters */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="relative flex-1 w-full">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter rules by name, ID, or target..."
              className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg pl-10 pr-4 py-2 text-xs font-mono text-slate-200 focus:outline-none"
            />
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto text-xs">
            <select
              value={scopeFilter}
              onChange={(e) => setScopeFilter(e.target.value)}
              className="bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-slate-300 font-mono focus:outline-none"
            >
              <option value="">All Scopes</option>
              <option value="global">GLOBAL</option>
              <option value="project">PROJECT</option>
              <option value="cli">CLI</option>
              <option value="task">TASK</option>
            </select>

            <select
              value={effectFilter}
              onChange={(e) => setEffectFilter(e.target.value)}
              className="bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-slate-300 font-mono focus:outline-none"
            >
              <option value="">All Effects</option>
              <option value="allow">ALLOW</option>
              <option value="warn">WARN</option>
              <option value="require">REQUIRE</option>
              <option value="ask">ASK</option>
              <option value="deny">DENY</option>
            </select>
          </div>
        </div>

        {/* Rule Cards Grid */}
        {isLoading ? (
          <div className="p-8 text-center text-slate-500 font-mono text-xs">
            Loading rules repository...
          </div>
        ) : filteredRules.length === 0 ? (
          <div className="p-8 text-center text-slate-500 font-mono text-xs border border-dashed border-[#1a253c] rounded-xl">
            No engineering rules found matching the criteria.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredRules.map((r) => (
              <Card key={r.rule_id} className="relative">
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={r.effect} size="sm" />
                    <h4 className="text-sm font-semibold text-slate-100">{r.name}</h4>
                  </div>

                  <button
                    onClick={() => handleDeleteRule(r.rule_id)}
                    className="p-1 rounded text-slate-500 hover:text-red-400 hover:bg-red-950/40 transition-colors"
                    title="Delete rule"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                <p className="text-xs text-slate-400 mb-3 leading-relaxed">{r.description}</p>

                <div className="pt-2 border-t border-[#18233a] flex flex-wrap items-center justify-between text-[11px] font-mono text-slate-500">
                  <span>
                    ID: <span className="text-slate-300">{r.rule_id}</span>
                  </span>
                  <span>
                    SCOPE: <span className="text-emerald-400 uppercase">{r.scope}</span>
                  </span>
                  <span>
                    PRIORITY: <span className="text-slate-300">{r.priority}</span>
                  </span>
                  {r.is_mandatory && (
                    <span className="px-1.5 py-0.5 rounded bg-red-950/60 text-red-300 border border-red-500/30">
                      MANDATORY
                    </span>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* ── Create Rule Modal ───────────────────────────────────────────── */}
      <Modal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title="Create Engineering Rule"
        subtitle="Adds a persistent constraint document to .envcore/rules or .cliverse/rules"
        maxWidth="xl"
      >
        <form onSubmit={handleCreateRule} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-mono text-slate-300 mb-1">Rule ID</label>
              <input
                type="text"
                value={ruleId}
                onChange={(e) => setRuleId(e.target.value)}
                placeholder="e.g., rule-require-tests"
                className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-mono text-slate-300 mb-1">Rule Name</label>
              <input
                type="text"
                value={ruleName}
                onChange={(e) => setRuleName(e.target.value)}
                placeholder="e.g., Automated Test Requirement"
                className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-mono text-slate-300 mb-1">Description / Constraint</label>
            <textarea
              rows={2}
              value={ruleDesc}
              onChange={(e) => setRuleDesc(e.target.value)}
              placeholder="State the engineering requirement clearly..."
              className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg p-3 text-xs font-mono text-slate-200 focus:outline-none"
              required
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-mono text-slate-300 mb-1">Scope</label>
              <select
                value={ruleScope}
                onChange={(e) => setRuleScope(e.target.value as RuleScopeType)}
                className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
              >
                <option value="project">PROJECT ({currentProject})</option>
                <option value="global">GLOBAL</option>
                <option value="cli">CLI ({currentCli})</option>
                <option value="task">TASK</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-mono text-slate-300 mb-1">Effect</label>
              <select
                value={ruleEffect}
                onChange={(e) => setRuleEffect(e.target.value as RuleEffectType)}
                className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
              >
                <option value="require">REQUIRE</option>
                <option value="allow">ALLOW</option>
                <option value="warn">WARN</option>
                <option value="ask">ASK</option>
                <option value="deny">DENY</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-mono text-slate-300 mb-1">Priority (0-99)</label>
              <input
                type="number"
                min={0}
                max={99}
                value={rulePriority}
                onChange={(e) => setRulePriority(Number(e.target.value))}
                className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-mono text-slate-300 mb-1">Target Keyword / Topic</label>
              <input
                type="text"
                value={ruleTarget}
                onChange={(e) => setRuleTarget(e.target.value)}
                placeholder="e.g. tests, database, git"
                className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
              />
            </div>

            <div className="flex items-center gap-2 mt-5">
              <input
                type="checkbox"
                id="isMandatoryCheck"
                checked={isMandatory}
                onChange={(e) => setIsMandatory(e.target.checked)}
                className="rounded accent-red-500 w-4 h-4 cursor-pointer"
              />
              <label htmlFor="isMandatoryCheck" className="text-xs font-mono text-slate-300 cursor-pointer">
                Mandatory Guardrail (Cannot be overridden)
              </label>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setCreateModalOpen(false)}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !ruleId.trim() || !ruleName.trim()}
              className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-bold transition-all shadow-[0_0_15px_rgba(16,185,129,0.3)] disabled:opacity-50"
            >
              {isSubmitting ? "Saving..." : "Save Rule Document"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
