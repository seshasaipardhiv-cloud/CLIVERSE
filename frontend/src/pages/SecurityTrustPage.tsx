import React, { useState, useEffect } from "react";
import { useApp } from "../context/AppContext";
import { Card } from "../components/Card";
import { StatusBadge } from "../components/StatusBadge";
import { Modal } from "../components/Modal";
import { securityApi } from "../api/security";
import type { SecurityEvaluationResult } from "../api/security";
import type { SecuritySummary, AgentIdentity, AuditEventItem } from "../types";
import {
  ShieldAlert,
  ShieldCheck,
  UserCheck,
  FileCheck2,
  Play,
  RotateCw,
  Plus,
} from "lucide-react";

export const SecurityTrustPage: React.FC = () => {
  const { showToast } = useApp();
  const [summary, setSummary] = useState<SecuritySummary | null>(null);
  const [identities, setIdentities] = useState<AgentIdentity[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEventItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Playground state
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [evalOp, setEvalOp] = useState("execute");
  const [evalCmd, setEvalCmd] = useState("git status");
  const [evalPath, setEvalPath] = useState("");
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [evalResult, setEvalResult] = useState<SecurityEvaluationResult | null>(null);

  // Confirmation flow
  const [confirmToken, setConfirmToken] = useState("");
  const [isConfirming, setIsConfirming] = useState(false);

  // Register Agent Modal
  const [registerModalOpen, setRegisterModalOpen] = useState(false);
  const [newCliName, setNewCliName] = useState("gemini-cli");
  const [newScopes, setNewScopes] = useState("read, write, git");
  const [isRegistering, setIsRegistering] = useState(false);

  const fetchSecurityData = async () => {
    setIsLoading(true);
    try {
      const [sum, idents, aud] = await Promise.all([
        securityApi.getSummary(),
        securityApi.listIdentities(),
        securityApi.getAuditTrail(40),
      ]);
      setSummary(sum);
      setIdentities(idents);
      setAuditEvents(aud.events);
      if (idents.length > 0 && !selectedAgentId) {
        setSelectedAgentId(idents[0].agent_id);
      }
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Security Data Load Error",
        message: err instanceof Error ? err.message : "Error fetching security data",
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSecurityData();
  }, []);

  const handleEvaluate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAgentId) {
      showToast({ type: "warn", title: "Select Agent", message: "Register or select an active agent identity" });
      return;
    }

    setIsEvaluating(true);
    setEvalResult(null);
    try {
      const res = await securityApi.evaluateOperation({
        agent_id: selectedAgentId,
        operation: evalOp,
        command: evalCmd.trim() || undefined,
        path: evalPath.trim() || undefined,
        user_confirmed: false,
      });
      setEvalResult(res);
      if (res.confirmation_token) {
        setConfirmToken(res.confirmation_token);
      }
      showToast({
        type: res.allowed ? "success" : res.decision === "WARN" ? "warn" : "error",
        title: `Gate Evaluated: ${res.decision}`,
        message: res.reason,
      });
      fetchSecurityData();
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Evaluation Error",
        message: err instanceof Error ? err.message : "Failed to evaluate operation",
      });
    } finally {
      setIsEvaluating(false);
    }
  };

  const handleConfirm = async () => {
    if (!confirmToken.trim()) return;
    setIsConfirming(true);
    try {
      const res = await securityApi.confirmWarning(confirmToken.trim());
      setEvalResult(res);
      showToast({
        type: "success",
        title: "Operation Approved",
        message: "Warning confirmed; execution cleared with audited approval",
      });
      fetchSecurityData();
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Confirmation Failed",
        message: err instanceof Error ? err.message : "Invalid or expired confirmation token",
      });
    } finally {
      setIsConfirming(false);
    }
  };

  const handleRegisterIdentity = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCliName.trim()) return;
    setIsRegistering(true);
    try {
      const sc = newScopes.split(",").map((s) => s.trim()).filter(Boolean);
      const ident = await securityApi.registerIdentity(newCliName.trim(), sc);
      showToast({
        type: "success",
        title: "CLI Identity Registered",
        message: `Registered agent ${ident.agent_id.substring(0, 8)} (${ident.cli_name})`,
      });
      setRegisterModalOpen(false);
      fetchSecurityData();
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Registration Failed",
        message: err instanceof Error ? err.message : "Error registering identity",
      });
    } finally {
      setIsRegistering(false);
    }
  };

  const handleRevokeIdentity = async (agentId: string) => {
    if (!confirm(`Revoke session for agent ${agentId}?`)) return;
    try {
      await securityApi.revokeIdentity(agentId);
      showToast({
        type: "warn",
        title: "Agent Revoked",
        message: `Revoked identity session for ${agentId.substring(0, 8)}`,
      });
      fetchSecurityData();
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Revocation Failed",
        message: err instanceof Error ? err.message : "Error revoking agent",
      });
    }
  };

  return (
    <div className="space-y-6">
      {/* ── Page Header ─────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#1b253b] pb-5">
        <div>
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-rose-400" />
            <h1 className="text-xl font-bold tracking-tight text-slate-100">
              Security, TrustGate & Governance Center
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Member 4 authority: strict sandboxing, agent identity tokens, regulatory compliance, and tamper-evident audit ledger
          </p>
        </div>

        <button
          onClick={() => setRegisterModalOpen(true)}
          className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-slate-950 font-bold text-xs rounded-xl flex items-center gap-2 shadow-[0_0_15px_rgba(244,63,94,0.3)] transition-all"
        >
          <Plus className="w-4 h-4" />
          <span>Register CLI Agent</span>
        </button>
      </div>

      {/* ── Crucial Subsystem Distinction Alert ─────────────────────────── */}
      <div className="p-4 rounded-xl bg-[#180a0e] border border-rose-500/30 flex items-start gap-3">
        <ShieldCheck className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
        <div className="text-xs text-slate-300 leading-relaxed">
          <span className="font-bold text-rose-300 block mb-0.5">
            ARCHITECTURAL RESPONSIBILITY BOUNDARY:
          </span>
          <span className="text-slate-200 font-semibold">Member 2 Rule Decisions</span> (ALLOW, WARN, REQUIRE, ASK, DENY) resolve engineering &amp; developer constraints for prompt planning.
          They are <span className="text-red-400 font-bold">NOT</span> execution authorization.
          <span className="text-rose-300 font-bold"> Member 4 TrustGate</span> is the final execution authority governing process launch, command sandboxing, and regulatory approvals.
        </div>
      </div>

      {/* ── Security Key Metrics ────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <Card>
          <span className="text-[10px] font-mono text-slate-400 block mb-1">SANDBOX ISOLATION MODE</span>
          <div className="text-xl font-bold font-mono text-rose-400">
            {summary?.mode || "STRICT"}
          </div>
          <p className="text-[11px] text-slate-500 mt-1 font-mono">Allowed root: A:\CLIVERSE</p>
        </Card>

        <Card>
          <span className="text-[10px] font-mono text-slate-400 block mb-1">AUDIT CHAIN INTEGRITY</span>
          <div className="flex items-center gap-2 mt-1">
            <StatusBadge status={summary?.chain_status || "VERIFIED"} size="sm" />
          </div>
          <p className="text-[11px] text-slate-500 mt-2 font-mono truncate" title={summary?.chain_message}>
            {summary?.chain_message || "All hash links valid"}
          </p>
        </Card>

        <Card>
          <span className="text-[10px] font-mono text-slate-400 block mb-1">ACTIVE TRUSTED SESSIONS</span>
          <div className="text-2xl font-bold font-mono text-slate-100">
            {identities.length} <span className="text-xs font-normal text-slate-400">identities</span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1 font-mono">Scope-governed tokens</p>
        </Card>

        <Card>
          <span className="text-[10px] font-mono text-slate-400 block mb-1">SECURITY & AUDIT EVENTS</span>
          <div className="text-2xl font-bold font-mono text-slate-100">
            {summary?.audit_events_count ?? 0}
          </div>
          <p className="text-[11px] text-slate-500 mt-1 font-mono">
            {summary?.security_alerts_count ?? 0} flagged security alert(s)
          </p>
        </Card>
      </div>

      {/* ── Active Registered CLI Identities ────────────────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <UserCheck className="w-4 h-4 text-emerald-400" />
            <span>Active CLI Agent Identities ({identities.length})</span>
          </div>
        }
        subtitle="Cryptographically fingerprinted session credentials"
      >
        <div className="divide-y divide-[#182338]">
          {identities.map((id) => (
            <div key={id.agent_id} className="py-3 flex items-center justify-between gap-4 text-xs font-mono">
              <div className="flex items-center gap-3">
                <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-slate-200">{id.cli_name}</span>
                    <span className="text-slate-500 text-[10px] font-mono">({id.agent_id.substring(0, 8)})</span>
                    {id.is_trusted && (
                      <span className="px-1.5 py-0.2 rounded bg-emerald-950/60 text-emerald-300 text-[9px] border border-emerald-500/30">
                        TRUSTED
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    Scopes: <span className="text-emerald-400 font-mono">{id.scopes.join(", ")}</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <span className="text-slate-500 text-[10px] hidden sm:inline">
                  Fingerprint: {id.fingerprint.substring(0, 16)}...
                </span>
                <button
                  onClick={() => handleRevokeIdentity(id.agent_id)}
                  className="px-2.5 py-1 rounded bg-red-950/40 hover:bg-red-900/60 text-red-300 border border-red-500/30 text-[11px] transition-colors"
                >
                  Revoke
                </button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* ── Interactive TrustGate Evaluation Playground ─────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <Play className="w-4 h-4 text-rose-400" />
            <span>TrustGate Pipeline Evaluation Playground</span>
          </div>
        }
        subtitle="Simulate and verify Member 4 authorization, sandboxing, and regulatory gates"
      >
        <form onSubmit={handleEvaluate} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-mono text-slate-400 mb-1">Acting Agent Identity</label>
              <select
                value={selectedAgentId}
                onChange={(e) => setSelectedAgentId(e.target.value)}
                className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
              >
                {identities.map((id) => (
                  <option key={id.agent_id} value={id.agent_id}>
                    {id.cli_name} ({id.agent_id.substring(0, 8)})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-mono text-slate-400 mb-1">Operation Type</label>
              <select
                value={evalOp}
                onChange={(e) => setEvalOp(e.target.value)}
                className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
              >
                <option value="execute">execute (Shell/CLI command)</option>
                <option value="read">read (Filesystem read)</option>
                <option value="write">write (Filesystem write)</option>
                <option value="git">git (Version control op)</option>
                <option value="secrets">secrets (Credential retrieval)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-mono text-slate-400 mb-1">Path Target (Optional)</label>
              <input
                type="text"
                value={evalPath}
                onChange={(e) => setEvalPath(e.target.value)}
                placeholder="e.g. src/cliverse/cli.py or /etc/passwd"
                className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-mono text-slate-400 mb-1">Command String</label>
            <input
              type="text"
              value={evalCmd}
              onChange={(e) => setEvalCmd(e.target.value)}
              placeholder="e.g. pytest tests/ or rm -rf / or curl http://..."
              className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
            />
          </div>

          <div className="flex flex-wrap gap-2 text-xs">
            <span className="text-slate-500 font-mono">Test Preset:</span>
            <button
              type="button"
              onClick={() => {
                setEvalCmd("git status");
                setEvalOp("execute");
              }}
              className="px-2 py-0.5 rounded bg-[#121c2e] hover:bg-[#1a2942] text-slate-300 font-mono"
            >
              Safe Git Status (ALLOW)
            </button>
            <button
              type="button"
              onClick={() => {
                setEvalCmd("rm -rf /");
                setEvalOp("execute");
              }}
              className="px-2 py-0.5 rounded bg-red-950/40 hover:bg-red-900/60 text-red-300 font-mono border border-red-500/30"
            >
              Destructive rm -rf (BLOCK)
            </button>
            <button
              type="button"
              onClick={() => {
                setEvalCmd("python process_biometric_data.py");
                setEvalOp("execute");
              }}
              className="px-2 py-0.5 rounded bg-amber-950/40 hover:bg-amber-900/60 text-amber-300 font-mono border border-amber-500/30"
            >
              Biometric Data Task (WARN)
            </button>
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={isEvaluating}
              className="px-5 py-2.5 bg-rose-600 hover:bg-rose-500 text-slate-950 font-bold text-xs rounded-xl flex items-center gap-2 shadow-[0_0_15px_rgba(244,63,94,0.3)] transition-all disabled:opacity-50"
            >
              <span>{isEvaluating ? "Evaluating..." : "Run TrustGate Evaluation"}</span>
            </button>
          </div>
        </form>

        {/* Evaluation Output */}
        {evalResult && (
          <div className="mt-4 pt-4 border-t border-[#1a253c] space-y-3 animate-in fade-in duration-200">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-slate-400">DECISION:</span>
                <StatusBadge status={evalResult.decision} size="md" />
                <span className="text-xs font-mono text-slate-400 ml-2">RISK:</span>
                <span className="text-xs font-bold font-mono text-slate-200">{evalResult.risk_level}</span>
              </div>
              <span className="text-xs font-mono text-slate-400">
                Allowed for Execution:{" "}
                <span className={evalResult.allowed ? "text-emerald-400 font-bold" : "text-red-400 font-bold"}>
                  {String(evalResult.allowed).toUpperCase()}
                </span>
              </span>
            </div>

            <p className="text-xs text-slate-300 bg-[#080d19] p-3 rounded-lg border border-[#18233a] font-mono">
              {evalResult.reason}
            </p>

            {evalResult.warnings.length > 0 && (
              <div className="p-3 bg-amber-950/30 border border-amber-500/30 rounded-lg space-y-1">
                <span className="text-[10px] font-mono text-amber-400 uppercase block font-bold">
                  REGULATORY WARNINGS DETECTED:
                </span>
                {evalResult.warnings.map((w, idx) => (
                  <div key={idx} className="text-xs text-amber-200 font-mono">
                    • {w}
                  </div>
                ))}
              </div>
            )}

            {evalResult.requires_user_confirmation && (
              <div className="p-3 bg-[#131b2c] border border-amber-500/40 rounded-lg flex items-center justify-between gap-4">
                <div>
                  <span className="text-xs font-bold text-amber-300 block">EXPLICIT HUMAN CONFIRMATION GATE</span>
                  <span className="text-[11px] font-mono text-slate-400">
                    Token: {confirmToken}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={handleConfirm}
                  disabled={isConfirming}
                  className="px-4 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs rounded-lg transition-all shadow-[0_0_12px_rgba(245,158,11,0.3)] disabled:opacity-50"
                >
                  {isConfirming ? "Confirming..." : "Confirm & Authorize"}
                </button>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* ── Tamper-Evident Audit Trail ──────────────────────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <FileCheck2 className="w-4 h-4 text-emerald-400" />
            <span>Cryptographic Audit Ledger ({auditEvents.length} events)</span>
          </div>
        }
        subtitle="SHA-256 chained event log with verification proof"
        action={
          <button
            onClick={fetchSecurityData}
            className="text-xs text-emerald-400 hover:text-emerald-300 font-medium flex items-center gap-1"
          >
            <RotateCw className="w-3 h-3" />
            <span>Re-verify Chain</span>
          </button>
        }
      >
        <div className="divide-y divide-[#182338] max-h-80 overflow-y-auto pr-1">
          {isLoading ? (
            <div className="py-8 text-center text-slate-500 font-mono text-xs">
              Verifying cryptographic audit chain...
            </div>
          ) : auditEvents.length === 0 ? (
            <div className="py-8 text-center text-slate-500 font-mono text-xs">
              No audit events recorded yet.
            </div>
          ) : (
            auditEvents.map((evt) => (
              <div key={evt.event_id} className="py-2.5 flex items-center justify-between gap-4 text-xs font-mono">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="px-1.5 py-0.5 rounded bg-[#10192a] text-[10px] text-slate-400 border border-slate-800">
                      {evt.source}
                    </span>
                    <span className="font-semibold text-slate-200 truncate">{evt.summary}</span>
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5 truncate">
                    Hash: {evt.hash ? evt.hash.substring(0, 24) + "..." : "Initial root"}
                  </div>
                </div>

                <div className="flex items-center gap-3 flex-shrink-0">
                  <StatusBadge status={evt.decision || "ALLOW"} size="sm" showIcon={false} />
                  <span className="text-[11px] text-slate-500">
                    {new Date(evt.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </Card>

      {/* ── Register Agent Modal ────────────────────────────────────────── */}
      <Modal
        isOpen={registerModalOpen}
        onClose={() => setRegisterModalOpen(false)}
        title="Register AI CLI Agent Identity"
        subtitle="Creates an authenticated session token for a target CLI"
      >
        <form onSubmit={handleRegisterIdentity} className="space-y-4">
          <div>
            <label className="block text-xs font-mono text-slate-300 mb-1">CLI Provider Name</label>
            <input
              type="text"
              value={newCliName}
              onChange={(e) => setNewCliName(e.target.value)}
              placeholder="e.g. claude-cli, gemini-cli, copilot-cli"
              className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-mono text-slate-300 mb-1">Granted Scopes (Comma-separated)</label>
            <input
              type="text"
              value={newScopes}
              onChange={(e) => setNewScopes(e.target.value)}
              placeholder="read, write, git, execute"
              className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
            />
            <p className="text-[11px] text-slate-500 mt-1 font-mono">
              Standard trusted scopes: read, write, git, execute.
            </p>
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setRegisterModalOpen(false)}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isRegistering || !newCliName.trim()}
              className="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-slate-950 text-xs font-bold transition-all shadow-[0_0_15px_rgba(244,63,94,0.3)] disabled:opacity-50"
            >
              {isRegistering ? "Registering..." : "Register Agent"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
