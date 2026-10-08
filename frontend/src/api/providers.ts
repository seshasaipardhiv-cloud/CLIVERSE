import { api } from "./client";

export interface CLIProviderInfo {
  provider_id: string;
  display_name: string;
  command_name: string;
  status: "INSTALLED" | "NOT_INSTALLED" | "UNAVAILABLE" | "ERROR";
  executable_path: string | null;
  version: string | null;
  capabilities: Record<string, unknown>;
  is_available: boolean;
  last_execution_at: string | null;
  last_status: string | null;
  error_message: string | null;
}

export interface ProviderRunRequest {
  provider: string;
  task: string;
  project_root?: string;
  confirm_warning?: boolean;
  timeout_seconds?: number;
}

export interface ProviderExecutionResponse {
  ok: boolean;
  session_id: string;
  provider_id: string;
  project_root: string;
  task: string;
  status: string;
  returncode: number;
  stdout: string;
  stderr: string;
  duration_seconds: number;
  memory_count: number;
  rule_decision: string;
  trust_gate_decision: string;
  trust_gate_reason: string;
  error_message?: string | null;
}

export const providersApi = {
  list: (refresh = false) => api.get<CLIProviderInfo[]>(`/api/providers${refresh ? "?refresh=true" : ""}`),
  refresh: () => api.post<CLIProviderInfo[]>("/api/providers/refresh"),
  get: (id: string) => api.get<CLIProviderInfo>(`/api/providers/${id}`),
  execute: (req: ProviderRunRequest) => api.post<ProviderExecutionResponse>("/api/providers/execute", req),
};
