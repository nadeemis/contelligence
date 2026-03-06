// ── Base event ──────────────────────────────────────────────────────
export interface AgentEvent {
  type: string;
  timestamp: string;
  /** Raw SSE payload preserved for display */
  payload: Record<string, unknown>;
}

// ── Turn lifecycle ──────────────────────────────────────────────────
export interface TurnStartEvent extends AgentEvent {
  type: "turn_start";
  turn_id: string;
  interaction_id: string;
}

export interface TurnEndEvent extends AgentEvent {
  type: "turn_end";
  turn_id: string;
}

// ── Usage / cost ────────────────────────────────────────────────────
export interface UsageInfoEvent extends AgentEvent {
  type: "usage_info";
  current_tokens: number;
  token_limit: number;
  messages_length: number;
}

export interface AssistantUsageEvent extends AgentEvent {
  type: "assistant_usage";
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  model: string;
  duration: number;
  cost: number;
}

// ── Reasoning / content ─────────────────────────────────────────────
export interface ThinkingEvent extends AgentEvent {
  type: "thinking";
  content: string;
}

export interface MessageEvent extends AgentEvent {
  type: "message";
  content: string;
}

// ── Tool lifecycle (4 events per tool call) ─────────────────────────
export interface ToolExecutionStartEvent extends AgentEvent {
  type: "tool_execution_start";
  tool_name: string;
  tool_call_id: string;
  arguments: Record<string, unknown>;
}

export interface ToolCallStartEvent extends AgentEvent {
  type: "tool_call_start";
  tool_name: string;
  params: string;
}

export interface ToolCallCompleteEvent extends AgentEvent {
  type: "tool_call_complete";
  tool_name: string;
  duration_ms: number;
}

export interface ToolExecutionCompleteEvent extends AgentEvent {
  type: "tool_execution_complete";
  tool_call_id: string;
  result: unknown;
  duration: number | null;
}

// ── Sub-agent delegation ────────────────────────────────────────────
export interface SubagentStartedEvent extends AgentEvent {
  type: "subagent_started";
  agent_name: string;
}

export interface SubagentCompletedEvent extends AgentEvent {
  type: "subagent_completed";
  agent_name: string;
  summary: string | null;
}

// ── Approval ────────────────────────────────────────────────────────
export interface ApprovalRequiredEvent extends AgentEvent {
  type: "approval_required";
  tool_name: string;
  arguments: Record<string, unknown>;
  reason: string;
}

// ── Terminal / status ───────────────────────────────────────────────
export interface ErrorEvent extends AgentEvent {
  type: "error";
  message: string;
  recoverable: boolean;
}

export interface DoneEvent extends AgentEvent {
  type: "done";
  session_id: string;
  summary: string;
}

export interface SessionTitleChangedEvent extends AgentEvent {
  type: "session_title_changed";
  title: string;
}

// ── Union ───────────────────────────────────────────────────────────
export type AgentEventUnion =
  | TurnStartEvent
  | TurnEndEvent
  | UsageInfoEvent
  | AssistantUsageEvent
  | ThinkingEvent
  | MessageEvent
  | ToolExecutionStartEvent
  | ToolCallStartEvent
  | ToolCallCompleteEvent
  | ToolExecutionCompleteEvent
  | SubagentStartedEvent
  | SubagentCompletedEvent
  | ApprovalRequiredEvent
  | ErrorEvent
  | DoneEvent
  | SessionTitleChangedEvent;

// ── Turn processing types ───────────────────────────────────────────
export interface ToolGroup {
  toolCallId: string;
  toolName: string;
  events: AgentEventUnion[];
}

export type TurnItem =
  | { kind: "event"; event: AgentEventUnion }
  | { kind: "tool_group"; group: ToolGroup };

export interface ProcessedTurn {
  turnId: string;
  interactionId?: string;
  usageEvents: (UsageInfoEvent | AssistantUsageEvent)[];
  items: TurnItem[];
}

export type TimelineItem =
  | { kind: "turn"; turn: ProcessedTurn }
  | { kind: "orphan"; event: AgentEventUnion };
