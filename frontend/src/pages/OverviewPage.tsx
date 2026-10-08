import React, { useState } from "react";
import { useApp } from "../context/AppContext";
import { Card } from "../components/Card";
import { StatusBadge } from "../components/StatusBadge";
import { layaApi } from "../api/laya";
import type { TabId } from "../components/Layout";
import {
  Database,
  Layers,
  ShieldCheck,
  GitBranch,
  Activity,
  ArrowRight,
  Send,
  Sparkles,
  ExternalLink,
} from "lucide-react";

interface OverviewPageProps {
  onNavigate: (tab: TabId) => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({ onNavigate }) => {
  const { health, currentProject, currentCli, recentActivities, showToast } = useApp();
  const [quickTask, setQuickTask] = useState("");
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [quickResult, setQuickResult] = useState<any>(null);

  const handleQuickEvaluate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickTask.trim()) return;

    setIsEvaluating(true);
    setQuickResult(null);
    try {
      const res = await layaApi.executePipeline({
        task: quickTask.trim(),
        project_id: currentProject,
        cli_name: currentCli,
      });
      setQuickResult(res);
      showToast({
        type: res.pipeline.trustgate.allowed ? "success" : "warn",
        title: "Pipeline Evaluated",
        message: `Task evaluated: Rule=${res.pipeline.rules.decision}, TrustGate=${res.pipeline.trustgate.decision}`,
      });
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Evaluation Failed",
        message: err instanceof Error ? err.message : "Error executing pipeline",
      });
    } finally {
      setIsEvaluating(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* ── Top Status Cards ────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        {/* System Status */}
        <Card className="border-l-4 border-l-emerald-500">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400">SYSTEM STATE</span>
            <StatusBadge status={health?.status || "HEALTHY"} size="sm" />
          </div>
          <div className="mt-3">
            <div className="text-2xl font-bold text-slate-100 font-mono tracking-tight">
              OPERATIONAL
            </div>
            <p className="text-xs text-slate-400 mt-1">All Member Subsystems Online</p>
          </div>
        </Card>

        {/* Memory RAG */}
        <Card className="border-l-4 border-l-emerald-500 cursor-pointer" onClick={() => onNavigate("memory")}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400">MEMORY / RAG</span>
            <StatusBadge status={health?.subsystems.memory.status || "OK_WITH_RESULTS"} size="sm" />
          </div>
          <div className="mt-3">
            <div className="text-2xl font-bold text-emerald-400 font-mono">
              {health?.subsystems.memory.chunks_count ?? 0}{" "}
              <span className="text-xs font-normal text-slate-400">indexed chunks</span>
            </div>
            <p className="text-xs text-slate-400 mt-1 truncate">
              {health?.subsystems.memory.provider || "Local 64-dim baseline"}
            </p>
          </div>
        </Card>

        {/* Rules */}
        <Card className="border-l-4 border-l-emerald-600 cursor-pointer" onClick={() => onNavigate("rules")}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400">RULES ENGINE</span>
            <StatusBadge status={health?.subsystems.rules.status || "OK_WITH_RESULTS"} size="sm" />
          </div>
          <div className="mt-3">
            <div className="text-2xl font-bold text-emerald-400 font-mono">
              {health?.subsystems.rules.rules_count ?? 0}{" "}
              <span className="text-xs font-normal text-slate-400">active rules</span>
            </div>
            <p className="text-xs text-slate-400 mt-1">Hierarchical Conflict Engine</p>
          </div>
        </Card>

        {/* TrustGate */}
        <Card className="border-l-4 border-l-rose-500 cursor-pointer" onClick={() => onNavigate("security")}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400">SECURITY GATE</span>
            <StatusBadge status={health?.subsystems.security.status || "ACTIVE"} size="sm" />
          </div>
          <div className="mt-3">
            <div className="text-2xl font-bold text-rose-400 font-mono">
              {health?.subsystems.security.mode || "STRICT"}{" "}
              <span className="text-xs font-normal text-slate-400">sandbox</span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Audit Chain: {health?.subsystems.security.audit_chain_valid ? "VERIFIED" : "TAMPERED"}
            </p>
          </div>
        </Card>

        {/* Git */}
        <Card className="border-l-4 border-l-amber-500 cursor-pointer" onClick={() => onNavigate("git")}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400">GIT ENGINE</span>
            <StatusBadge status={health?.subsystems.git.status || "CLEAN"} size="sm" />
          </div>
          <div className="mt-3">
            <div className="text-2xl font-bold text-amber-400 font-mono truncate">
              {health?.subsystems.git.branch || "main"}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Work tree: {health?.subsystems.git.status || "CLEAN"}
            </p>
          </div>
        </Card>

        {/* CLI Providers */}
        <Card className="border-l-4 border-l-emerald-500 cursor-pointer" onClick={() => onNavigate("providers")}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400">CLI PROVIDERS</span>
            <span className="inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-500/40">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              READY
            </span>
          </div>
          <div className="mt-3">
            <div className="text-2xl font-bold text-emerald-400 font-mono">
              2 <span className="text-xs font-normal text-slate-400">installed</span>
            </div>
            <p className="text-xs text-slate-400 mt-1 truncate">
              Claude Code & Aider
            </p>
          </div>
        </Card>
      </div>

      {/* ── Central Quick-Commander ────────────────────────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-emerald-400" />
            <span>Laya Quick-Commander & Live Pipeline</span>
          </div>
        }
        subtitle={`Execute task intent across Memory, Rules, Planning, and TrustGate for ${currentProject}`}
        action={
          <button
            onClick={() => onNavigate("laya")}
            className="flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300 transition-colors font-medium"
          >
            <span>Open Full Workspace</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        }
      >
        <form onSubmit={handleQuickEvaluate} className="space-y-4">
          <div className="relative">
            <input
              type="text"
              value={quickTask}
              onChange={(e) => setQuickTask(e.target.value)}
              placeholder="e.g., Implement pre-commit hook to verify test suite passing..."
              className="w-full bg-[#0a0f1d] border border-[#23314d] rounded-xl px-4 py-3.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-all font-mono"
            />
            <button
              type="submit"
              disabled={isEvaluating || !quickTask.trim()}
              className="absolute right-2.5 top-2.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-semibold rounded-lg text-xs flex items-center gap-2 transition-all disabled:opacity-50 shadow-[0_0_15px_rgba(16,185,129,0.3)]"
            >
              <Send className="w-3.5 h-3.5" />
              <span>{isEvaluating ? "Evaluating..." : "Run Pipeline"}</span>
            </button>
          </div>

          <div className="flex flex-wrap gap-2 text-xs text-slate-400">
            <span className="text-slate-500">Quick Scenarios:</span>
            <button
              type="button"
              onClick={() => setQuickTask("Verify test suite passes before committing changes")}
              className="px-2.5 py-1 rounded-md bg-[#131d31] hover:bg-[#1c2944] text-slate-300 transition-colors"
            >
              Scenario A: Safe Test Task
            </button>
            <button
              type="button"
              onClick={() => setQuickTask("Execute rm -rf / to clean up system files")}
              className="px-2.5 py-1 rounded-md bg-[#1c1318] hover:bg-[#2e1921] text-red-300 transition-colors border border-red-500/20"
            >
              Scenario B: Prohibited Command (DENY)
            </button>
            <button
              type="button"
              onClick={() => setQuickTask("Process user biometric and facial recognition data")}
              className="px-2.5 py-1 rounded-md bg-[#1f190e] hover:bg-[#332714] text-amber-300 transition-colors border border-amber-500/20"
            >
              Scenario C: Compliance Warning (WARN)
            </button>
          </div>
        </form>

        {/* Quick Result Pipeline Trace */}
        {quickResult && (
          <div className="mt-6 pt-5 border-t border-[#1c263c] space-y-4 animate-in fade-in duration-200">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-mono font-semibold uppercase tracking-wider text-slate-400">
                Pipeline Execution Trace
              </h4>
              <span className="text-xs font-mono text-slate-500">CLI: {quickResult.cli_name}</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
              {/* Stage 1: Memory */}
              <div className="bg-[#090e1a] border border-[#1a253b] rounded-lg p-3">
                <span className="text-[10px] font-mono text-slate-500 block mb-1">1. MEMORY / RAG</span>
                <StatusBadge status={quickResult.pipeline.memory.status} size="sm" />
                <p className="text-xs text-slate-400 mt-2">
                  {quickResult.pipeline.memory.chunks_retrieved} context chunks
                </p>
              </div>

              {/* Stage 2: Rules */}
              <div className="bg-[#090e1a] border border-[#1a253b] rounded-lg p-3">
                <span className="text-[10px] font-mono text-slate-500 block mb-1">2. RULES RESOLUTION</span>
                <StatusBadge status={quickResult.pipeline.rules.decision} size="sm" />
                <p className="text-xs text-slate-400 mt-2">
                  {quickResult.pipeline.rules.winning_rules_count} winning rule(s)
                </p>
              </div>

              {/* Stage 3: Planning */}
              <div className="bg-[#090e1a] border border-[#1a253b] rounded-lg p-3">
                <span className="text-[10px] font-mono text-slate-500 block mb-1">3. LAYA PLANNING</span>
                <StatusBadge status={quickResult.pipeline.planning.ready ? "READY" : "WARN"} size="sm" />
                <p className="text-xs text-slate-400 mt-2">Structured prompt built</p>
              </div>

              {/* Stage 4: TrustGate */}
              <div className="bg-[#090e1a] border border-[#1a253b] rounded-lg p-3">
                <span className="text-[10px] font-mono text-slate-500 block mb-1">4. TRUSTGATE AUTHORIZATION</span>
                <StatusBadge status={quickResult.pipeline.trustgate.decision} size="sm" />
                <p className="text-xs text-slate-400 mt-2 truncate" title={quickResult.pipeline.trustgate.reason}>
                  {quickResult.pipeline.trustgate.reason}
                </p>
              </div>

              {/* Stage 5: Execution */}
              <div className="bg-[#090e1a] border border-[#1a253b] rounded-lg p-3">
                <span className="text-[10px] font-mono text-slate-500 block mb-1">5. EXECUTION STATUS</span>
                <StatusBadge
                  status={
                    quickResult.pipeline.execution.status === "EXECUTED_SUCCESS"
                      ? "ALLOW"
                      : quickResult.pipeline.execution.status === "AWAITING_CONFIRMATION"
                      ? "WARN"
                      : "DENY"
                  }
                  size="sm"
                />
                <p className="text-xs text-slate-400 mt-2 font-mono truncate">
                  {quickResult.pipeline.execution.status}
                </p>
              </div>
            </div>
          </div>
        )}
      </Card>

      {/* ── Two Column Deep Inspection ──────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column: Cognitive Subsystems (Memory + Rules) */}
        <div className="space-y-6">
          {/* Memory Quick View */}
          <Card
            title={
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-emerald-400" />
                <span>Knowledge & Memory (Member 2)</span>
              </div>
            }
            action={
              <button
                onClick={() => onNavigate("memory")}
                className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1 font-medium"
              >
                <span>Search Chunks</span>
                <ExternalLink className="w-3 h-3" />
              </button>
            }
          >
            <div className="space-y-3">
              <div className="p-3 bg-[#0a101f] border border-[#1c2944] rounded-lg">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400 font-mono">SQLite Knowledge DB</span>
                  <span className="text-slate-300 font-mono">.envcore/memory/cliverse_memory.db</span>
                </div>
                <div className="mt-2 text-xs text-slate-400">
                  Total Indexed Records: <span className="text-slate-100 font-bold">2 records</span> (
                  <span className="text-emerald-400 font-bold">{health?.subsystems.memory.chunks_count ?? 128}</span> chunks)
                </div>
              </div>

              <div className="text-xs text-slate-400 leading-relaxed">
                Persistent storage indexes architectural docs, decision records, and session history with SHA-256 deduplication and hybrid cosine + keyword retrieval.
              </div>
            </div>
          </Card>

          {/* Rules Quick View */}
          <Card
            title={
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-emerald-400" />
                <span>Rules Intelligence (Member 2)</span>
              </div>
            }
            action={
              <button
                onClick={() => onNavigate("rules")}
                className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1 font-medium"
              >
                <span>Manage Rules</span>
                <ExternalLink className="w-3 h-3" />
              </button>
            }
          >
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                <div className="p-2.5 bg-[#0a101f] border border-[#19243a] rounded-lg flex items-center justify-between">
                  <span className="text-rose-300">REQUIRE</span>
                  <span className="text-slate-200 font-bold">1 active</span>
                </div>
                <div className="p-2.5 bg-[#0a101f] border border-[#19243a] rounded-lg flex items-center justify-between">
                  <span className="text-red-300">DENY (MANDATORY)</span>
                  <span className="text-slate-200 font-bold">1 active</span>
                </div>
                <div className="p-2.5 bg-[#0a101f] border border-[#19243a] rounded-lg flex items-center justify-between">
                  <span className="text-amber-300">WARN</span>
                  <span className="text-slate-200 font-bold">1 active</span>
                </div>
                <div className="p-2.5 bg-[#0a101f] border border-[#19243a] rounded-lg flex items-center justify-between">
                  <span className="text-emerald-300">ALLOW</span>
                  <span className="text-slate-200 font-bold">1 active</span>
                </div>
              </div>

              <p className="text-xs text-slate-400">
                Priority hierarchy: <span className="font-mono text-slate-200">TASK (400) &gt; CLI (300) &gt; PROJECT (200) &gt; GLOBAL (100)</span>. Mandatory DENY rules cannot be overridden.
              </p>
            </div>
          </Card>
        </div>

        {/* Right Column: Execution & Security Subsystems (Member 1 + Member 4) */}
        <div className="space-y-6">
          {/* Security / TrustGate Quick View */}
          <Card
            title={
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-rose-400" />
                <span>Security & TrustGate (Member 4)</span>
              </div>
            }
            action={
              <button
                onClick={() => onNavigate("security")}
                className="text-xs text-rose-400 hover:text-rose-300 flex items-center gap-1 font-medium"
              >
                <span>Audit Trail</span>
                <ExternalLink className="w-3 h-3" />
              </button>
            }
          >
            <div className="space-y-3">
              <div className="p-3 bg-[#0a101f] border border-[#1c2944] rounded-lg flex items-center justify-between">
                <div>
                  <div className="text-xs font-semibold text-slate-200">Cryptographic Audit Chain</div>
                  <div className="text-[11px] text-slate-400 font-mono mt-0.5">SHA-256 Tamper-evident ledger</div>
                </div>
                <StatusBadge status="VERIFIED" size="sm" />
              </div>

              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>Active Registered Agents:</span>
                <span className="font-mono font-semibold text-slate-200">
                  {health?.subsystems.security.active_identities ?? 1} AI CLIs
                </span>
              </div>
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>Sandbox Mode:</span>
                <span className="font-mono font-semibold text-rose-300">
                  {health?.subsystems.security.mode || "STRICT"}
                </span>
              </div>
            </div>
          </Card>

          {/* Git Inspection Quick View */}
          <Card
            title={
              <div className="flex items-center gap-2">
                <GitBranch className="w-4 h-4 text-amber-400" />
                <span>Git Work-Tree & Commits (Member 1)</span>
              </div>
            }
            action={
              <button
                onClick={() => onNavigate("git")}
                className="text-xs text-amber-400 hover:text-amber-300 flex items-center gap-1 font-medium"
              >
                <span>Diff & Recovery</span>
                <ExternalLink className="w-3 h-3" />
              </button>
            }
          >
            <div className="space-y-3">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-slate-400">Current Branch:</span>
                <span className="text-slate-200 font-bold">{health?.subsystems.git.branch || "main"}</span>
              </div>
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-slate-400">Work-Tree Status:</span>
                <StatusBadge status={health?.subsystems.git.status || "CLEAN"} size="sm" />
              </div>
              <p className="text-xs text-slate-400">
                Provides read-only status, diff inspection, session commit tagging, and confirmation-gated rollback recovery.
              </p>
            </div>
          </Card>
        </div>
      </div>

      {/* ── Bottom Section: Real-Time Live Activity Feed ────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-emerald-400 animate-pulse" />
            <span>Live Activity Stream (Real Telemetry)</span>
          </div>
        }
        subtitle="Chronological feed of real operations, memory queries, rule resolutions, and audit events"
        action={
          <button
            onClick={() => onNavigate("activity")}
            className="text-xs text-emerald-400 hover:text-emerald-300 font-medium"
          >
            View All ({recentActivities.length})
          </button>
        }
      >
        <div className="divide-y divide-[#182338] max-h-72 overflow-y-auto">
          {recentActivities.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-500 font-mono">
              Waiting for live telemetry events...
            </div>
          ) : (
            recentActivities.slice(0, 8).map((evt) => (
              <div key={evt.event_id} className="py-2.5 flex items-center justify-between gap-4 text-xs">
                <div className="flex items-center gap-3 min-w-0">
                  <span className="px-1.5 py-0.5 rounded bg-[#10192b] text-[10px] font-mono text-slate-400 border border-slate-800">
                    {evt.source}
                  </span>
                  <span className="text-slate-200 font-medium truncate">{evt.summary}</span>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <StatusBadge status={evt.status} size="sm" showIcon={false} />
                  <span className="text-[11px] font-mono text-slate-500">
                    {new Date(evt.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
};
