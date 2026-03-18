import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { CheckCircle, XCircle, Activity, Monitor, Server, Database, FolderOpen, Gauge, HardDrive } from "lucide-react";
import { healthApi } from "@/lib/api";
import type { HealthStatus, EnvironmentInfo } from "@/types";

/* ── System Health Panel ─────────────────── */

function SystemHealthPanel() {
  const { data: health, isLoading } = useQuery<HealthStatus>({
    queryKey: ["system-health"],
    queryFn: healthApi.status,
    refetchInterval: 30_000,
  });

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-24" />
          </div>
        ))}
      </div>
    );
  }

  const statusColor = health?.status === "healthy" ? "text-success" : "text-warning";

  return (
    <div className="space-y-4">
      {/* Overall status */}
      <div className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
        <span className="text-sm font-medium text-foreground">Overall Status</span>
        <Badge variant={health?.status === "healthy" ? "default" : "destructive"} className="capitalize">
          {health?.status ?? "unknown"}
        </Badge>
      </div>

      {/* Core info */}
      <div className="grid grid-cols-2 gap-3">
        <InfoRow label="Service" value={health?.service ?? "—"} />
        <InfoRow label="Version" value={health?.version ?? "—"} />
        <InfoRow label="Instance ID" value={health?.instance_id ?? "—"} mono />
        {health?.is_scheduler_leader !== undefined && (
          <InfoRow label="Scheduler Leader" value={health.is_scheduler_leader ? "✅ This instance" : "Another instance"} />
        )}
      </div>

      {/* Token health */}
      {health?.token_health && (
        <div className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
          <span className="text-sm text-foreground">Token Manager</span>
          <Badge variant={health.token_health.status === "healthy" ? "default" : "destructive"} className="capitalize">
            {health.token_health.status}
          </Badge>
        </div>
      )}

      {/* MCP Servers */}
      {health?.mcp_servers && Object.keys(health.mcp_servers).length > 0 && (
        <div className="space-y-2">
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">MCP Servers</span>
          {Object.entries(health.mcp_servers).map(([name, info]) => (
            <div key={name} className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
              <span className="text-sm text-foreground">{name}</span>
              <div className="flex items-center gap-2">
                {info.status === "available" ? (
                  <CheckCircle className="h-4 w-4 text-success" />
                ) : (
                  <XCircle className="h-4 w-4 text-destructive" />
                )}
                <span className="text-sm text-muted-foreground">
                  {info.status}
                  {info.latency_ms !== undefined && ` (${info.latency_ms}ms)`}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Environment Info Panel ──────────────── */

function EnvironmentPanel() {
  const { data: env, isLoading } = useQuery<EnvironmentInfo>({
    queryKey: ["system-environment"],
    queryFn: healthApi.environment,
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-20 w-full" />
          </div>
        ))}
      </div>
    );
  }

  if (!env) return null;

  return (
    <div className="space-y-6">
      {/* Storage */}
      <EnvSection icon={<FolderOpen className="h-4 w-4" />} title="Storage & Paths" entries={env.storage} />

      {/* Server / Runtime */}
      <EnvSection icon={<Server className="h-4 w-4" />} title="Server / Runtime" entries={env.server} />

      {/* Quotas */}
      <EnvSection icon={<Gauge className="h-4 w-4" />} title="Session Quotas" entries={env.quotas} />

      {/* Rate Limits */}
      <EnvSection icon={<Gauge className="h-4 w-4" />} title="Rate Limits" entries={env.rate_limits} />

      {/* Cache & Retention */}
      <EnvSection icon={<HardDrive className="h-4 w-4" />} title="Cache & Retention" entries={env.cache_retention} />

      {/* Scaling */}
      <EnvSection icon={<Server className="h-4 w-4" />} title="Scaling" entries={env.scaling} />
    </div>
  );
}

/* ── Shared helpers ──────────────────────── */

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-lg bg-secondary/50 p-3">
      <span className="text-xs text-muted-foreground">{label}</span>
      <p className={`text-sm text-foreground mt-0.5 ${mono ? "font-mono" : ""} truncate`}>{value}</p>
    </div>
  );
}

function EnvSection({
  icon,
  title,
  entries,
}: {
  icon: React.ReactNode;
  title: string;
  entries: Record<string, string | number | boolean>;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-primary">{icon}</span>
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{title}</span>
      </div>
      <div className="rounded-lg border border-border overflow-hidden">
        {Object.entries(entries).map(([key, val], idx) => (
          <div
            key={key}
            className={`flex items-center justify-between px-3 py-2 text-sm ${idx > 0 ? "border-t border-border" : ""}`}
          >
            <span className="text-muted-foreground">{formatKey(key)}</span>
            <span className="text-foreground font-mono text-xs ml-2 max-w-[80%] text-right">
              {typeof val === "boolean" ? (val ? "Yes" : "No") : String(val)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ── Main Page ────────────────────────────── */
const Settings = () => {
  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-bold text-foreground font-display tracking-wide">Settings</h1>

      {/* System Health */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-foreground flex items-center gap-2">
            <Activity className="h-5 w-5 text-primary" />
            System Health
          </CardTitle>
        </CardHeader>
        <CardContent>
          <SystemHealthPanel />
        </CardContent>
      </Card>

      {/* System Environment */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-foreground flex items-center gap-2">
            <Server className="h-5 w-5 text-primary" />
            System Environment
          </CardTitle>
        </CardHeader>
        <CardContent>
          <EnvironmentPanel />
        </CardContent>
      </Card>

      {/* Desktop App Info — Electron only */}
      {window.electronAPI && <DesktopInfoCard />}
    </div>
  );
};

function DesktopInfoCard() {
  const [info, setInfo] = useState<Record<string, string> | null>(null);
  useEffect(() => {
    window.electronAPI.getAppInfo().then((data) =>
      setInfo(data as unknown as Record<string, string>)
    );
  }, []);
  if (!info) return null;
  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-foreground flex items-center gap-2">
          <Monitor className="h-5 w-5 text-primary" />
          Desktop App
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3 text-sm">
          {Object.entries(info).map(([key, val]) => (
            <div key={key}>
              <span className="text-muted-foreground capitalize">{key.replace(/_/g, " ")}</span>
              <p className="text-foreground font-mono mt-0.5">{val}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export default Settings;