import React, { useState, useEffect } from "react";
import { useApp } from "../context/AppContext";
import { Card } from "../components/Card";
import { StatusBadge } from "../components/StatusBadge";
import { Modal } from "../components/Modal";
import { sessionsApi } from "../api/sessions";
import type { SessionItem, CoreEventItem } from "../types";
import {
  Terminal,
  Plus,
  FileText,
  Activity,
} from "lucide-react";

export const SessionsPage: React.FC = () => {
  const { currentProject, showToast } = useApp();
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [sessionEvents, setSessionEvents] = useState<CoreEventItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Start Session Modal
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [newRequest, setNewRequest] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const fetchSessions = async () => {
    setIsLoading(true);
    try {
      const list = await sessionsApi.list(50);
      setSessions(list);
      if (list.length > 0 && !selectedSessionId) {
        setSelectedSessionId(list[0].session_id);
      }
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Session Fetch Error",
        message: err instanceof Error ? err.message : "Error listing sessions",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const fetchSessionDetails = async (id: string) => {
    try {
      const res = await sessionsApi.get(id);
      setSessionEvents(res.events);
    } catch {
      setSessionEvents([]);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, [currentProject]);

  useEffect(() => {
    if (selectedSessionId) {
      fetchSessionDetails(selectedSessionId);
    }
  }, [selectedSessionId]);

  const handleCreateSession = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRequest.trim()) return;

    setIsCreating(true);
    try {
      const s = await sessionsApi.create(newRequest.trim());
      showToast({
        type: "success",
        title: "Session Initialized",
        message: `Session ${s.session_id.substring(0, 8)} created in SQLite store`,
      });
      setCreateModalOpen(false);
      setNewRequest("");
      await fetchSessions();
      setSelectedSessionId(s.session_id);
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Session Creation Failed",
        message: err instanceof Error ? err.message : "Error starting session",
      });
    } finally {
      setIsCreating(false);
    }
  };

  const handleFinishSession = async (status: "completed" | "failed" | "cancelled") => {
    if (!selectedSessionId) return;
    try {
      await sessionsApi.finish(selectedSessionId, status);
      showToast({
        type: "info",
        title: "Session Updated",
        message: `Session marked as ${status}`,
      });
      fetchSessions();
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Update Failed",
        message: err instanceof Error ? err.message : "Error finishing session",
      });
    }
  };

  const selectedSession = sessions.find((s) => s.session_id === selectedSessionId);

  return (
    <div className="space-y-6">
      {/* ── Page Header ─────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#1b253b] pb-5">
        <div>
          <div className="flex items-center gap-2">
            <Terminal className="w-6 h-6 text-emerald-400" />
            <h1 className="text-xl font-bold tracking-tight text-slate-100">
              Persistent Sessions & Lifecycle Explorer
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Member 1 SessionStore: project-local SQLite session records and append-only event timelines
          </p>
        </div>

        <button
          onClick={() => setCreateModalOpen(true)}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-xs rounded-xl flex items-center gap-2 shadow-[0_0_15px_rgba(16,185,129,0.3)] transition-all"
        >
          <Plus className="w-4 h-4" />
          <span>Start New Session</span>
        </button>
      </div>

      {/* ── Session Split Layout ────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Sessions List */}
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs font-mono text-slate-400">
            <span>SAVED SESSIONS ({sessions.length})</span>
            <span>STORE: sessions.db</span>
          </div>

          <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
            {isLoading ? (
              <div className="p-8 text-center text-xs text-slate-500 bg-[#090e1c] border border-[#1a253c] rounded-xl font-mono">
                Loading sessions from SQLite database...
              </div>
            ) : sessions.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500 bg-[#090e1c] border border-[#1a253c] rounded-xl font-mono">
                No active sessions found.
              </div>
            ) : (
              sessions.map((s) => {
                const isSelected = s.session_id === selectedSessionId;
                return (
                  <div
                    key={s.session_id}
                    onClick={() => setSelectedSessionId(s.session_id)}
                    className={`p-3.5 rounded-xl border transition-all cursor-pointer ${
                      isSelected
                        ? "bg-[#0d1e16] border-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.15)]"
                        : "bg-[#0c1222] border-[#1c273e] hover:border-slate-600"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="font-mono text-xs font-bold text-emerald-400">
                        {s.session_id.substring(0, 8)}
                      </span>
                      <StatusBadge status={s.status} size="sm" showIcon={false} />
                    </div>

                    <p className="text-xs text-slate-200 line-clamp-2 mb-2 font-medium">
                      {s.user_request}
                    </p>

                    <div className="flex items-center justify-between text-[10px] font-mono text-slate-500">
                      <span>{new Date(s.created_at).toLocaleDateString()}</span>
                      <span>{new Date(s.created_at).toLocaleTimeString()}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Selected Session Detail & Event Timeline */}
        <div className="lg:col-span-2 space-y-4">
          {selectedSession ? (
            <>
              {/* Session Overview Card */}
              <Card
                title={
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-emerald-400" />
                    <span>Session: {selectedSession.session_id}</span>
                  </div>
                }
                action={
                  <div className="flex items-center gap-2">
                    <StatusBadge status={selectedSession.status} size="sm" />
                    {selectedSession.status === "running" && (
                      <button
                        onClick={() => handleFinishSession("completed")}
                        className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-[11px] rounded transition-colors"
                      >
                        Complete Session
                      </button>
                    )}
                  </div>
                }
              >
                <div className="space-y-3 font-mono text-xs">
                  <div className="p-3 bg-[#0a0f1d] rounded-lg border border-[#1a253c]">
                    <span className="text-[10px] text-slate-500 uppercase block mb-1">
                      USER REQUEST PROMPT:
                    </span>
                    <span className="text-slate-200 font-sans">{selectedSession.user_request}</span>
                  </div>

                  <div className="grid grid-cols-2 gap-3 text-[11px]">
                    <div>
                      <span className="text-slate-500">Created:</span>{" "}
                      <span className="text-slate-300">{new Date(selectedSession.created_at).toLocaleString()}</span>
                    </div>
                    <div>
                      <span className="text-slate-500">Last Updated:</span>{" "}
                      <span className="text-slate-300">{new Date(selectedSession.updated_at).toLocaleString()}</span>
                    </div>
                  </div>
                </div>
              </Card>

              {/* Event Timeline */}
              <Card
                title={
                  <div className="flex items-center gap-2">
                    <Activity className="w-4 h-4 text-emerald-400" />
                    <span>Append-Only Event Timeline ({sessionEvents.length})</span>
                  </div>
                }
                subtitle="Lifecycle events logged by Member 1 SessionStore"
              >
                {sessionEvents.length === 0 ? (
                  <div className="py-8 text-center text-xs text-slate-500 font-mono">
                    No discrete events recorded for this session yet.
                  </div>
                ) : (
                  <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
                    {sessionEvents.map((evt, idx) => (
                      <div
                        key={evt.event_id || idx}
                        className="p-3 bg-[#090e1c] border border-[#19243a] rounded-lg space-y-1 font-mono text-xs"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="px-1.5 py-0.2 rounded bg-[#131d31] text-[10px] text-slate-400 border border-slate-800">
                              {evt.source}
                            </span>
                            <span className="font-bold text-slate-200">{evt.event_type}</span>
                          </div>
                          {evt.decision && <StatusBadge status={evt.decision} size="sm" showIcon={false} />}
                        </div>

                        <p className="text-slate-300 font-sans text-xs">{evt.summary}</p>

                        <div className="text-[10px] text-slate-500">
                          {new Date(evt.timestamp).toLocaleTimeString()}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </>
          ) : (
            <div className="p-12 text-center text-xs text-slate-500 font-mono bg-[#090e1c] border border-[#1a253c] rounded-xl">
              Select a session from the left to view details and history.
            </div>
          )}
        </div>
      </div>

      {/* ── Start Session Modal ─────────────────────────────────────────── */}
      <Modal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title="Start New Development Session"
        subtitle="Initializes a persistent session in Member 1 SessionStore"
      >
        <form onSubmit={handleCreateSession} className="space-y-4">
          <div>
            <label className="block text-xs font-mono text-slate-300 mb-1">User Task / Goal</label>
            <textarea
              rows={3}
              value={newRequest}
              onChange={(e) => setNewRequest(e.target.value)}
              placeholder="e.g. Implement authentication middleware and run security scan"
              className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg p-3 text-xs font-mono text-slate-200 focus:outline-none"
              required
            />
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
              disabled={isCreating || !newRequest.trim()}
              className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-bold transition-all shadow-[0_0_15px_rgba(16,185,129,0.3)] disabled:opacity-50"
            >
              {isCreating ? "Creating..." : "Start Session"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
