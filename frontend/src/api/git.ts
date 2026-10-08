import { api } from "./client";
import type { GitStatusResponse, GitCommitItem, GitDiffResponse } from "../types";

export interface UndoPreviewResponse {
  session_id: string;
  target_commit: string;
  changed_paths: string[];
}

export interface UndoResultResponse {
  session_id: string;
  reverted_commit: string;
  recovery_commit: string;
  changed_paths: string[];
  authorization_decision: string;
}

export const gitApi = {
  getStatus: () => api.get<GitStatusResponse>("/api/git/status"),

  getDiff: () => api.get<GitDiffResponse>("/api/git/diff"),

  getHistory: (limit: number = 20) => api.get<GitCommitItem[]>(`/api/git/history?limit=${limit}`),

  previewUndo: (sessionId: string) =>
    api.get<UndoPreviewResponse>(`/api/git/recovery/preview/${encodeURIComponent(sessionId)}`),

  executeUndo: (sessionId: string, identity: string = "claude-cli", confirmed: boolean = true) =>
    api.post<UndoResultResponse>("/api/git/recovery/undo", {
      session_id: sessionId,
      identity,
      confirmed,
    }),
};
