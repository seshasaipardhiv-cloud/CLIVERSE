import React, { useState, useEffect } from "react";
import { useApp } from "../context/AppContext";
import { Card } from "../components/Card";
import { StatusBadge } from "../components/StatusBadge";
import { Modal } from "../components/Modal";
import { memoryApi } from "../api/memory";
import type { StoreMemoryPayload } from "../api/memory";
import type { MemorySearchResultItem, MemoryStatsResponse } from "../types";
import {
  Database,
  Search,
  Plus,
  Trash2,
  Tag,
  FileCode,
  FileText,
  MessageSquare,
  Bookmark,
  AlertCircle,
  HelpCircle,
} from "lucide-react";

export const MemoryExplorerPage: React.FC = () => {
  const { currentProject, showToast } = useApp();
  const [query, setQuery] = useState("architecture");
  const [sourceType, setSourceType] = useState<string>("");
  const [topK, setTopK] = useState(5);
  const [minScore, setMinScore] = useState(0.2);

  const [isLoading, setIsLoading] = useState(false);
  const [searchResults, setSearchResults] = useState<MemorySearchResultItem[]>([]);
  const [searchStatus, setSearchStatus] = useState<"IDLE" | "OK_WITH_RESULTS" | "OK_EMPTY" | "ERROR">("IDLE");
  const [stats, setStats] = useState<MemoryStatsResponse | null>(null);

  // Ingest Modal state
  const [ingestModalOpen, setIngestModalOpen] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [newSourcePath, setNewSourcePath] = useState("docs/custom-convention.md");
  const [newSourceType, setNewSourceType] = useState("doc");
  const [newTitle, setNewTitle] = useState("");
  const [newTags, setNewTags] = useState("convention, custom");
  const [isSubmittingIngest, setIsSubmittingIngest] = useState(false);

  // Selected result for detail drawer
  const [selectedResult, setSelectedResult] = useState<MemorySearchResultItem | null>(null);

  const fetchStats = async () => {
    try {
      const res = await memoryApi.getStats(currentProject);
      setStats(res);
    } catch {
      // Ignored
    }
  };

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    setIsLoading(true);
    try {
      const res = await memoryApi.search({
        query: query.trim(),
        project_id: currentProject,
        top_k: topK,
        min_score: minScore,
        source_type: sourceType || undefined,
      });

      setSearchResults(res.results);
      setSearchStatus(res.status);
    } catch (err: unknown) {
      setSearchStatus("ERROR");
      setSearchResults([]);
      showToast({
        type: "error",
        title: "Memory Search Error",
        message: err instanceof Error ? err.message : "Failed to query memory",
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    handleSearch();
  }, [currentProject]);

  const handleIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newContent.trim()) return;

    setIsSubmittingIngest(true);
    try {
      const payload: StoreMemoryPayload = {
        content: newContent.trim(),
        project_id: currentProject,
        source_path: newSourcePath.trim() || "manual_entry",
        source_type: newSourceType,
        title: newTitle.trim() || undefined,
        tags: newTags ? newTags.split(",").map((s) => s.trim()).filter(Boolean) : undefined,
      };

      const res = await memoryApi.store(payload);
      showToast({
        type: "success",
        title: "Knowledge Ingested",
        message: `Indexed ${res.chunks_created} chunk(s) with SHA-256 deduplication`,
      });

      setIngestModalOpen(false);
      setNewContent("");
      fetchStats();
      handleSearch();
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Ingestion Failed",
        message: err instanceof Error ? err.message : "Error ingesting memory",
      });
    } finally {
      setIsSubmittingIngest(false);
    }
  };

  const handleDelete = async (recordId: string) => {
    if (!confirm(`Are you sure you want to delete memory record ${recordId}?`)) return;

    try {
      await memoryApi.delete(recordId);
      showToast({
        type: "success",
        title: "Memory Deleted",
        message: `Record ${recordId} removed from SQLite store`,
      });
      if (selectedResult?.record_id === recordId) setSelectedResult(null);
      fetchStats();
      handleSearch();
    } catch (err: unknown) {
      showToast({
        type: "error",
        title: "Delete Failed",
        message: err instanceof Error ? err.message : "Error deleting record",
      });
    }
  };

  const getSourceIcon = (type: string) => {
    switch (type.toLowerCase()) {
      case "code":
        return <FileCode className="w-4 h-4 text-emerald-400" />;
      case "conversation":
        return <MessageSquare className="w-4 h-4 text-emerald-400" />;
      case "decision":
        return <Bookmark className="w-4 h-4 text-amber-400" />;
      default:
        return <FileText className="w-4 h-4 text-emerald-400" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* ── Page Header ─────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#1b253b] pb-5">
        <div>
          <div className="flex items-center gap-2">
            <Database className="w-6 h-6 text-emerald-400" />
            <h1 className="text-xl font-bold tracking-tight text-slate-100">
              Persistent Memory & Hybrid Retrieval Explorer
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Browse indexed chunks, verify source line provenance, and search SQLite vector store
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setIngestModalOpen(true)}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-xs rounded-xl flex items-center gap-2 shadow-[0_0_15px_rgba(16,185,129,0.2)] transition-all"
          >
            <Plus className="w-4 h-4" />
            <span>Ingest Document / Code</span>
          </button>
        </div>
      </div>

      {/* ── Storage Stats & Embedding Engine ────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <span className="text-[10px] font-mono text-slate-400 block mb-1">TOTAL INDEXED CHUNKS</span>
          <div className="text-2xl font-bold font-mono text-emerald-400">
            {stats?.stats.total_chunks ?? 0}
          </div>
          <p className="text-[11px] text-slate-500 mt-1 font-mono">
            {stats?.stats.total_records ?? 0} root memory records
          </p>
        </Card>

        <Card>
          <span className="text-[10px] font-mono text-slate-400 block mb-1">EMBEDDING VECTORIZER</span>
          <div className="text-base font-bold font-mono text-slate-100">
            {stats?.embedding_model || "cliverse-local-baseline-v1"}
          </div>
          <p className="text-[11px] text-slate-500 mt-1 font-mono">
            {stats?.embedding_dimension || 64}-dimensional hash-bucket projection
          </p>
        </Card>

        <Card>
          <span className="text-[10px] font-mono text-slate-400 block mb-1">PERSISTENCE STORAGE ENGINE</span>
          <div className="text-base font-bold font-mono text-slate-100">SQLite In-Memory / Disk</div>
          <p className="text-[11px] text-slate-500 mt-1 font-mono truncate">
            {stats?.stats.db_path || ".envcore/memory/cliverse_memory.db"}
          </p>
        </Card>
      </div>

      {/* ── Search & Filter Controls ─────────────────────────────────────── */}
      <Card>
        <form onSubmit={handleSearch} className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search semantic memory chunks by keyword or concept..."
                className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-xl pl-10 pr-4 py-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 font-mono"
              />
            </div>
            <button
              type="submit"
              disabled={isLoading || !query.trim()}
              className="px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-xs rounded-xl flex items-center justify-center gap-2 shadow-[0_0_15px_rgba(16,185,129,0.3)] transition-all disabled:opacity-50"
            >
              <Search className="w-4 h-4" />
              <span>{isLoading ? "Searching..." : "Search Memory"}</span>
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2 border-t border-[#1a253c] text-xs">
            <div>
              <label className="block text-slate-400 font-mono mb-1">Filter by Source Type</label>
              <select
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value)}
                className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-slate-200 font-mono focus:outline-none"
              >
                <option value="">All Types (doc, code, decision, session)</option>
                <option value="doc">Documentation (doc)</option>
                <option value="code">Source Code (code)</option>
                <option value="decision">Architecture Decision (decision)</option>
                <option value="conversation">Session Conversation (conversation)</option>
              </select>
            </div>

            <div>
              <div className="flex justify-between font-mono text-slate-400 mb-1">
                <span>Top-K Results: {topK}</span>
              </div>
              <input
                type="range"
                min={1}
                max={15}
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
                className="w-full accent-emerald-500 mt-2"
              />
            </div>

            <div>
              <div className="flex justify-between font-mono text-slate-400 mb-1">
                <span>Min Similarity Score: {minScore.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min={0.0}
                max={0.8}
                step={0.05}
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-full accent-emerald-500 mt-2"
              />
            </div>
          </div>
        </form>
      </Card>

      {/* ── Search Results List ─────────────────────────────────────────── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-slate-200">Retrieval Results</h3>
            {searchStatus !== "IDLE" && <StatusBadge status={searchStatus} size="sm" />}
          </div>
          <span className="text-xs font-mono text-slate-400">
            {searchResults.length} chunks returned
          </span>
        </div>

        {searchStatus === "OK_EMPTY" && (
          <div className="p-8 text-center bg-[#090e1c] border border-[#1a253c] rounded-xl space-y-2">
            <HelpCircle className="w-8 h-8 text-slate-500 mx-auto" />
            <h4 className="text-sm font-semibold text-slate-300">No relevant project memory found</h4>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              No chunks in project '{currentProject}' met the minimum similarity score of {minScore}.
              Try lowering the score threshold or entering alternate keywords.
            </p>
          </div>
        )}

        {searchStatus === "ERROR" && (
          <div className="p-8 text-center bg-[#180a0e] border border-red-500/30 rounded-xl space-y-2">
            <AlertCircle className="w-8 h-8 text-red-400 mx-auto" />
            <h4 className="text-sm font-semibold text-red-200">Memory Subsystem Error</h4>
            <p className="text-xs text-red-400/80 max-w-md mx-auto">
              The storage query failed. This is a real subsystem error and has not been masked as an empty state.
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 gap-3">
          {searchResults.map((hit) => {
            const isSelected = selectedResult?.chunk_id === hit.chunk_id;
            return (
              <div
                key={hit.chunk_id}
                onClick={() => setSelectedResult(hit)}
                className={`p-4 rounded-xl border transition-all cursor-pointer ${
                  isSelected
                    ? "bg-[#0d1e16] border-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.15)]"
                    : "bg-[#0c1222] border-[#1c273e] hover:border-slate-600"
                }`}
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    {getSourceIcon(hit.source_type)}
                    <span className="font-mono text-xs font-bold text-slate-200">
                      {hit.source_path}:{hit.start_line}-{hit.end_line}
                    </span>
                    <span className="px-2 py-0.5 rounded bg-[#101728] text-[10px] font-mono text-slate-400 border border-slate-800">
                      {hit.source_type}
                    </span>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5 font-mono text-xs">
                      <span className="text-slate-500 text-[10px]">RELEVANCE:</span>
                      <span className="font-bold text-emerald-400">{(hit.score * 100).toFixed(1)}%</span>
                    </div>

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(hit.record_id);
                      }}
                      className="p-1 rounded text-slate-500 hover:text-red-400 hover:bg-red-950/40 transition-colors"
                      title="Delete parent record"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <pre className="text-xs text-slate-300 font-mono bg-[#070b14] p-3 rounded-lg border border-slate-900 whitespace-pre-wrap max-h-36 overflow-y-auto">
                  {hit.content}
                </pre>

                {hit.tags && hit.tags.length > 0 && (
                  <div className="flex items-center gap-1.5 mt-3">
                    <Tag className="w-3 h-3 text-slate-500" />
                    <div className="flex flex-wrap gap-1">
                      {hit.tags.map((tag, i) => (
                        <span
                          key={i}
                          className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#141d30] text-slate-400 border border-slate-800"
                        >
                          #{tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Ingest New Memory Modal ─────────────────────────────────────── */}
      <Modal
        isOpen={ingestModalOpen}
        onClose={() => setIngestModalOpen(false)}
        title="Ingest New Knowledge Document"
        subtitle={`Stores document into SQLite database under project workspace '${currentProject}'`}
        maxWidth="xl"
      >
        <form onSubmit={handleIngest} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-mono text-slate-300 mb-1">Source Path</label>
              <input
                type="text"
                value={newSourcePath}
                onChange={(e) => setNewSourcePath(e.target.value)}
                placeholder="docs/guide.md or src/utils.py"
                className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-mono text-slate-300 mb-1">Source Type</label>
              <select
                value={newSourceType}
                onChange={(e) => setNewSourceType(e.target.value)}
                className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
              >
                <option value="doc">Documentation (doc)</option>
                <option value="code">Source Code (code)</option>
                <option value="decision">Decision Record (decision)</option>
                <option value="conversation">Conversation Turn (conversation)</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-mono text-slate-300 mb-1">Title (Optional)</label>
            <input
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="e.g., Code Review Guidelines"
              className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-mono text-slate-300 mb-1">Tags (Comma-separated)</label>
            <input
              type="text"
              value={newTags}
              onChange={(e) => setNewTags(e.target.value)}
              placeholder="e.g. standards, security, python"
              className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-mono text-slate-300 mb-1">Content to Ingest & Chunk</label>
            <textarea
              rows={6}
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              placeholder="Paste Markdown document, code snippet, or engineering conventions..."
              className="w-full bg-[#0a0f1d] border border-[#22304d] rounded-lg p-3 text-xs font-mono text-slate-200 focus:outline-none"
              required
            />
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setIngestModalOpen(false)}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmittingIngest || !newContent.trim()}
              className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-bold transition-all shadow-[0_0_15px_rgba(16,185,129,0.3)] disabled:opacity-50"
            >
              {isSubmittingIngest ? "Chunking & Storing..." : "Ingest into Memory"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
