import type {
  SessionRecord,
  ConversationTurn,
  OutputArtifact,
  ScheduleRecord,
  ScheduleRunRecord,
  CreateScheduleRequest,
  UpdateScheduleRequest,
  DashboardMetrics,
  DetailedMetrics,
  DailyDetailMetrics,
  ActivityEvent,
  AdminSettings,
  TokenStatus,
  TokenValidationResult,
  HealthCheck,
  HealthStatus,
  EnvironmentInfo,
  UserPreferences,
  AgentDefinitionRecord,
  ModelInfo,
  AgentSummary,
  CreateAgentRequest,
  UpdateAgentRequest,
  TestAgentRequest,
  TestAgentResponse,
  ToolInfo,
  McpServerEntry,
  McpServerHealthResult,
  McpToolEntry,
  AddMcpServerRequest,
  SkillRecord,
  SkillSummary,
  CreateSkillRequest,
  UpdateSkillRequest,
  SkillValidationResult,
  PromptResponse,
  PromptListResponse,
  SessionTagCount,
} from "@/types";

// Resolve API base URL: Electron IPC bridge (main process) → Vite env → /api fallback
let _resolvedBaseUrl: string | null = null;

async function resolveBaseUrl(): Promise<string> {
  if (_resolvedBaseUrl) return _resolvedBaseUrl;
  _resolvedBaseUrl = await window.electronAPI.getApiBaseUrl();
  return _resolvedBaseUrl;
}

// Synchronous access for SSE URL construction — fallback to env or default
function getBaseUrlSync(): string {
  return _resolvedBaseUrl || "http://localhost:8081/api/v1";
}

// Initialize eagerly
resolveBaseUrl();

// Kept as an alias for backwards-compatible SSE streaming URL construction
export const BASE_URL = getBaseUrlSync();

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const baseUrl = await resolveBaseUrl();
  const res = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }

  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }

  return res.json();
}

function toQueryString(params?: Record<string, string | number | boolean | undefined>): string {
  if (!params) return "";
  const filtered = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (filtered.length === 0) return "";
  return "?" + new URLSearchParams(filtered.map(([k, v]) => [k, String(v)])).toString();
}

// ── Agent API ────────────────────────────
export const agentApi = {
  instruct: (
    instruction: string,
    sessionId?: string,
    options?: { agents?: string[]; skill_ids?: string[]; model?: string },
  ) =>
    apiFetch<{ session_id: string }>("/agent/instruct", {
      method: "POST",
      body: JSON.stringify({
        instruction,
        session_id: sessionId,
        options: options ?? undefined,
      }),
    }),

  getSessions: (params?: {
    status?: string;
    limit?: number;
    tags?: string;
    search?: string;
    pinned_first?: boolean;
  }) =>
    apiFetch<SessionRecord[]>(`/agent/sessions${toQueryString(params)}`),

  getSessionTags: () =>
    apiFetch<SessionTagCount[]>("/agent/sessions/tags"),

  getSession: (id: string) =>
    apiFetch<SessionRecord>(`/agent/sessions/${id}`),

  getSessionLogs: (id: string, params?: { include_tool_results?: boolean }) =>
    apiFetch<{ session_id: string; turns: ConversationTurn[] }>(`/agent/sessions/${id}/logs${toQueryString(params)}`)
      .then((r) => r.turns),

  reply: (
    sessionId: string,
    message: string,
    mode?: "immediate" | "enqueue",
  ) =>
    apiFetch<{ status: string; mode?: string }>(
      `/agent/sessions/${sessionId}/reply`,
      {
        method: "POST",
        body: JSON.stringify({ message, mode }),
      },
    ),

  cancel: (sessionId: string) =>
    apiFetch<void>(`/agent/sessions/${sessionId}/cancel`, {
      method: "DELETE",
    }),

  deleteSession: (sessionId: string) =>
    apiFetch<{ status: string; session_id: string; turns_deleted: number; outputs_deleted: number; events_deleted: number; blobs_deleted: number }>(
      `/agent/sessions/${sessionId}`,
      { method: "DELETE" },
    ),

  listModels: () =>
    apiFetch<{ models: Array<ModelInfo> }>("/agent/models")
      .then((r) => r.models),

  updateSessionSettings: (sessionId: string, data: { model?: string }) =>
    apiFetch<{ status: string; session_id: string; model?: string }>(`/agent/sessions/${sessionId}/settings`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // ── Session management — item 1, 3, 5, 6, 8 ──
  renameSession: (sessionId: string, data: { auto?: boolean; title?: string }) =>
    apiFetch<SessionRecord>(`/agent/sessions/${sessionId}/rename`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  setSessionTags: (sessionId: string, tags: string[]) =>
    apiFetch<SessionRecord>(`/agent/sessions/${sessionId}/tags`, {
      method: "PUT",
      body: JSON.stringify({ tags }),
    }),

  addSessionTags: (sessionId: string, tags: string[]) =>
    apiFetch<SessionRecord>(`/agent/sessions/${sessionId}/tags`, {
      method: "POST",
      body: JSON.stringify({ tags }),
    }),

  removeSessionTags: (sessionId: string, tags: string[]) =>
    apiFetch<SessionRecord>(`/agent/sessions/${sessionId}/tags`, {
      method: "DELETE",
      body: JSON.stringify({ tags }),
    }),

  pinSession: (sessionId: string, pinned: boolean) =>
    apiFetch<SessionRecord>(`/agent/sessions/${sessionId}/pin`, {
      method: "POST",
      body: JSON.stringify({ pinned }),
    }),

  duplicateSession: (
    sessionId: string,
    data?: { include_turns?: boolean; new_title?: string },
  ) =>
    apiFetch<SessionRecord>(`/agent/sessions/${sessionId}/duplicate`, {
      method: "POST",
      body: JSON.stringify(data ?? {}),
    }),
};

// ── Preferences API ──────────────────────
export const preferencesApi = {
  get: () =>
    apiFetch<UserPreferences>("/agent/preferences"),

  update: (data: { default_model?: string; default_agent_id?: string }) =>
    apiFetch<UserPreferences>("/agent/preferences", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
};

// ── Schedule API ─────────────────────────
export const scheduleApi = {
  list: (params?: { status?: string }) =>
    apiFetch<ScheduleRecord[]>(`/schedules${toQueryString(params)}`),

  get: (id: string) =>
    apiFetch<ScheduleRecord>(`/schedules/${id}`),

  create: (data: CreateScheduleRequest) =>
    apiFetch<ScheduleRecord>("/schedules", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (id: string, data: UpdateScheduleRequest) =>
    apiFetch<ScheduleRecord>(`/schedules/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    apiFetch<void>(`/schedules/${id}`, { method: "DELETE" }),

  pause: (id: string) =>
    apiFetch<void>(`/schedules/${id}/pause`, { method: "POST" }),

  resume: (id: string) =>
    apiFetch<void>(`/schedules/${id}/resume`, { method: "POST" }),

  trigger: (id: string) =>
    apiFetch<{ session_id: string }>(`/schedules/${id}/trigger`, { method: "POST" }),

  history: (id: string, limit = 20) =>
    apiFetch<ScheduleRunRecord[]>(`/schedules/${id}/runs?limit=${limit}`),
};

// ── Dashboard API ────────────────────────
export const dashboardApi = {
  metrics: (since?: string) =>
    apiFetch<DashboardMetrics>(`/dashboard/metrics${since ? `?since=${since}` : ""}`),

  detailedMetrics: (days = 30) =>
    apiFetch<DetailedMetrics>(`/dashboard/metrics/detailed?days=${days}`),

  dailyMetrics: (date: string) =>
    apiFetch<DailyDetailMetrics>(`/dashboard/metrics/daily?date=${date}`),

  activity: (limit = 50) =>
    apiFetch<ActivityEvent[]>(`/dashboard/activity?limit=${limit}`),
};

// ── Admin API ────────────────────────────
export const adminApi = {
  getSettings: () =>
    apiFetch<AdminSettings>("/admin/settings"),

  updateSettings: (data: Partial<AdminSettings>) =>
    apiFetch<AdminSettings>("/admin/settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  getTokenStatus: () =>
    apiFetch<TokenStatus>("/admin/settings/github-token/status"),

  validateToken: (token: string) =>
    apiFetch<TokenValidationResult>("/admin/settings/github-token/validate", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),

  rotateToken: (token: string) =>
    apiFetch<void>("/admin/settings/github-token/rotate", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),

  getHealth: () =>
    apiFetch<Record<string, HealthCheck>>("/admin/health"),
};

// ── Health API ───────────────────────────
export const healthApi = {
  status: () =>
    apiFetch<HealthStatus>("/health"),

  environment: () =>
    apiFetch<EnvironmentInfo>("/health/environment"),
};

// Export for SSE streaming URL construction
export { getBaseUrlSync, resolveBaseUrl };

// ── Agents Management API ────────────────
export const agentsApi = {
  list: (params?: { status?: string; source?: string }) =>
    apiFetch<AgentSummary[]>(`/agents${toQueryString(params)}`),

  get: (id: string) =>
    apiFetch<AgentDefinitionRecord>(`/agents/${id}`),

  create: (data: CreateAgentRequest) =>
    apiFetch<AgentDefinitionRecord>("/agents", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (id: string, data: UpdateAgentRequest) =>
    apiFetch<AgentDefinitionRecord>(`/agents/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    apiFetch<void>(`/agents/${id}`, { method: "DELETE" }),

  clone: (id: string) =>
    apiFetch<AgentDefinitionRecord>(`/agents/${id}/clone`, { method: "POST" }),

  test: (id: string, data: TestAgentRequest) =>
    apiFetch<TestAgentResponse>(`/agents/${id}/test`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  tools: () =>
    apiFetch<ToolInfo[]>("/agents/tools"),
};

// ── MCP Servers API ──────────────────────
export const mcpServersApi = {
  list: () =>
    apiFetch<McpServerEntry[]>("/mcp-servers"),

  add: (data: AddMcpServerRequest) =>
    apiFetch<McpServerEntry>("/mcp-servers", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  remove: (key: string) =>
    apiFetch<void>(`/mcp-servers/${encodeURIComponent(key)}`, { method: "DELETE" }),

  setDisabled: (key: string, disabled: boolean) =>
    apiFetch<McpServerEntry>(`/mcp-servers/${encodeURIComponent(key)}/disabled`, {
      method: "PATCH",
      body: JSON.stringify({ disabled }),
    }),

  test: (key: string) =>
    apiFetch<McpServerHealthResult>(`/mcp-servers/${encodeURIComponent(key)}/test`, {
      method: "POST",
    }),

  tools: (key: string) =>
    apiFetch<McpToolEntry[]>(`/mcp-servers/${encodeURIComponent(key)}/tools`),
};

// ── Skills API ───────────────────────────
export const skillsApi = {
  list: (params?: { status?: string; tag?: string }) =>
    apiFetch<SkillSummary[]>(`/skills${toQueryString(params)}`),

  get: (id: string) =>
    apiFetch<SkillRecord>(`/skills/${id}`),

  create: (data: CreateSkillRequest) =>
    apiFetch<SkillRecord>("/skills", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (id: string, data: UpdateSkillRequest) =>
    apiFetch<SkillRecord>(`/skills/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    apiFetch<void>(`/skills/${id}`, { method: "DELETE" }),

  validate: (content: string) =>
    apiFetch<SkillValidationResult>("/skills/validate", {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  files: (id: string) =>
    apiFetch<string[]>(`/skills/${id}/files`),

  uploadFile: async (id: string, file: File, path: string) => {
    const baseUrl = await resolveBaseUrl();
    const formData = new FormData();
    formData.append("file", file);
    formData.append("path", path);
    const res = await fetch(`${baseUrl}/skills/${id}/files`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(error.detail || `Upload failed: ${res.status}`);
    }
    return res.json() as Promise<{ path: string; size: number }>;
  },

  uploadZip: async (id: string, file: File) => {
    const baseUrl = await resolveBaseUrl();
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${baseUrl}/skills/${id}/upload-zip`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(error.detail || `Zip upload failed: ${res.status}`);
    }
    return res.json() as Promise<{ files_added: number; files: string[] }>;
  },

  deleteFile: (id: string, path: string) =>
    apiFetch<void>(`/skills/${id}/files/${encodeURIComponent(path)}`, {
      method: "DELETE",
    }),
};

// ── Prompts API ──────────────────────────
export const promptsApi = {
  list: () =>
    apiFetch<PromptListResponse>("/admin/prompts").then((r) => r.prompts),

  get: (id: string) =>
    apiFetch<PromptResponse>(`/admin/prompts/${id}`),

  update: (id: string, content: string) =>
    apiFetch<PromptResponse>(`/admin/prompts/${id}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),

  reset: (id: string) =>
    apiFetch<PromptResponse>(`/admin/prompts/${id}/reset`, {
      method: "POST",
    }),
};
