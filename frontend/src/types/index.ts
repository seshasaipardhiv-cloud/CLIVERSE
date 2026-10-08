// Comprehensive TypeScript Interfaces for CLIVERSE Control Center

export type SubsystemStatusType = "OK_WITH_RESULTS" | "OK_EMPTY" | "ERROR" | "READY" | "ACTIVE" | "CLEAN" | "MODIFIED";

export type RuleDecisionType = "ALLOW" | "WARN" | "REQUIRE" | "ASK" | "DENY" | "UNKNOWN";

export type RuleScopeType = "global" | "project" | "cli" | "task";

export type RuleEffectType = "allow" | "warn" | "require" | "ask" | "deny";

export interface SystemHealth {
  status: "HEALTHY" | "DEGRADED" | "ERROR";
  timestamp: string;
  active_project: string;
  active_cli: string;
  subsystems: {
    memory: {
      status: SubsystemStatusType;
      chunks_count: number;
      provider: string;
    };
    rules: {
      status: SubsystemStatusType;
      rules_count: number;
    };
    laya: {
      status: SubsystemStatusType;
      planner: string;
    };
    security: {
      status: SubsystemStatusType;
      mode: string;
      active_identities: number;
      audit_chain_valid: boolean;
    };
    git: {
      status: "CLEAN" | "MODIFIED";
      branch: string;
    };
  };
}

export interface ProjectItem {
  id: string;
  name: string;
  root: string;
}

export interface ProjectsResponse {
  active_project: string;
  active_cli: string;
  available_projects: ProjectItem[];
  available_clis: string[];
}

export interface MemorySearchResultItem {
  record_id: string;
  chunk_id: string;
  content: string;
  source_path: string;
  source_type: string;
  start_line: number;
  end_line: number;
  score: number;
  tags?: string[];
  metadata?: Record<string, unknown>;
}

export interface MemorySearchResponse {
  status: "OK_WITH_RESULTS" | "OK_EMPTY" | "ERROR";
  query: string;
  project_id: string;
  count: number;
  error?: string;
  results: MemorySearchResultItem[];
}

export interface MemoryStatsResponse {
  project_id: string;
  stats: {
    total_records: number;
    total_chunks: number;
    db_path: string;
  };
  embedding_model: string;
  embedding_dimension: number;
}

export interface RuleItem {
  rule_id: string;
  name: string;
  description: string;
  scope: RuleScopeType;
  priority: number;
  effect: RuleEffectType;
  target?: string;
  is_mandatory: boolean;
  version?: number;
  project_id?: string | null;
  cli_name?: string | null;
  conditions?: Array<{
    field: string;
    operator: string;
    value: unknown;
  }>;
}

export interface RuleResolutionResponse {
  task: string;
  project_id: string;
  cli_name: string;
  winning_decision: RuleDecisionType;
  applicable_rules: RuleItem[];
  winning_rules: RuleItem[];
  conflicts: Array<{
    rule_a_id: string;
    rule_b_id: string;
    nature: string;
    winning_rule_id: string;
    reason: string;
  }>;
  explanation_trace: string[];
}

export interface ContextItemResponse {
  content: string;
  source: string;
  source_path: string;
  start_line: number;
  end_line: number;
  relevance_score: number;
  source_type: string;
}

export interface LayaIntelligenceResponse {
  task_text: string;
  project_id: string;
  cli_name: string;
  memory_status: SubsystemStatusType;
  rules_status: SubsystemStatusType;
  rule_decision: RuleDecisionType;
  rule_explanations: string[];
  retrieved_context_items: ContextItemResponse[];
  applicable_rules: RuleItem[];
  winning_rules: RuleItem[];
  conflicts: Array<{
    rule_a_id: string;
    rule_b_id: string;
    nature: string;
    winning_rule_id: string;
    reason: string;
  }>;
  combined_laya_context: string;
  metadata?: Record<string, unknown>;
}

export interface LayaPlanResponse {
  ready: boolean;
  task: {
    role: string;
    context: string;
    task: string;
    requirements: string[];
    constraints: string[];
    output: string;
  } | null;
  clarification_questions: string[];
  context_provenance: string[];
  applicable_rule_ids: string[];
}

export interface PipelineExecutionResponse {
  task: string;
  project_id: string;
  cli_name: string;
  pipeline: {
    memory: {
      status: SubsystemStatusType;
      chunks_retrieved: number;
    };
    rules: {
      status: SubsystemStatusType;
      decision: RuleDecisionType;
      winning_rules_count: number;
    };
    planning: {
      ready: boolean;
      applicable_rule_ids: string[];
    };
    trustgate: {
      allowed: boolean;
      decision: "ALLOW" | "WARN" | "BLOCK";
      risk_level: string;
      reason: string;
      requires_user_confirmation: boolean;
      confirmation_token?: string | null;
      warnings: string[];
    };
    execution: {
      status: string;
      command: string;
    };
  };
}

export interface AgentIdentity {
  agent_id: string;
  session_id: string;
  cli_name: string;
  is_trusted: boolean;
  scopes: string[];
  fingerprint: string;
  created_at: string;
}

export interface SecuritySummary {
  mode: string;
  active_identities_count: number;
  pending_confirmations_count: number;
  audit_events_count: number;
  security_alerts_count: number;
  chain_valid: boolean;
  chain_status: "VERIFIED" | "TAMPERED";
  chain_message: string;
  allowed_root?: string;
}

export interface AuditEventItem {
  event_id: string;
  timestamp: string;
  source: string;
  event_type: string;
  session_id?: string;
  agent_id?: string;
  decision?: string;
  risk_level?: string;
  summary: string;
  prev_hash?: string;
  hash?: string;
  details?: Record<string, unknown>;
}

export interface AuditTrailResponse {
  chain_valid: boolean;
  chain_status: "VERIFIED" | "TAMPERED";
  chain_message: string;
  count: number;
  events: AuditEventItem[];
}

export interface GitStatusResponse {
  project_root: string;
  branch: string;
  is_clean: boolean;
  changed_paths: string[];
  porcelain: string;
}

export interface GitCommitItem {
  commit_id: string;
  subject: string;
  session_id: string | null;
}

export interface GitDiffResponse {
  diff: string;
}

export interface SessionItem {
  session_id: string;
  project_root: string;
  user_request: string;
  status: "running" | "completed" | "failed" | "cancelled";
  created_at: string;
  updated_at: string;
}

export interface CoreEventItem {
  event_id: string;
  timestamp: string;
  source: string;
  event_type: string;
  summary: string;
  decision?: string | null;
  details: Record<string, unknown>;
}

export interface SessionDetailResponse {
  session: SessionItem;
  events: CoreEventItem[];
}

export interface ActivityItem {
  event_id: string;
  timestamp: string;
  source: string;
  event_type: string;
  summary: string;
  status: "success" | "warn" | "denied" | "error" | "empty";
  details?: Record<string, unknown>;
}
