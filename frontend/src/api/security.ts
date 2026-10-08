import { api } from "./client";
import type { SecuritySummary, AgentIdentity, AuditTrailResponse } from "../types";

export interface SecurityEvaluationPayload {
  agent_id: string;
  operation: string;
  command?: string;
  path?: string;
  context?: Record<string, unknown>;
  user_confirmed?: boolean;
}

export interface SecurityEvaluationResult {
  allowed: boolean;
  decision: "ALLOW" | "WARN" | "BLOCK";
  risk_level: string;
  reason: string;
  requires_user_confirmation: boolean;
  confirmation_token?: string | null;
  warnings: string[];
  audit_event_id?: string | null;
}

export const securityApi = {
  getSummary: () => api.get<SecuritySummary>("/api/security/summary"),

  listIdentities: () => api.get<AgentIdentity[]>("/api/security/identities"),

  registerIdentity: (cliName: string, scopes?: string[]) =>
    api.post<AgentIdentity>("/api/security/identities", { cli_name: cliName, scopes }),

  revokeIdentity: (agentId: string) =>
    api.delete<{ status: string; agent_id: string }>(`/api/security/identities/${encodeURIComponent(agentId)}`),

  evaluateOperation: (payload: SecurityEvaluationPayload) =>
    api.post<SecurityEvaluationResult>("/api/security/evaluate", payload),

  confirmWarning: (confirmationToken: string) =>
    api.post<SecurityEvaluationResult>("/api/security/confirm", {
      confirmation_token: confirmationToken,
    }),

  getAuditTrail: (limit: number = 100) => api.get<AuditTrailResponse>(`/api/security/audit?limit=${limit}`),

  getPolicies: () => api.get<Array<Record<string, unknown>>>("/api/security/policies"),
};
