import type {
  SessionRecord,
  ConversationTurn,
  OutputArtifact,
  ScheduleRecord,
  ScheduleRunRecord,
  CreateScheduleRequest,
  UpdateScheduleRequest,
  DashboardMetrics,
  ActivityEvent,
  AdminSettings,
  TokenStatus,
  TokenValidationResult,
  HealthCheck,
  AgentDefinitionRecord,
  AgentSummary,
  CreateAgentRequest,
  UpdateAgentRequest,
  TestAgentRequest,
  TestAgentResponse,
  ToolInfo,
  McpServerInfo,
  SkillRecord,
  SkillSummary,
  CreateSkillRequest,
  UpdateSkillRequest,
  SkillValidationResult,
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
    options?: { agents?: string[]; skill_ids?: string[] },
  ) =>
    apiFetch<{ session_id: string }>("/agent/instruct", {
      method: "POST",
      body: JSON.stringify({
        instruction,
        session_id: sessionId,
        options: options ?? undefined,
      }),
    }),

  getSessions: (params?: { status?: string; limit?: number }) =>
    apiFetch<SessionRecord[]>(`/agent/sessions${toQueryString(params)}`),

  getSession: (id: string) =>
    apiFetch<SessionRecord>(`/agent/sessions/${id}`),

  getSessionLogs: (id: string, params?: { include_tool_results?: boolean }) =>
    apiFetch<{ session_id: string; turns: ConversationTurn[] }>(`/agent/sessions/${id}/logs${toQueryString(params)}`)
      .then((r) => r.turns),

  getSessionOutputs: (id: string) =>
    apiFetch<{ session_id: string; outputs: OutputArtifact[] }>(`/agent/sessions/${id}/outputs`)
      .then((r) => r.outputs),

  reply: (sessionId: string, message: string) =>
    apiFetch<void>(`/agent/sessions/${sessionId}/reply`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

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
    apiFetch<{ models: Array<{ id: string; name: string; capabilities?: Record<string, unknown> }> }>("/agent/models")
      .then((r) => r.models),
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

  mcpServers: () =>
    apiFetch<McpServerInfo[]>("/agents/mcp-servers"),
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
