import { api } from "./client";
import type { ActivityItem } from "../types";

export const activityApi = {
  list: (limit: number = 50) => api.get<ActivityItem[]>(`/api/activity?limit=${limit}`),

  subscribe: (onEvent: (event: ActivityItem) => void): (() => void) => {
    const eventSource = new EventSource("/api/activity/stream");

    eventSource.onmessage = (e) => {
      try {
        const parsed = JSON.parse(e.data) as ActivityItem;
        onEvent(parsed);
      } catch (err) {
        console.error("Failed to parse SSE event", err);
      }
    };

    eventSource.onerror = () => {
      // EventSource reconnects automatically
    };

    return () => {
      eventSource.close();
    };
  },
};
