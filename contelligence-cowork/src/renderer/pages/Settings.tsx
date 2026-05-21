import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CheckCircle, XCircle, Activity, Monitor, Server, FolderOpen, Gauge, HardDrive, ScrollText, Sun, Moon, Laptop, Cpu, Download, RefreshCw, ExternalLink, History, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { healthApi, promptsApi, agentApi, preferencesApi } from "@/lib/api";
import { PromptEditDialog } from "@/components/PromptEditDialog";
import { useTheme, type Theme } from "@/components/ThemeProvider";
import { useUpdateStatus } from "@/hooks/useUpdateStatus";
import type { HealthStatus, EnvironmentInfo, PromptResponse } from "@/types";

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

      {/* Copilot CLI */}
      {health?.copilot_cli && (
        <>
        <div className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
          <span className="text-sm text-foreground">Copilot CLI:</span>
          <Badge variant={health.copilot_cli.status === "available" ? "default" : "destructive"} className="capitalize">
            {(  health.copilot_cli.status === "available" ? "Available" : "Unavailable") +
              (health.copilot_cli.cli_version ? ` (v${health.copilot_cli.cli_version})` : "")}
          </Badge>
        </div>
        {health.copilot_cli.cli_config && (
          <div className="rounded-lg bg-secondary/50 p-3">
            <span className="text-sm text-foreground">Copilot CLI Config:</span>
            <pre className="mt-1 max-h-48 overflow-y-auto overflow-x-hidden whitespace-pre-wrap break-all rounded-md bg-secondary/30 p-2 text-xs text-foreground">
              {JSON.stringify(health.copilot_cli.cli_config, null, 2)}
            </pre>
          </div>
        )}
        </>
      )}

      {/* MCP Servers */}
      {health?.mcp_servers && Object.keys(health.mcp_servers).length > 0 && (
        <div className="space-y-2">
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">MCP Servers</span>
          {Object.entries(health.mcp_servers).map(([name, info]) => (
            <div key={name} className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
              <span className="text-sm text-foreground">{name}</span>
              <div className="flex items-center gap-2">
                {info.status === "ok" ? (
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

/* ── System Prompt Panel ──────────────────── */

function SystemPromptPanel() {
  const queryClient = useQueryClient();
  const [editingPrompt, setEditingPrompt] = useState<PromptResponse | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const { data: prompts, isLoading } = useQuery<PromptResponse[]>({
    queryKey: ["admin-prompts"],
    queryFn: promptsApi.list,
  });

  const systemPrompt = prompts?.find((p) => p.prompt_type === "system");

  const saveMutation = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) =>
      promptsApi.update(id, content),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["admin-prompts"] });
      setEditingPrompt(updated);
      toast.success(`"${updated.name}" prompt saved`);
    },
    onError: (err: Error) => {
      toast.error(`Failed to save prompt: ${err.message}`);
    },
  });

  const resetMutation = useMutation({
    mutationFn: (id: string) => promptsApi.reset(id),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["admin-prompts"] });
      setEditingPrompt(updated);
      toast.success(`"${updated.name}" reset to default`);
    },
    onError: (err: Error) => {
      toast.error(`Failed to reset prompt: ${err.message}`);
    },
  });

  if (isLoading) {
    return <Skeleton className="h-9 w-full rounded-lg" />;
  }

  if (!systemPrompt) {
    return <p className="text-sm text-muted-foreground">No system prompt available.</p>;
  }

  return (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm text-foreground">{systemPrompt.name}</span>
          {systemPrompt.is_default ? (
            <Badge variant="secondary" className="text-xs">Default</Badge>
          ) : (
            <Badge className="text-xs bg-primary/15 text-primary border-primary/30">Customised</Badge>
          )}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setEditingPrompt(systemPrompt);
            setDialogOpen(true);
          }}
        >
          <ScrollText className="h-3.5 w-3.5 mr-1" />
          View / Edit
        </Button>
      </div>

      <PromptEditDialog
        prompt={editingPrompt}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onSave={async (id, content) => {
          await saveMutation.mutateAsync({ id, content });
        }}
        onReset={async (id) => {
          await resetMutation.mutateAsync(id);
        }}
        isSaving={saveMutation.isPending || resetMutation.isPending}
      />
    </>
  );
}

/* ── Appearance Panel ─────────────────────── */

const themeOptions: { value: Theme; label: string; icon: React.ReactNode; description: string }[] = [
  { value: "system", label: "System", icon: <Laptop className="h-5 w-5" />, description: "Follow your OS appearance" },
  { value: "light", label: "Light", icon: <Sun className="h-5 w-5" />, description: "Bright and warm" },
  { value: "dark", label: "Dark", icon: <Moon className="h-5 w-5" />, description: "Easy on the eyes" },
];

function AppearanceCard() {
  const { theme, setTheme, resolvedTheme } = useTheme();

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-foreground flex items-center gap-2">
          <Sun className="h-5 w-5 text-primary" />
          Appearance
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 gap-3">
          {themeOptions.map((opt) => {
            const isActive = theme === opt.value;
            return (
              <button
                key={opt.value}
                onClick={() => setTheme(opt.value)}
                className={`
                  group relative flex flex-col items-center gap-2 rounded-xl border-2 p-4 transition-all duration-200
                  ${isActive
                    ? "border-primary bg-primary/10 shadow-sm shadow-primary/10"
                    : "border-border bg-secondary/30 hover:border-primary/40 hover:bg-secondary/60"
                  }
                `}
              >
                {/* Theme preview swatch */}
                <div className={`
                  flex h-10 w-full items-center justify-center rounded-lg transition-colors
                  ${opt.value === "dark"
                    ? "bg-[hsl(220,10%,7%)] text-[hsl(40,50%,82%)]"
                    : opt.value === "light"
                      ? "bg-[hsl(40,25%,97%)] text-[hsl(220,15%,15%)]"
                      : resolvedTheme === "dark"
                        ? "bg-[hsl(220,10%,7%)] text-[hsl(40,50%,82%)]"
                        : "bg-[hsl(40,25%,97%)] text-[hsl(220,15%,15%)]"
                  }
                `}>
                  {opt.icon}
                </div>
                <span className={`text-sm font-medium ${isActive ? "text-primary" : "text-foreground"}`}>
                  {opt.label}
                </span>
                <span className="text-xs text-muted-foreground">{opt.description}</span>
                {/* Active indicator */}
                {isActive && (
                  <div className="absolute -top-1 -right-1 h-3 w-3 rounded-full bg-primary ring-2 ring-background" />
                )}
              </button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

/* ── Default Model Panel ───────────────────── */

function DefaultModelPanel() {
  const queryClient = useQueryClient();

  const { data: preferences, isLoading: prefsLoading } = useQuery({
    queryKey: ["user-preferences"],
    queryFn: preferencesApi.get,
  });

  const { data: availableModels = [], isLoading: modelsLoading } = useQuery({
    queryKey: ["models"],
    queryFn: () => agentApi.listModels(),
    staleTime: 5 * 60 * 1000,
  });

  const updateMutation = useMutation({
    mutationFn: preferencesApi.update,
    onSuccess: () => {
      toast.success("Default model preference saved");
      queryClient.invalidateQueries({ queryKey: ["user-preferences"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  if (prefsLoading || modelsLoading) {
    return <Skeleton className="h-10 w-full" />;
  }

  const effectiveDefault =
    preferences?.default_model ?? (availableModels.length > 0 ? availableModels[0].id : "");

  return (
    <div className="space-y-2">
      <Label className="text-muted-foreground">Default Model</Label>
      <Select
        value={effectiveDefault}
        onValueChange={(v) => updateMutation.mutate({ default_model: v })}
      >
        <SelectTrigger className="bg-secondary border-border text-foreground">
          <SelectValue placeholder="Select default model…" />
        </SelectTrigger>
        <SelectContent>
          {availableModels.map((m) => (
            <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="text-xs text-muted-foreground">
        New sessions will use this model unless overridden.
      </p>
    </div>
  );
}

/* ── Main Page ────────────────────────────── */
const Settings = () => {
  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-bold text-foreground font-display tracking-wide">Settings</h1>

      {/* Appearance */}
      <AppearanceCard />

      {/* Default Model */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-foreground flex items-center gap-2">
            <Cpu className="h-5 w-5 text-primary" />
            Default Model
          </CardTitle>
        </CardHeader>
        <CardContent>
          <DefaultModelPanel />
        </CardContent>
      </Card>

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

      {/* System Prompt */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-foreground flex items-center gap-2">
            <ScrollText className="h-5 w-5 text-primary" />
            System Prompt
          </CardTitle>
        </CardHeader>
        <CardContent>
          <SystemPromptPanel />
        </CardContent>
      </Card>

      {/* Desktop App Info — Electron only */}
      {window.electronAPI && <DesktopInfoCard />}
      {window.electronAPI && <UpdatesCard />}
      {window.electronAPI && <InputHistoryCard />}
    </div>
  );
};

function UpdatesCard() {
  const { status, checkNow, openRelease, openDownloads } = useUpdateStatus();
  const [checking, setChecking] = useState(false);

  const handleCheck = async () => {
    setChecking(true);
    try {
      const next = await checkNow();
      if (next.state === "available") {
        toast.success(`Update available — v${next.latestVersion}`);
      } else if (next.state === "up-to-date") {
        toast.success("You're on the latest version");
      } else if (next.state === "error") {
        toast.error(`Update check failed: ${next.error ?? "unknown error"}`);
      }
    } finally {
      setChecking(false);
    }
  };

  const lastChecked = status.checkedAt
    ? new Date(status.checkedAt).toLocaleString()
    : "Never";

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-foreground flex items-center gap-2">
          <Download className="h-5 w-5 text-primary" />
          Updates
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <InfoRow
            label="Current Version"
            value={status.currentVersion || "—"}
            mono
          />
          <InfoRow
            label="Latest Version"
            value={status.latestVersion ? `v${status.latestVersion}` : "—"}
            mono
          />
          <InfoRow label="Last Checked" value={lastChecked} />
          <div className="rounded-lg bg-secondary/50 p-3">
            <span className="text-xs text-muted-foreground">Status</span>
            <div className="mt-1">
              {status.state === "available" && (
                <Badge className="bg-primary/15 text-primary border-primary/30">
                  Update available
                </Badge>
              )}
              {status.state === "up-to-date" && (
                <Badge variant="secondary">Up to date</Badge>
              )}
              {status.state === "checking" && (
                <Badge variant="secondary">Checking…</Badge>
              )}
              {status.state === "error" && (
                <Badge variant="destructive">Error</Badge>
              )}
              {status.state === "idle" && (
                <Badge variant="secondary">Idle</Badge>
              )}
            </div>
          </div>
        </div>

        {status.state === "error" && status.error && (
          <p className="text-xs text-destructive">{status.error}</p>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleCheck}
            disabled={checking || status.state === "checking"}
          >
            <RefreshCw
              className={`h-3.5 w-3.5 mr-1 ${
                checking || status.state === "checking" ? "animate-spin" : ""
              }`}
            />
            Check for updates
          </Button>
          {status.state === "available" && (
            <>
              <Button size="sm" onClick={() => openDownloads()}>
                <Download className="h-3.5 w-3.5 mr-1" />
                Download
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => openRelease()}
              >
                <ExternalLink className="h-3.5 w-3.5 mr-1" />
                Release notes
              </Button>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

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

function InputHistoryCard() {
  const [entryCount, setEntryCount] = useState(0);

  useEffect(() => {
    window.electronAPI?.getInputHistory?.().then((store) => {
      if (store && Array.isArray(store.entries)) {
        setEntryCount(store.entries.length);
      }
    });
  }, []);

  const handleClear = async () => {
    await window.electronAPI?.clearInputHistory?.();
    setEntryCount(0);
    toast.success("Input history cleared");
  };

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-foreground flex items-center gap-2">
          <History className="h-5 w-5 text-primary" />
          Input History
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Your chat input history is stored locally and used for Up/Down arrow navigation in the chat input.
        </p>
        <div className="flex items-center justify-between">
          <span className="text-sm text-foreground">
            {entryCount} {entryCount === 1 ? "entry" : "entries"} stored
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={handleClear}
            disabled={entryCount === 0}
            className="text-destructive hover:bg-destructive/10 border-destructive/30"
          >
            <Trash2 className="h-3.5 w-3.5 mr-1" />
            Clear History
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default Settings;