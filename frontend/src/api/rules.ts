import { api } from "./client";
import type { RuleItem, RuleResolutionResponse, RuleScopeType, RuleEffectType } from "../types";

export interface CreateRulePayload {
  rule_id: string;
  name: string;
  description: string;
  scope: RuleScopeType;
  priority: number;
  effect: RuleEffectType;
  target?: string;
  is_mandatory?: boolean;
  project_id?: string | null;
  cli_name?: string | null;
}

export const rulesApi = {
  list: (scope?: RuleScopeType, projectId?: string) => {
    const sp = new URLSearchParams();
    if (scope) sp.append("scope", scope);
    if (projectId) sp.append("project_id", projectId);
    const qs = sp.toString() ? `?${sp.toString()}` : "";
    return api.get<{ project_id: string; count: number; rules: RuleItem[] }>(`/api/rules${qs}`);
  },

  get: (ruleId: string) => api.get<RuleItem>(`/api/rules/${encodeURIComponent(ruleId)}`),

  create: (payload: CreateRulePayload) => api.post<RuleItem>("/api/rules", payload),

  delete: (ruleId: string) =>
    api.delete<{ status: string; rule_id: string }>(`/api/rules/${encodeURIComponent(ruleId)}`),

  resolve: (payload: { task: string; project_id?: string; cli_name?: string; task_metadata?: Record<string, unknown> }) =>
    api.post<RuleResolutionResponse>("/api/rules/resolve", payload),
};
