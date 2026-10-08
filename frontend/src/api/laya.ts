import { api } from "./client";
import type { LayaIntelligenceResponse, LayaPlanResponse, PipelineExecutionResponse } from "../types";

export interface IntelligencePayload {
  task: string;
  project_id?: string;
  cli_name?: string;
  top_k?: number;
  min_score?: number;
  context_budget_tokens?: number;
  task_metadata?: Record<string, unknown>;
}

export interface PlanPayload {
  task: string;
  role?: string;
  context?: string;
  requirements?: string[];
  constraints?: string[];
  output?: string;
  project_id?: string;
  cli_name?: string;
}

export interface ExecutePipelinePayload {
  task: string;
  command?: string;
  project_id?: string;
  cli_name?: string;
  user_confirmed?: boolean;
}

export const layaApi = {
  buildIntelligence: (payload: IntelligencePayload) =>
    api.post<LayaIntelligenceResponse>("/api/laya/intelligence", payload),

  planTask: (payload: PlanPayload) => api.post<LayaPlanResponse>("/api/laya/plan", payload),

  executePipeline: (payload: ExecutePipelinePayload) =>
    api.post<PipelineExecutionResponse>("/api/laya/execute", payload),
};
