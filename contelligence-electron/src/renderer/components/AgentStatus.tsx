import { useState, useEffect, useCallback } from "react";

import { getBaseUrlSync } from "@/lib/api";

const POLL_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

interface HealthResponse {
  status: string;
  service?: string;
  version?: string;
  token_health?: {
    healthy: boolean;
    error?: string;
  };
}

type AgentState = "online" | "degraded" | "offline";

const stateConfig: Record<AgentState, { color: string; label: string }> = {
  online: { color: "bg-success animate-pulse-glow", label: "Online" },
  degraded: { color: "bg-warning", label: "Degraded" },
  offline: { color: "bg-destructive", label: "Offline" },
};

export function AgentStatus() {
  const [agentState, setAgentState] = useState<AgentState>("offline");

  const checkHealth = useCallback(async () => {
    try {
      const baseUrl = getBaseUrlSync();
      const res = await fetch(`${baseUrl}/health/`, {
        signal: AbortSignal.timeout(10_000),
      });
      if (!res.ok) {
        setAgentState("offline");
        return;
      }
      const data: HealthResponse = await res.json();

      if (data.status === "healthy") {
        // Also verify token manager is healthy if present
        if (data.token_health && !data.token_health.healthy) {
          setAgentState("degraded");
        } else {
          setAgentState("online");
        }
      } else if (data.status === "degraded") {
        setAgentState("degraded");
      } else {
        setAgentState("offline");
      }
    } catch {
      setAgentState("offline");
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const id = setInterval(checkHealth, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [checkHealth]);

  const { color, label } = stateConfig[agentState];

  return (
    <div className="rounded-lg bg-secondary p-3">
      <p className="text-xs text-muted-foreground">Agent Status</p>
      <div className="mt-1 flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${color}`} />
        <span className="text-sm text-foreground">{label}</span>
      </div>
    </div>
  );
}
