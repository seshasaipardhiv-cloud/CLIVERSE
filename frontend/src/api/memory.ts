import { api } from "./client";
import type { MemorySearchResponse, MemoryStatsResponse } from "../types";

export interface SearchMemoryParams {
  query: string;
  project_id?: string;
  top_k?: number;
  min_score?: number;
  source_type?: string;
  session_id?: string;
}

export interface StoreMemoryPayload {
  content: string;
  project_id?: string;
  source_type?: string;
  source_path?: string;
  title?: string;
  tags?: string[];
  metadata?: Record<string, unknown>;
}

export const memoryApi = {
  getStats: (projectId?: string) => {
    const q = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return api.get<MemoryStatsResponse>(`/api/memory/stats${q}`);
  },

  search: (params: SearchMemoryParams) => {
    const sp = new URLSearchParams();
    sp.append("query", params.query);
    if (params.project_id) sp.append("project_id", params.project_id);
    if (params.top_k !== undefined) sp.append("top_k", String(params.top_k));
    if (params.min_score !== undefined) sp.append("min_score", String(params.min_score));
    if (params.source_type) sp.append("source_type", params.source_type);
    if (params.session_id) sp.append("session_id", params.session_id);

    return api.get<MemorySearchResponse>(`/api/memory/search?${sp.toString()}`);
  },

  store: (payload: StoreMemoryPayload) =>
    api.post<{ status: string; record_id: string; chunks_created: number; status_code: string }>(
      "/api/memory",
      payload
    ),

  delete: (recordId: string) =>
    api.delete<{ status: string; record_id: string }>(`/api/memory/${encodeURIComponent(recordId)}`),
};
