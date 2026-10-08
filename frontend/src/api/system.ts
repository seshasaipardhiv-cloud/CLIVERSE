import { api } from "./client";
import type { SystemHealth, ProjectsResponse } from "../types";

export const systemApi = {
  getHealth: () => api.get<SystemHealth>("/api/health"),
  getProjects: () => api.get<ProjectsResponse>("/api/projects"),
  selectProject: (projectId: string, cliName?: string) =>
    api.post<{ status: string; project_id: string; cli_name: string }>("/api/projects/select", {
      project_id: projectId,
      cli_name: cliName,
    }),
};
