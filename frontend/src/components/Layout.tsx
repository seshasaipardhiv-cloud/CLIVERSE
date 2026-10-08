import React from "react";
import { useApp } from "../context/AppContext";
import { StatusBadge } from "./StatusBadge";
import { ToastContainer } from "./ToastContainer";
import {
  LayoutDashboard,
  Brain,
  Database,
  ShieldAlert,
  GitBranch,
  Terminal,
  Activity,
  Layers,
  RefreshCw,
  FolderGit2,
  ChevronDown,
} from "lucide-react";

export type TabId =
  | "overview"
  | "providers"
  | "laya"
  | "memory"
  | "rules"
  | "security"
  | "git"
  | "sessions"
  | "activity";

interface LayoutProps {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ activeTab, onTabChange, children }) => {
  const {
    health,
    projectsData,
    currentProject,
    currentCli,
    setCurrentProject,
    setCurrentCli,
    refreshHealth,
    isLoading,
  } = useApp();

  const navItems: Array<{ id: TabId; label: string; icon: React.FC<{ className?: string }> }> = [
    { id: "overview", label: "Command Center", icon: LayoutDashboard },
    { id: "providers", label: "CLI Providers", icon: Terminal },
    { id: "laya", label: "Laya Workspace", icon: Brain },
    { id: "memory", label: "Memory Explorer", icon: Database },
    { id: "rules", label: "Rules Intelligence", icon: Layers },
    { id: "security", label: "Security & Trust", icon: ShieldAlert },
    { id: "git", label: "Git & Recovery", icon: GitBranch },
    { id: "sessions", label: "Sessions", icon: FolderGit2 },
    { id: "activity", label: "Live Activity", icon: Activity },
  ];

  return (
    <div className="min-h-screen bg-[#070b14] text-slate-100 flex flex-col font-sans selection:bg-emerald-500/20 selection:text-emerald-300">
      {/* ── Top Header Command Center ───────────────────────────────────── */}
      <header className="sticky top-0 z-40 bg-[#0a0f1d]/90 backdrop-blur-md border-b border-[#1b253b]">
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          {/* Logo & Platform Info */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-500 to-emerald-700 flex items-center justify-center shadow-[0_0_15px_rgba(16,185,129,0.3)]">
                <Brain className="w-5 h-5 text-slate-950 font-bold" />
              </div>
              <div>
                <span className="font-extrabold tracking-wider text-base text-slate-100">
                  CLIVERSE
                </span>
                <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-[#162136] text-slate-400 font-mono border border-slate-700">
                  AI OS v2.0
                </span>
              </div>
            </div>

            <div className="hidden lg:flex items-center gap-2 border-l border-slate-800 pl-4 ml-2">
              <div className="flex items-center gap-1.5 text-xs text-slate-400 font-mono">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>SYSTEM NOMINAL</span>
              </div>
            </div>
          </div>

          {/* Project & CLI Selectors */}
          <div className="flex items-center gap-3">
            {/* Project Switcher */}
            <div className="flex items-center gap-2 bg-[#0d1424] border border-[#1e2a42] rounded-lg px-3 py-1.5 hover:border-slate-600 transition-colors">
              <FolderGit2 className="w-4 h-4 text-emerald-400" />
              <div className="flex flex-col text-left">
                <span className="text-[10px] uppercase font-mono tracking-wider text-slate-500">
                  Project Workspace
                </span>
                <div className="relative flex items-center">
                  <select
                    value={currentProject}
                    onChange={(e) => setCurrentProject(e.target.value)}
                    className="bg-transparent text-xs font-semibold text-slate-200 pr-5 focus:outline-none cursor-pointer appearance-none"
                    aria-label="Select active project workspace"
                  >
                    {projectsData?.available_projects.map((p) => (
                      <option key={p.id} value={p.id} className="bg-[#0e1627] text-slate-200">
                        {p.name} ({p.id})
                      </option>
                    )) || <option value="cliverse-core">CLIVERSE Core</option>}
                  </select>
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400 absolute right-0 pointer-events-none" />
                </div>
              </div>
            </div>

            {/* Target CLI Switcher */}
            <div className="flex items-center gap-2 bg-[#0d1424] border border-[#1e2a42] rounded-lg px-3 py-1.5 hover:border-slate-600 transition-colors">
              <Terminal className="w-4 h-4 text-emerald-400" />
              <div className="flex flex-col text-left">
                <span className="text-[10px] uppercase font-mono tracking-wider text-slate-500">
                  Target CLI
                </span>
                <div className="relative flex items-center">
                  <select
                    value={currentCli}
                    onChange={(e) => setCurrentCli(e.target.value)}
                    className="bg-transparent text-xs font-semibold text-slate-200 pr-5 focus:outline-none cursor-pointer appearance-none font-mono"
                    aria-label="Select target CLI provider"
                  >
                    {projectsData?.available_clis.map((cli) => (
                      <option key={cli} value={cli} className="bg-[#0e1627] text-slate-200">
                        {cli}
                      </option>
                    )) || <option value="claude-cli">claude-cli</option>}
                  </select>
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400 absolute right-0 pointer-events-none" />
                </div>
              </div>
            </div>

            {/* Refresh Button */}
            <button
              onClick={() => refreshHealth()}
              disabled={isLoading}
              className="p-2 rounded-lg bg-[#0e1627] border border-[#1e2a42] text-slate-400 hover:text-slate-100 hover:border-slate-600 transition-all disabled:opacity-50"
              title="Refresh system state"
              aria-label="Refresh system state"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin text-emerald-400" : ""}`} />
            </button>
          </div>
        </div>

        {/* ── Primary Navigation Bar ──────────────────────────────────────── */}
        <div className="border-t border-[#162035] bg-[#080d19]/80 px-4 sm:px-6">
          <div className="max-w-[1600px] mx-auto flex items-center justify-between overflow-x-auto no-scrollbar">
            <nav className="flex items-center space-x-1 py-1.5" role="tablist">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => onTabChange(item.id)}
                    role="tab"
                    aria-selected={isActive}
                    className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-medium transition-all ${
                      isActive
                        ? "bg-[#142036] text-emerald-400 border border-emerald-500/30 shadow-[0_0_12px_rgba(16,185,129,0.15)]"
                        : "text-slate-400 hover:text-slate-200 hover:bg-[#0e172a]/60"
                    }`}
                  >
                    <Icon className={`w-4 h-4 ${isActive ? "text-emerald-400" : "text-slate-500"}`} />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </nav>

            {/* Subsystem Live Badges */}
            <div className="hidden xl:flex items-center gap-2 py-1 pl-4 text-xs font-mono">
              <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-[#0d1525] border border-slate-800 text-slate-400">
                <span className="text-[10px] text-slate-500">MEM:</span>
                <StatusBadge
                  status={health?.subsystems.memory.status || "OK_EMPTY"}
                  size="sm"
                  showIcon={false}
                />
              </div>
              <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-[#0d1525] border border-slate-800 text-slate-400">
                <span className="text-[10px] text-slate-500">RULES:</span>
                <StatusBadge
                  status={health?.subsystems.rules.status || "OK_EMPTY"}
                  size="sm"
                  showIcon={false}
                />
              </div>
              <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-[#0d1525] border border-slate-800 text-slate-400">
                <span className="text-[10px] text-slate-500">TRUST:</span>
                <StatusBadge
                  status={health?.subsystems.security.status || "ACTIVE"}
                  size="sm"
                  showIcon={false}
                />
              </div>
              <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-[#0d1525] border border-slate-800 text-slate-400">
                <span className="text-[10px] text-slate-500">GIT:</span>
                <StatusBadge
                  status={health?.subsystems.git.status || "CLEAN"}
                  size="sm"
                  showIcon={false}
                />
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* ── Main Content Area ───────────────────────────────────────────── */}
      <main className="flex-1 max-w-[1600px] w-full mx-auto p-4 sm:p-6 lg:p-8">
        {children}
      </main>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="border-t border-[#162035] bg-[#070c17] py-4 text-center text-xs text-slate-500">
        <div className="max-w-[1600px] mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-slate-400">CLIVERSE</span>
            <span>•</span>
            <span>AI CLI Intelligence & Governance Command Center</span>
          </div>
          <div className="flex items-center gap-4 font-mono text-[11px] text-slate-400">
            <span>M1: Core & Laya</span>
            <span>•</span>
            <span>M2: Memory & Rules</span>
            <span>•</span>
            <span>M3: Dashboard</span>
            <span>•</span>
            <span>M4: TrustGate</span>
          </div>
        </div>
      </footer>

      {/* Global Toast Notifications */}
      <ToastContainer />
    </div>
  );
};
