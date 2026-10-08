import { api } from "./client";
import type { SessionItem, SessionDetailResponse } from "../types";

export const sessionsApi = {
  list: (limit: number = 50) => api.get<SessionItem[]>(`/api/sessions?limit=${limit}`),

  create: (userRequest: string, projectRoot?: string) =>
    api.post<SessionItem>("/api/sessions", {
      user_request: userRequest,
      project_root: projectRoot,
    }),

  get: (sessionId: string) =>
    api.get<SessionDetailResponse>(`/api/sessions/${encodeURIComponent(sessionId)}`),

  finish: (sessionId: string, status: "completed" | "failed" | "cancelled" = "completed") =>
    api.post<{ session_id: string; status: string; updated_at: string }>(
      `/api/sessions/${encodeURIComponent(sessionId)}/finish`,
      { status }
    ),
};
