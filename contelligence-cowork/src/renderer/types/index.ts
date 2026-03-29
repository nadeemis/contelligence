// ── Sessions ──────────────────────
export interface SessionRecord {
  id: string;
  instruction: string;
  status: "active" | "completed" | "failed" | "cancelled" | "waiting_approval";
  model: string;
  created_at: string;
  updated_at: string;
  user_id: string;
  options: InstructOptions;
  trigger_reason: string | null;
  summary: string | null;
  schedule_id: string | null;
  metrics: SessionMetrics;
}

export interface SessionMetrics {
  total_tool_calls: number;
  total_duration_seconds: number;
  documents_processed: number;
  errors_encountered: number;
  input_tokens?: number;
  output_tokens?: number;
  cache_read_tokens?: number;
  cache_write_tokens?: number;
  total_tokens_used: number;
  model?: string | null;
  cost?: number;
  outputs_produced?: number;
}

export interface ConversationTurn {
  session_id: string;
  sequence: number;
  role: "user" | "assistant" | "tool";
  prompt: string | null;
  content: string | null;
  reasoning: string | null;
  tool_call: ToolCallRecord | null;
  timestamp: string;
}

export interface ToolCallRecord {
  tool_name: string;
  parameters: Record<string, any>;
  result?: any | null;
  result_blob_ref?: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number;
  status: string | null;
  error?: string | null;
}

export interface OutputArtifact {
  id: string;
  session_id: string;
  file_name: string;
  content_type: string;
  size_bytes: number;
  blob_url: string;
  created_at: string;
}

// ── Schedules ─────────────────────
export interface ScheduleRecord {
  id: string;
  name: string;
  description: string | null;
  instruction: string;
  trigger: TriggerConfig;
  options: InstructOptions;
  tags: string[];
  status: "active" | "paused" | "error" | "deleted";
  created_at: string;
  updated_at: string;
  created_by: string | null;
  last_run_at: string | null;
  last_run_session_id: string | null;
  last_run_status: string | null;
  next_run_at: string | null;
  total_runs: number;
  consecutive_failures: number;
  webhook_id: string | null;
  webhook_url: string | null;
}

export type TriggerType = "cron" | "interval" | "event" | "webhook";

export interface TriggerConfig {
  type: TriggerType;
  cron?: string;
  timezone?: string;
  interval_minutes?: number;
  event_source?: string;
  event_filter?: string;
  webhook_secret?: string;
}

export interface CreateScheduleRequest {
  name: string;
  description?: string;
  instruction: string;
  trigger: TriggerConfig;
  options?: InstructOptions;
  tags?: string[];
  enabled?: boolean;
}

export type UpdateScheduleRequest = Partial<CreateScheduleRequest>;

export interface ScheduleRunRecord {
  id: string;
  schedule_id: string;
  session_id: string;
  triggered_at: string;
  trigger_reason: string;
  completed_at: string | null;
  status: "running" | "completed" | "failed" | "cancelled";
  summary: string | null;
  duration_seconds: number | null;
  tool_calls: number | null;
  documents_processed: number | null;
  errors: number | null;
}

// ── Dashboard ─────────────────────
export interface DashboardMetrics {
  total_sessions: number;
  active_sessions: number;
  completed_sessions: number;
  failed_sessions: number;
  total_tool_calls: number;
  total_documents_processed: number;
  avg_session_duration_seconds: number;
  error_rate: number;
  active_schedules: number;
  schedules_fired_today: number;
  sessions_by_day: { date: string; count: number }[];
  top_tools: { tool: string; calls: number }[];
  error_breakdown?: { type: string; count: number }[];
}

export interface ActivityEvent {
  timestamp: string;
  type: string;
  session_id: string | null;
  schedule_id: string | null;
  summary: string;
}

// ── Detailed Metrics ──────────────
export interface SessionMetricsDetail {
  token_usage_by_day: { date: string; input_tokens: number; output_tokens: number; cache_tokens: number; total_tokens: number; cost: number }[];
  duration_by_day: { date: string; avg_duration: number; min_duration: number; max_duration: number; session_count: number }[];
  status_by_day: { date: string; active: number; completed: number; failed: number; cancelled: number }[];
  documents_by_day: { date: string; documents_processed: number; outputs_produced: number; errors: number }[];
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_tokens: number;
  total_cost: number;
  avg_duration: number;
}

export interface ToolCallMetricsDetail {
  tool_usage: { tool_name: string; total_calls: number; success_count: number; error_count: number; avg_duration_ms: number }[];
  tool_calls_by_day: { date: string; count: number }[];
  tool_errors: { tool_name: string; error_count: number; last_error: string | null }[];
  tool_duration: { tool_name: string; avg_duration_ms: number; min_duration_ms: number; max_duration_ms: number }[];
  total_tool_calls: number;
  total_tool_errors: number;
}

export interface ScheduleMetricsDetail {
  schedule_overview: { name: string; status: string; total_runs: number; success_rate: number; last_run_at: string | null; next_run_at: string | null }[];
  runs_by_day: { date: string; runs: number; successes: number; failures: number }[];
  schedule_duration: { name: string; avg_duration: number; min_duration: number; max_duration: number }[];
  schedule_reliability: { name: string; consecutive_failures: number; success_rate: number; total_runs: number }[];
  total_runs: number;
  total_successes: number;
  total_failures: number;
}

export interface DetailedMetrics {
  sessions: SessionMetricsDetail;
  tool_calls: ToolCallMetricsDetail;
  schedules: ScheduleMetricsDetail;
}

export interface DailyDetailMetrics {
  date: string;
  sessions: { id: string; instruction: string; status: string; duration: number; tool_calls: number; tokens: number; cost: number; created_at: string }[];
  session_count: number;
  completed_count: number;
  failed_count: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost: number;
  avg_duration: number;
  min_duration: number;
  max_duration: number;
  tool_calls: { tool_name: string; status: string; duration_ms: number; session_id: string; error: string | null }[];
  total_tool_calls: number;
  total_tool_errors: number;
  schedule_runs: { schedule_id: string; name: string; session_id: string; status: string; duration: number | null; trigger_reason: string }[];
  total_schedule_runs: number;
}

// ── Admin ─────────────────────────
export interface AdminSettings {
  default_model: string;
  require_approval: boolean;
  default_timeout_minutes: number;
}

export interface TokenStatus {
  connected: boolean;
  masked_token: string | null;
  user: string | null;
  scopes: string[] | null;
  expires_at: string | null;
}

export interface TokenValidationResult {
  valid: boolean;
  error?: string;
  user?: string;
  scopes?: string[];
  expires_at?: string | null;
}

export interface InstructOptions {
  model?: string;
  require_approval?: boolean;
  persist_outputs?: boolean;
  timeout_minutes?: number;
  agents?: string[];
  skill_ids?: string[];
}

export interface HealthCheck {
  healthy: boolean;
  detail?: string;
}

export interface McpServerHealth {
  status: string;
  latency_ms?: number;
  error?: string;
}

export interface CopilotCliHealth {
  status: string;
  auth_type?: string;
  cli_version?: string;
}

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
  instance_id: string;
  active_sessions?: number;
  is_scheduler_leader?: boolean;
  copilot_cli?: CopilotCliHealth;
  mcp_servers?: Record<string, McpServerHealth>;
}

export interface EnvironmentInfo {
  storage: Record<string, string>;
  server: Record<string, string | number>;
  quotas: Record<string, number>;
  rate_limits: Record<string, number>;
  cache_retention: Record<string, boolean | number>;
  services: Record<string, boolean>;
  models: Record<string, string>;
  scaling: Record<string, number>;
}

// ── Agents ────────────────────────
export type AgentSource = "built-in" | "user-created";
export type AgentStatusType = "active" | "archived" | "draft";

export interface AgentDefinitionRecord {
  id: string;
  display_name: string;
  description: string;
  icon: string;
  prompt: string;
  tools: string[];
  model_override: string | null;
  max_tool_calls: number;
  timeout_seconds: number;
  tags: string[];
  bound_skills: string[];
  source: AgentSource;
  status: AgentStatusType;
  version: number;
  usage_count: number;
  created_at: string;
  updated_at: string | null;
  created_by: string | null;
}

export interface CreateAgentRequest {
  id: string;
  display_name: string;
  description: string;
  icon?: string;
  prompt: string;
  tools: string[];
  model?: string | null;
  max_tool_calls?: number;
  timeout_seconds?: number;
  tags?: string[];
  bound_skills?: string[];
  status?: AgentStatusType;
}

export interface UpdateAgentRequest {
  display_name?: string;
  description?: string;
  icon?: string;
  prompt?: string;
  tools?: string[];
  model?: string | null;
  max_tool_calls?: number;
  timeout_seconds?: number;
  tags?: string[];
  bound_skills?: string[];
  status?: AgentStatusType;
}

export interface AgentSummary {
  id: string;
  display_name: string;
  description?: string;
  icon?: string;
  tools?: string[];
  tags?: string[];
  source?: AgentSource;
  status: AgentStatusType;
  usage_count?: number;
  created_at: string;
  updated_at: string | null;
}

export interface ToolInfo {
  name: string;
  description: string;
  category: string;
}

// ── MCP Server Management ─────────
export interface McpServerEntry {
  name: string;
  disabled: boolean;
  config: Record<string, any>;
}

export interface McpServerHealthResult {
  key: string;
  status: string;
  transport: string;
  detail: string;
}

export interface AddMcpServerRequest {
  name: string;
  config: Record<string, any>;
}

export interface McpToolEntry {
  name: string;
  description: string;
  inputSchema: Record<string, any>;
}

export interface TestAgentRequest {
  instruction: string;
}

export interface TestAgentResponse {
  agent_id: string;
  system_prompt_preview: string;
  tool_count: number;
  estimated_tokens: number;
  warnings: string[];
}

// ── Skills ────────────────────────
export type SkillSource = "built-in" | "user-created" | "marketplace";
export type SkillStatusType = "active" | "disabled" | "draft";

export interface SkillRecord {
  id: string;
  name: string;
  description: string;
  license: string | null;
  compatibility: string | null;
  metadata: Record<string, string>;
  tags: string[];
  source: SkillSource;
  status: SkillStatusType;
  blob_prefix: string;
  version: number;
  usage_count: number;
  bound_to_agents: string[];
  created_at: string;
  updated_at: string | null;
  created_by: string | null;
  instructions: string | null;
  files: string[];
}

export interface CreateSkillRequest {
  name: string;
  description: string;
  license?: string | null;
  compatibility?: string | null;
  metadata?: Record<string, string>;
  tags?: string[];
  status?: SkillStatusType;
  instructions: string;
}

export interface UpdateSkillRequest {
  name?: string;
  description?: string;
  license?: string | null;
  compatibility?: string | null;
  metadata?: Record<string, string>;
  tags?: string[];
  status?: SkillStatusType;
  instructions?: string;
}

export interface SkillSummary {
  id: string;
  name: string;
  description: string;
  tags: string[];
  source: SkillSource;
  status: SkillStatusType;
  usage_count: number;
  bound_to_agents: string[];
  created_at: string;
  updated_at: string | null;
}

export interface SkillValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  parsed_name: string | null;
  parsed_description: string | null;
}

// ── Prompts ───────────────────────
export type PromptType = "system" | "agent";

export interface PromptResponse {
  id: string;
  prompt_type: PromptType;
  name: string;
  content: string;
  version: number;
  updated_at: string;
  is_default: boolean;
}

export interface PromptListResponse {
  prompts: PromptResponse[];
}
