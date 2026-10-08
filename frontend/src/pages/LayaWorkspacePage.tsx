import React, { useState } from "react";
import { useApp } from "../context/AppContext";
import { Card } from "../components/Card";
import { StatusBadge } from "../components/StatusBadge";
import { Modal } from "../components/Modal";
import { layaApi } from "../api/laya";
import { securityApi } from "../api/security";
import {
  Brain,
  Send,
  Database,
  Layers,
  ShieldCheck,
  Terminal,
  AlertTriangle,
  Sparkles,
  Code2,
  FileText,
} from "lucide-react";

export const LayaWorkspacePage: React.FC = () => {
  const { currentProject, currentCli, showToast } = useApp();
  const [taskText, setTaskText] = useState("Implement pre-commit tests and check database architecture conventions");
  const [role, setRole] = useState("AI coding assistant");
  const [targetCommand, setTargetCommand] = useState("pytest tests/test_memory_storage_models.py");
  const [minScore, setMinScore] = useState(0.35);
  const [topK, setTopK] = useState(5);
  const [contextBudget, setContextBudget] = useState(2000);

  const [isLoading, setIsLoading] = useState(false);
  const [executionResult, setExecutionResult] = useState<any>(null);
  const [intelligenceResult, setIntelligenceResult] = useState<any>(null);
  const [planResult, setPlanResult] = useState<any>(null);

  // Warning Confirmation Modal state
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const [confirmToken, setConfirmToken] = useState("");
  const [isConfirming, setIsConfirming] = useState(false);

  const handleRunFullPipeline = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!taskText.trim()) return;

    setIsLoading(true);
    setExecutionResult(null);
    setIntelligenceResult(null);
    setPlanResult(null);

    try {
      // 1. Fetch complete Laya Intelligence
      const intel = await layaApi.buildIntelligence({
        task: taskText.trim(),
        project_id: currentProject,
        cli_name: currentCli,
        top_k: topK,
        min_score: minScore,
        context_budget_tokens: contextBudget,
      });
      setIntelligenceResult(intel);

      // 2. Fetch Member 1 Planning Result
      const plan = await layaApi.planTask({
        task: taskText.trim(),
        role: role,
        project_id: currentProject,
        cli_name: currentCli,
      });
      setPlanResult(plan);

      // 3. Execute Complete Pipeline with TrustGate
      const exec = await layaApi.executePipeline({
        task: taskText.trim(),
        command: targetCommand.trim(),
        project_id: currentProject,
        cli_name: currentCli,
        user_confirmed: false,
      });
      setExecutionResult(exec);

      if (exec.pipeline.trustgate.requires_user_confirmation && exec.pipeline.trustgate.confirmation_token) {
        setConfirmToken(exec.pipeline.trustgate.confirmation_token);
        setConfirmModalOpen(true);
      }

      showToast({
        type: exec.pipeline.trustgate.allowed ? "success" : "warn",
        title: "Pipeline Processed",
        message: `Decision: ${exec.pipeline.rules.decision} | TrustGate: ${exec.pipeline.trustgate.decision}`,
      });
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Execution Error",
        message: err instanceof Error ? err.message : "Pipeline failed",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirmWarning = async () => {
    if (!confirmToken) return;
    setIsConfirming(true);
    try {
      await securityApi.confirmWarning(confirmToken);
      showToast({
        type: "success",
        title: "Warning Confirmed",
        message: `Operation authorized under explicit user approval`,
      });
      setConfirmModalOpen(false);

      // Re-run pipeline with user confirmation
      const exec = await layaApi.executePipeline({
        task: taskText.trim(),
        command: targetCommand.trim(),
        project_id: currentProject,
        cli_name: currentCli,
        user_confirmed: true,
      });
      setExecutionResult(exec);
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Confirmation Failed",
        message: err instanceof Error ? err.message : "Failed to confirm warning",
      });
    } finally {
      setIsConfirming(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* ── Page Header ─────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#1b253b] pb-5">
        <div>
          <div className="flex items-center gap-2">
            <Brain className="w-6 h-6 text-emerald-400" />
            <h1 className="text-xl font-bold tracking-tight text-slate-100">
              Laya Intent & Intelligence Workspace
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Central cognitive execution pipeline: Memory RAG &rarr; Rules Intelligence &rarr; Structured Planning &rarr; TrustGate Authorization
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono">
          <span className="px-2.5 py-1 rounded-md bg-[#0e1627] border border-slate-800 text-slate-300">
            Workspace: <span className="text-emerald-400 font-semibold">{currentProject}</span>
          </span>
          <span className="px-2.5 py-1 rounded-md bg-[#0e1627] border border-slate-800 text-slate-300">
            CLI: <span className="text-emerald-400 font-semibold">{currentCli}</span>
          </span>
        </div>
      </div>

      {/* ── Visual 5-Stage Transition Tracker ───────────────────────────── */}
      <div className="bg-[#0b101d] border border-[#1d273f] rounded-xl p-4 shadow-lg">
        <div className="text-[11px] font-mono uppercase tracking-wider text-slate-500 mb-3">
          CLIVERSE Cognitive & Security Pipeline
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-2 relative">
          {/* Stage 1 */}
          <div className="flex items-center gap-2 p-2.5 rounded-lg bg-[#0e1628] border border-[#1b263e]">
            <Database className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <div className="min-w-0">
              <span className="text-[10px] text-slate-500 font-mono block">1. RAG MEMORY</span>
              <span className="text-xs font-semibold text-slate-200">
                {executionResult ? executionResult.pipeline.memory.chunks_retrieved + " chunks" : "Standby"}
              </span>
            </div>
          </div>

          {/* Stage 2 */}
          <div className="flex items-center gap-2 p-2.5 rounded-lg bg-[#0e1628] border border-[#1b263e]">
            <Layers className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <div className="min-w-0">
              <span className="text-[10px] text-slate-500 font-mono block">2. RULES ENGINE</span>
              <span className="text-xs font-semibold text-slate-200">
                {executionResult ? executionResult.pipeline.rules.decision : "Standby"}
              </span>
            </div>
          </div>

          {/* Stage 3 */}
          <div className="flex items-center gap-2 p-2.5 rounded-lg bg-[#0e1628] border border-[#1b263e]">
            <Brain className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <div className="min-w-0">
              <span className="text-[10px] text-slate-500 font-mono block">3. LAYA PLANNER</span>
              <span className="text-xs font-semibold text-slate-200">
                {planResult ? (planResult.ready ? "Task Ready" : "Questions Pending") : "Standby"}
              </span>
            </div>
          </div>

          {/* Stage 4 */}
          <div className="flex items-center gap-2 p-2.5 rounded-lg bg-[#0e1628] border border-[#1b263e]">
            <ShieldCheck className="w-4 h-4 text-rose-400 flex-shrink-0" />
            <div className="min-w-0">
              <span className="text-[10px] text-slate-500 font-mono block">4. TRUSTGATE</span>
              <span className="text-xs font-semibold text-slate-200 truncate">
                {executionResult ? executionResult.pipeline.trustgate.decision : "Standby"}
              </span>
            </div>
          </div>

          {/* Stage 5 */}
          <div className="flex items-center gap-2 p-2.5 rounded-lg bg-[#0e1628] border border-[#1b263e]">
            <Terminal className="w-4 h-4 text-amber-400 flex-shrink-0" />
            <div className="min-w-0">
              <span className="text-[10px] text-slate-500 font-mono block">5. EXECUTION</span>
              <span className="text-xs font-semibold text-slate-200 truncate">
                {executionResult ? executionResult.pipeline.execution.status : "Standby"}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ── Main Input & Configuration Form ─────────────────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-emerald-400" />
            <span>Task Intent & Parameter Controls</span>
          </div>
        }
      >
        <form onSubmit={handleRunFullPipeline} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5 font-mono">
              USER TASK PROMPT
            </label>
            <textarea
              rows={3}
              value={taskText}
              onChange={(e) => setTaskText(e.target.value)}
              placeholder="Describe the engineering task for Laya to plan..."
              className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-xl p-3.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 font-mono"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5 font-mono">
                PLANNER ROLE
              </label>
              <input
                type="text"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs text-slate-100 font-mono focus:outline-none focus:border-emerald-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5 font-mono">
                TARGET COMMAND FOR TRUSTGATE EVALUATION
              </label>
              <input
                type="text"
                value={targetCommand}
                onChange={(e) => setTargetCommand(e.target.value)}
                placeholder="e.g. pytest tests/ or git commit"
                className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs text-slate-100 font-mono focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>

          {/* Tunable RAG Parameters */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2 border-t border-[#1a253c]">
            <div>
              <div className="flex justify-between text-xs font-mono text-slate-400 mb-1">
                <span>Top-K Chunks</span>
                <span className="text-emerald-400 font-bold">{topK}</span>
              </div>
              <input
                type="range"
                min={1}
                max={15}
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
                className="w-full accent-emerald-500"
              />
            </div>

            <div>
              <div className="flex justify-between text-xs font-mono text-slate-400 mb-1">
                <span>Min Similarity Score</span>
                <span className="text-emerald-400 font-bold">{minScore.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min={0.0}
                max={0.9}
                step={0.05}
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-full accent-emerald-500"
              />
            </div>

            <div>
              <div className="flex justify-between text-xs font-mono text-slate-400 mb-1">
                <span>Context Token Budget</span>
                <span className="text-emerald-400 font-bold">{contextBudget}</span>
              </div>
              <input
                type="range"
                min={500}
                max={6000}
                step={250}
                value={contextBudget}
                onChange={(e) => setContextBudget(Number(e.target.value))}
                className="w-full accent-emerald-500"
              />
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={isLoading || !taskText.trim()}
              className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-xs rounded-xl flex items-center gap-2 shadow-[0_0_20px_rgba(16,185,129,0.3)] transition-all disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
              <span>{isLoading ? "Executing Pipeline..." : "Process End-to-End Pipeline"}</span>
            </button>
          </div>
        </form>
      </Card>

      {/* ── Inspection Tabs / Results ───────────────────────────────────── */}
      {intelligenceResult && (
        <div className="space-y-6 animate-in fade-in duration-300">
          {/* Subsystem Decisions Banner */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card>
              <span className="text-[10px] font-mono text-slate-400 block mb-1">RAG RETRIEVAL STATUS</span>
              <div className="flex items-center justify-between">
                <span className="text-base font-bold text-slate-100">
                  {intelligenceResult.retrieved_context_items.length} Chunks In Budget
                </span>
                <StatusBadge status={intelligenceResult.memory_status} size="sm" />
              </div>
            </Card>

            <Card>
              <span className="text-[10px] font-mono text-slate-400 block mb-1">RULES RESOLUTION DECISION</span>
              <div className="flex items-center justify-between">
                <span className="text-base font-bold text-slate-100">
                  {intelligenceResult.winning_rules.length} Winning Constraint(s)
                </span>
                <StatusBadge status={intelligenceResult.rule_decision} size="sm" />
              </div>
            </Card>

            <Card>
              <span className="text-[10px] font-mono text-slate-400 block mb-1">TRUSTGATE AUTHORIZATION</span>
              <div className="flex items-center justify-between">
                <span className="text-base font-bold text-slate-100">
                  {executionResult?.pipeline.trustgate.allowed ? "Cleared for Exec" : "Access Blocked"}
                </span>
                <StatusBadge
                  status={executionResult?.pipeline.trustgate.decision || "STANDBY"}
                  size="sm"
                />
              </div>
            </Card>
          </div>

          {/* Deep Dives: Context Items & Rules */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Retrieved Memory Chunks */}
            <Card
              title={
                <div className="flex items-center gap-2">
                  <Database className="w-4 h-4 text-emerald-400" />
                  <span>Retrieved Knowledge Chunks ({intelligenceResult.retrieved_context_items.length})</span>
                </div>
              }
              subtitle="Source provenance and relevance scoring"
            >
              {intelligenceResult.retrieved_context_items.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-500 font-mono">
                  No relevant project memory found above score {minScore}.
                </div>
              ) : (
                <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
                  {intelligenceResult.retrieved_context_items.map((chunk: any, idx: number) => (
                    <div
                      key={idx}
                      className="p-3 bg-[#0a0f1d] border border-[#1b263e] rounded-lg space-y-1.5"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-mono text-emerald-400 font-semibold">
                          {chunk.source_path}:{chunk.start_line}-{chunk.end_line}
                        </span>
                        <span className="px-2 py-0.5 rounded bg-[#0d1e16] font-mono text-[10px] text-emerald-300">
                          Score: {(chunk.relevance_score * 100).toFixed(1)}%
                        </span>
                      </div>
                      <pre className="text-xs text-slate-300 bg-[#070b14] p-2 rounded border border-slate-900 font-mono whitespace-pre-wrap max-h-28 overflow-y-auto">
                        {chunk.content}
                      </pre>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            {/* Applicable & Winning Rules */}
            <Card
              title={
                <div className="flex items-center gap-2">
                  <Layers className="w-4 h-4 text-emerald-400" />
                  <span>Applicable Engineering Rules ({intelligenceResult.applicable_rules.length})</span>
                </div>
              }
              subtitle="Hierarchical resolution and conflict traces"
            >
              {intelligenceResult.applicable_rules.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-500 font-mono">
                  No applicable engineering constraints found for this task.
                </div>
              ) : (
                <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
                  {intelligenceResult.winning_rules.map((rule: any) => (
                    <div
                      key={rule.rule_id}
                      className="p-3 bg-[#0a0f1d] border border-[#1b263e] rounded-lg space-y-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <StatusBadge status={rule.effect} size="sm" />
                          <span className="text-xs font-semibold text-slate-200">{rule.name}</span>
                        </div>
                        <span className="text-[10px] font-mono text-slate-500 uppercase">
                          {rule.scope} | Priority {rule.priority}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400">{rule.description}</p>
                    </div>
                  ))}

                  {/* Conflict Traces */}
                  {intelligenceResult.rule_explanations.length > 0 && (
                    <div className="p-3 bg-[#111e19] border border-emerald-500/20 rounded-lg">
                      <span className="text-[10px] font-mono uppercase text-emerald-400 block mb-1">
                        RESOLUTION EXPLANATION TRACE
                      </span>
                      <ul className="text-xs text-slate-300 space-y-1 list-disc list-inside">
                        {intelligenceResult.rule_explanations.map((exp: string, i: number) => (
                          <li key={i}>{exp}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </Card>
          </div>

          {/* Member 1 StructuredTask Prompt Injection */}
          {planResult && planResult.task && (
            <Card
              title={
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-emerald-400" />
                  <span>Member 1 StructuredTask Representation</span>
                </div>
              }
              subtitle="Normalized prompt generated by RequestPlanner"
            >
              <div className="space-y-3 font-mono text-xs">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="p-3 bg-[#0a0f1d] rounded-lg border border-[#1a253c]">
                    <span className="text-slate-500 block mb-1">ROLE:</span>
                    <span className="text-slate-200">{planResult.task.role}</span>
                  </div>
                  <div className="p-3 bg-[#0a0f1d] rounded-lg border border-[#1a253c]">
                    <span className="text-slate-500 block mb-1">PLANNING STATUS:</span>
                    <span className={planResult.ready ? "text-emerald-400" : "text-amber-400"}>
                      {planResult.ready ? "READY (0 questions)" : "CLARIFICATION REQUIRED"}
                    </span>
                  </div>
                </div>

                <div className="p-3 bg-[#0a0f1d] rounded-lg border border-[#1a253c]">
                  <span className="text-slate-500 block mb-1">INJECTED CONTEXT & PROVENANCE:</span>
                  <pre className="text-slate-300 whitespace-pre-wrap max-h-40 overflow-y-auto">
                    {planResult.task.context || "No context attached"}
                  </pre>
                </div>
              </div>
            </Card>
          )}

          {/* Raw Generated Prompt Context */}
          <Card
            title={
              <div className="flex items-center gap-2">
                <Code2 className="w-4 h-4 text-slate-400" />
                <span>Combined Laya Prompt Context Block</span>
              </div>
            }
            subtitle="The exact formatted markdown string injected into the LLM system prompt"
          >
            <pre className="p-4 bg-[#070b14] border border-[#1a253b] rounded-lg text-xs font-mono text-slate-300 whitespace-pre-wrap max-h-64 overflow-y-auto selection:bg-emerald-500/30">
              {intelligenceResult.combined_laya_context}
            </pre>
          </Card>
        </div>
      )}

      {/* ── Warning Confirmation Modal ──────────────────────────────────── */}
      <Modal
        isOpen={confirmModalOpen}
        onClose={() => setConfirmModalOpen(false)}
        title="Security Warning Confirmation Gate"
        subtitle="TrustGate detected regulatory warnings requiring explicit human confirmation"
      >
        <div className="space-y-4">
          <div className="p-3.5 bg-amber-950/40 border border-amber-500/40 rounded-lg flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="text-xs text-amber-200">
              <span className="font-bold block mb-1">HIGH RISK REGULATORY FLAG:</span>
              {executionResult?.pipeline.trustgate.warnings.map((w: string, i: number) => (
                <div key={i} className="mt-1">
                  • {w}
                </div>
              ))}
            </div>
          </div>

          <div className="text-xs text-slate-300 font-mono">
            Confirmation Token:{" "}
            <span className="text-emerald-400 font-bold">{confirmToken}</span>
          </div>

          <p className="text-xs text-slate-400">
            By confirming, you authorize the CLI agent to proceed with this operation. The event will be permanently recorded in the cryptographic audit ledger.
          </p>

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              onClick={() => setConfirmModalOpen(false)}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirmWarning}
              disabled={isConfirming}
              className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-slate-950 text-xs font-bold transition-all shadow-[0_0_15px_rgba(245,158,11,0.3)]"
            >
              {isConfirming ? "Confirming..." : "Confirm & Authorize Execution"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
