import React, { useState } from "react";
import { useApp } from "../context/AppContext";
import { Card } from "../components/Card";
import { StatusBadge } from "../components/StatusBadge";
import { Activity, Search, Radio } from "lucide-react";

export const ActivityPage: React.FC = () => {
  const { recentActivities } = useApp();
  const [sourceFilter, setSourceFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  const filteredActivities = recentActivities.filter((evt) => {
    if (sourceFilter !== "ALL" && evt.source.toUpperCase() !== sourceFilter.toUpperCase()) {
      return false;
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        evt.summary.toLowerCase().includes(q) ||
        evt.event_type.toLowerCase().includes(q) ||
        evt.source.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const sources = ["ALL", "MEMORY", "RULES", "LAYA", "MEMBER1_PLANNING", "SECURITY", "TRUSTGATE", "GIT_RECOVERY", "SESSION", "SYSTEM"];

  return (
    <div className="space-y-6">
      {/* ── Page Header ─────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#1b253b] pb-5">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="w-6 h-6 text-emerald-400" />
            <h1 className="text-xl font-bold tracking-tight text-slate-100">
              Live Activity Stream & Telemetry Ledger
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Real-time Server-Sent Events (SSE) telemetry feed of all subsystem operations across CLIVERSE
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-500/30 px-3 py-1.5 rounded-lg shadow-[0_0_12px_rgba(16,185,129,0.15)]">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
          <span>SSE LIVE BROADCAST CONNECTED</span>
        </div>
      </div>

      {/* ── Filters & Search ────────────────────────────────────────────── */}
      <Card>
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search activity events by keyword, event type, or summary..."
              className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg pl-10 pr-4 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-emerald-500"
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5 pt-3 mt-3 border-t border-[#1a253c] text-xs">
          <span className="text-slate-500 font-mono py-1 pr-1 text-[11px]">Filter Source:</span>
          {sources.map((s) => (
            <button
              key={s}
              onClick={() => setSourceFilter(s)}
              className={`px-2.5 py-1 rounded-md font-mono text-[11px] transition-colors ${
                sourceFilter === s
                  ? "bg-emerald-600 text-slate-950 font-bold shadow-[0_0_10px_rgba(16,185,129,0.3)]"
                  : "bg-[#0f1728] text-slate-400 hover:text-slate-200 border border-slate-800"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </Card>

      {/* ── Event Stream List ───────────────────────────────────────────── */}
      <Card
        title={
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-emerald-400" />
            <span>Chronological Event Stream ({filteredActivities.length})</span>
          </div>
        }
      >
        <div className="divide-y divide-[#182338]">
          {filteredActivities.length === 0 ? (
            <div className="py-12 text-center text-xs text-slate-500 font-mono">
              No activity events match the current filter criteria.
            </div>
          ) : (
            filteredActivities.map((evt) => (
              <div
                key={evt.event_id}
                className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-mono hover:bg-[#0b101e]/60 px-2 rounded-lg transition-colors"
              >
                <div className="flex items-start gap-3 min-w-0">
                  <span className="px-2 py-0.5 rounded bg-[#10192a] text-[10px] text-slate-300 border border-slate-800 font-bold uppercase flex-shrink-0 mt-0.5">
                    {evt.source}
                  </span>
                  <div>
                    <div className="text-slate-100 font-semibold">{evt.summary}</div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                      Event: <span className="text-slate-400">{evt.event_type}</span> | ID:{" "}
                      <span className="text-slate-400">{evt.event_id}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3 flex-shrink-0 self-end sm:self-center">
                  <StatusBadge status={evt.status} size="sm" showIcon={false} />
                  <span className="text-[11px] text-slate-400">
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
