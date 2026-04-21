// ── Sessions ──────────────────────
export interface SessionRecord {
  id: string;
  instruction: string;
  status: "active" | "completed" | "failed" | "cancelled" | "waiting_approval";
  model: string;
  created_at: string;
  updated_at: string;
  summary: string | null;
  schedule_id: string | null;
  metrics: SessionMetrics;
  // Session management — item 1, 3, 5, 6
  title?: string | null;
  title_source?: "auto" | "manual" | null;
  tags?: string[];
  pinned?: boolean;
  parent_session_id?: string | null;
}

export interface SessionTagCount {
  tag: string;
  count: number;
}

export interface SessionMetrics {
  total_tool_calls: number;
  total_duration_seconds: number;
  documents_processed: number;
  errors_encountered: number;
  tokens_used: number;
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
  result?: string | null;
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

export interface UserPreferences {
  user_id: string;
  default_model: string | null;
  default_agent_id: string | null;
  updated_at?: string;
}

export interface HealthCheck {
  healthy: boolean;
  detail?: string;
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
  mcp_servers: string[];
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
  mcp_servers?: string[];
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
  mcp_servers?: string[];
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

export interface McpServerInfo {
  id: string;
  name: string;
  description: string;
  source?: 'built-in' | 'shared' | 'app';
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
