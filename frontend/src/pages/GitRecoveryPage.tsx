import React, { useState, useEffect } from "react";
import { useApp } from "../context/AppContext";
import { Card } from "../components/Card";
import { StatusBadge } from "../components/StatusBadge";
import { Modal } from "../components/Modal";
import { gitApi } from "../api/git";
import type { UndoPreviewResponse, UndoResultResponse } from "../api/git";
import type { GitStatusResponse, GitCommitItem } from "../types";
import {
  GitBranch,
  GitCommit,
  RotateCcw,
  FileDiff,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  FolderGit2,
} from "lucide-react";

export const GitRecoveryPage: React.FC = () => {
  const { currentCli, showToast } = useApp();
  const [gitStatus, setGitStatus] = useState<GitStatusResponse | null>(null);
  const [gitHistory, setGitHistory] = useState<GitCommitItem[]>([]);
  const [gitDiff, setGitDiff] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);

  // Recovery modal
  const [recoveryModalOpen, setRecoveryModalOpen] = useState(false);
  const [targetSessionId, setTargetSessionId] = useState("");
  const [undoPreview, setUndoPreview] = useState<UndoPreviewResponse | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isExecutingUndo, setIsExecutingUndo] = useState(false);

  const fetchGitData = async () => {
    setIsLoading(true);
    try {
      const [st, hist, diffRes] = await Promise.all([
        gitApi.getStatus(),
        gitApi.getHistory(20),
        gitApi.getDiff(),
      ]);
      setGitStatus(st);
      setGitHistory(hist);
      setGitDiff(diffRes.diff);
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Git Inspection Error",
        message: err instanceof Error ? err.message : "Failed to read git state",
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchGitData();
  }, []);

  const handlePreviewUndo = async (sessionId: string) => {
    if (!sessionId.trim()) return;
    setIsPreviewing(true);
    setUndoPreview(null);
    try {
      const prev = await gitApi.previewUndo(sessionId.trim());
      setUndoPreview(prev);
      setTargetSessionId(sessionId.trim());
      setRecoveryModalOpen(true);
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Undo Preview Failed",
        message: err instanceof Error ? err.message : "Cannot preview undo for session",
      });
    } finally {
      setIsPreviewing(false);
    }
  };

  const handleExecuteUndo = async () => {
    if (!targetSessionId) return;
    setIsExecutingUndo(true);
    try {
      const res: UndoResultResponse = await gitApi.executeUndo(targetSessionId, currentCli, true);
      showToast({
        type: "success",
        title: "Session Revert Executed",
        message: `Reverted ${res.reverted_commit.substring(0, 8)} -> Created recovery commit ${res.recovery_commit.substring(0, 8)}`,
      });
      setRecoveryModalOpen(false);
      fetchGitData();
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Undo Failed",
        message: err instanceof Error ? err.message : "Error executing session revert",
      });
    } finally {
      setIsExecutingUndo(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* ── Page Header ─────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#1b253b] pb-5">
        <div>
          <div className="flex items-center gap-2">
            <GitBranch className="w-6 h-6 text-amber-400" />
            <h1 className="text-xl font-bold tracking-tight text-slate-100">
              Git Inspection & Rollback Recovery Center
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Member 1 capability: read-only work-tree inspection, diff viewing, and session commit reversion
          </p>
        </div>

        <button
          onClick={fetchGitData}
          disabled={isLoading}
          className="px-4 py-2 bg-[#0e1628] hover:bg-[#16223b] border border-[#1f2b44] text-slate-200 text-xs font-semibold rounded-xl flex items-center gap-2 transition-all disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-amber-400" : ""}`} />
          <span>Refresh Git State</span>
        </button>
      </div>

      {/* ── Work-Tree Status Metrics ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <span className="text-[10px] font-mono text-slate-400 block mb-1">ACTIVE BRANCH</span>
          <div className="text-xl font-bold font-mono text-amber-400">
            {gitStatus?.branch || "main"}
          </div>
          <p className="text-[11px] text-slate-500 mt-1 font-mono truncate">
            {gitStatus?.project_root || "A:\\CLIVERSE"}
          </p>
        </Card>

        <Card>
          <span className="text-[10px] font-mono text-slate-400 block mb-1">WORK-TREE STATE</span>
          <div className="flex items-center gap-2 mt-1">
            <StatusBadge status={gitStatus?.is_clean ? "CLEAN" : "MODIFIED"} size="sm" />
          </div>
          <p className="text-[11px] text-slate-500 mt-2 font-mono">
            {gitStatus?.changed_paths.length ?? 0} changed file(s)
          </p>
        </Card>

        <Card>
          <span className="text-[10px] font-mono text-slate-400 block mb-1">RECOVERY SAFETY GATE</span>
          <div className="flex items-center gap-2 mt-1">
            <StatusBadge status={gitStatus?.is_clean ? "ALLOW" : "WARN"} size="sm" />
          </div>
          <p className="text-[11px] text-slate-500 mt-2 font-mono">
            {gitStatus?.is_clean ? "Work-tree clean: undo safe" : "Uncommitted changes prevent undo"}
          </p>
        </Card>
      </div>

      {/* ── Changed Files & Porcelain ───────────────────────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <FolderGit2 className="w-4 h-4 text-amber-400" />
            <span>Changed Work-Tree Paths ({gitStatus?.changed_paths.length ?? 0})</span>
          </div>
        }
        subtitle="Unstaged or staged files in the local workspace"
      >
        {(!gitStatus?.changed_paths || gitStatus.changed_paths.length === 0) ? (
          <div className="py-6 text-center text-xs text-slate-500 font-mono flex items-center justify-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>Working tree clean — no unstaged or modified files.</span>
          </div>
        ) : (
          <div className="space-y-1.5 max-h-48 overflow-y-auto font-mono text-xs">
            {gitStatus.changed_paths.map((p, i) => (
              <div
                key={i}
                className="px-3 py-1.5 bg-[#090e1c] border border-[#19243a] rounded-lg text-slate-300 flex items-center justify-between"
              >
                <span>{p}</span>
                <span className="px-1.5 py-0.5 rounded bg-[#131d31] text-[10px] text-amber-400">
                  MODIFIED
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* ── Recent Commits & Session Undo ───────────────────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <GitCommit className="w-4 h-4 text-emerald-400" />
            <span>Recent Commit History & Session Recovery ({gitHistory.length})</span>
          </div>
        }
        subtitle="Commits with session metadata can be rolled back safely via GitRecovery"
      >
        <div className="divide-y divide-[#182338]">
          {gitHistory.map((c) => (
            <div key={c.commit_id} className="py-3 flex items-center justify-between gap-4 text-xs font-mono">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-amber-400 font-bold">{c.commit_id.substring(0, 7)}</span>
                  <span className="text-slate-200 truncate">{c.subject}</span>
                </div>
                {c.session_id && (
                  <span className="text-[10px] text-emerald-400 mt-0.5 block">
                    Session Tag: {c.session_id}
                  </span>
                )}
              </div>

              {c.session_id && (
                <button
                  onClick={() => handlePreviewUndo(c.session_id!)}
                  disabled={isPreviewing || !gitStatus?.is_clean}
                  className="px-2.5 py-1 rounded bg-red-950/40 hover:bg-red-900/60 text-red-300 border border-red-500/30 text-[11px] transition-colors flex items-center gap-1.5 disabled:opacity-40"
                  title={!gitStatus?.is_clean ? "Clean working tree required for undo" : "Preview revert"}
                >
                  <RotateCcw className="w-3 h-3" />
                  <span>Undo Commit</span>
                </button>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* ── Git Diff Viewer ─────────────────────────────────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <FileDiff className="w-4 h-4 text-slate-400" />
            <span>Repository Working Diff</span>
          </div>
        }
        subtitle="Unified diff output from GitInspector"
      >
        {!gitDiff.trim() ? (
          <div className="py-6 text-center text-xs text-slate-500 font-mono">
            No working tree diff to display.
          </div>
        ) : (
          <pre className="p-4 bg-[#070b14] border border-[#1a253b] rounded-lg text-xs font-mono text-slate-300 whitespace-pre-wrap max-h-96 overflow-y-auto">
            {gitDiff}
          </pre>
        )}
      </Card>

      {/* ── Undo Confirmation Modal ─────────────────────────────────────── */}
      <Modal
        isOpen={recoveryModalOpen}
        onClose={() => setRecoveryModalOpen(false)}
        title="Confirm Session Commit Reversion"
        subtitle="Member 1 GitRecovery will safely revert the target commit"
      >
        <div className="space-y-4">
          <div className="p-3 bg-red-950/40 border border-red-500/40 rounded-lg flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div className="text-xs text-red-200">
              <span className="font-bold block mb-1">DESTRUCTIVE ROLLBACK ACTION:</span>
              This will create a new git revert commit restoring the state prior to session{" "}
              <span className="font-mono font-bold text-slate-100">{targetSessionId}</span>.
            </div>
          </div>

          {undoPreview && (
            <div className="space-y-2 text-xs font-mono bg-[#090f1d] p-3 rounded-lg border border-slate-800">
              <div>
                Target Commit:{" "}
                <span className="text-amber-400 font-bold">{undoPreview.target_commit.substring(0, 8)}</span>
              </div>
              <div>
                Affected Files:{" "}
                <span className="text-slate-300 font-bold">{undoPreview.changed_paths.length} file(s)</span>
              </div>
              <ul className="list-disc list-inside text-slate-400 mt-1 max-h-32 overflow-y-auto">
                {undoPreview.changed_paths.map((p, idx) => (
                  <li key={idx}>{p}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              onClick={() => setRecoveryModalOpen(false)}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300"
            >
              Cancel
            </button>
            <button
              onClick={handleExecuteUndo}
              disabled={isExecutingUndo}
              className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-slate-100 font-bold text-xs transition-all shadow-[0_0_15px_rgba(239,68,68,0.3)] disabled:opacity-50"
            >
              {isExecutingUndo ? "Reverting..." : "Confirm & Execute Revert"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
