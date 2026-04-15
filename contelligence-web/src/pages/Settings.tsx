import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { CheckCircle, XCircle, ShieldCheck, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { adminApi, agentApi, preferencesApi } from "@/lib/api";
import type { HealthCheck } from "@/types";

/* ── System Health Panel ─────────────────── */
const HEALTH_CHECKS = [
  { key: "copilot_cli", label: "Copilot CLI" },
  { key: "cosmos_db", label: "Cosmos DB" },
  { key: "blob_storage", label: "Blob Storage" },
  { key: "key_vault", label: "Key Vault" },
  { key: "scheduler", label: "Scheduler" },
  { key: "event_grid", label: "Event Grid" },
];

function SystemHealthPanel() {
  const { data: health, isLoading } = useQuery({
    queryKey: ["system-health"],
    queryFn: adminApi.getHealth,
    refetchInterval: 30_000,
  });

  return (
    <div className="space-y-3">
      {HEALTH_CHECKS.map(({ key, label }) => {
        if (isLoading) {
          return (
            <div key={key} className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
              <span className="text-sm text-foreground">{label}</span>
              <Skeleton className="h-4 w-24" />
            </div>
          );
        }
        const check: HealthCheck | undefined = health?.[key];
        return (
          <div key={key} className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
            <span className="text-sm text-foreground">{label}</span>
            <div className="flex items-center gap-2">
              {check?.healthy ? (
                <CheckCircle className="h-4 w-4 text-success" />
              ) : (
                <XCircle className="h-4 w-4 text-destructive" />
              )}
              <span className="text-sm text-muted-foreground">
                {check?.detail ?? (check?.healthy ? "Connected" : "Error")}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ── Main Page ────────────────────────────── */

function DefaultModelSettings() {
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

  const { data: settings, isLoading: settingsLoading } = useQuery({
    queryKey: ["admin-settings"],
    queryFn: adminApi.getSettings,
  });

  const updatePreferencesMutation = useMutation({
    mutationFn: preferencesApi.update,
    onSuccess: () => {
      toast.success("Default model preference saved");
      queryClient.invalidateQueries({ queryKey: ["user-preferences"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const updateSettingsMutation = useMutation({
    mutationFn: adminApi.updateSettings,
    onSuccess: () => {
      toast.success("Settings saved");
      queryClient.invalidateQueries({ queryKey: ["admin-settings"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const isLoading = prefsLoading || modelsLoading || settingsLoading;

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-10 w-32" />
      </div>
    );
  }

  // Determine effective default: user preference → system setting → first model
  const effectiveDefault =
    preferences?.default_model ??
    settings?.default_model ??
    (availableModels.length > 0 ? availableModels[0].id : "");

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label className="text-muted-foreground">Default Model</Label>
        <Select
          value={effectiveDefault}
          onValueChange={(v) => updatePreferencesMutation.mutate({ default_model: v })}
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

      <div className="flex items-center justify-between">
        <Label className="text-muted-foreground">Require Approval for Write Operations</Label>
        <Switch
          checked={settings?.require_approval ?? true}
          onCheckedChange={(v) => updateSettingsMutation.mutate({ require_approval: v })}
        />
      </div>

      <div className="space-y-2">
        <Label className="text-muted-foreground">Default Timeout (minutes)</Label>
        <Input
          type="number"
          value={settings?.default_timeout_minutes ?? 60}
          onChange={(e) =>
            updateSettingsMutation.mutate({
              default_timeout_minutes: parseInt(e.target.value) || 60,
            })
          }
          className="bg-secondary border-border text-foreground w-32"
        />
      </div>
    </div>
  );
}

const Settings = () => {
  const queryClient = useQueryClient();
  const [newToken, setNewToken] = useState("");

  const { data: tokenStatus, isLoading: tokenLoading } = useQuery({
    queryKey: ["token-status"],
    queryFn: adminApi.getTokenStatus,
  });

  const validateMutation = useMutation({
    mutationFn: adminApi.validateToken,
    onSuccess: (result) => {
      if (result.valid) {
        toast.success(`Token valid — user: ${result.user}, scopes: ${result.scopes?.join(", ")}`);
      } else {
        toast.error(`Token invalid: ${result.error}`);
      }
    },
    onError: (err) => toast.error(err.message),
  });

  const rotateMutation = useMutation({
    mutationFn: adminApi.rotateToken,
    onSuccess: () => {
      toast.success("Token rotated successfully");
      setNewToken("");
      queryClient.invalidateQueries({ queryKey: ["token-status"] });
    },
    onError: (err) => toast.error(err.message),
  });

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-bold text-foreground font-display tracking-wide">Settings</h1>

      {/* GitHub Copilot Auth */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-foreground flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-primary" />
            GitHub Copilot Authentication
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {tokenLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-4 w-40" />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Status</span>
                <div className="flex items-center gap-2 mt-1">
                  {tokenStatus?.connected ? (
                    <CheckCircle className="h-4 w-4 text-success" />
                  ) : (
                    <XCircle className="h-4 w-4 text-destructive" />
                  )}
                  <span className="text-foreground">
                    {tokenStatus?.connected ? "Connected" : "Disconnected"}
                  </span>
                </div>
              </div>
              <div>
                <span className="text-muted-foreground">User</span>
                <p className="text-foreground mt-1 font-mono">{tokenStatus?.user ?? "—"}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Token</span>
                <p className="text-foreground mt-1 font-mono text-xs">
                  {tokenStatus?.masked_token ?? "Not set"}
                </p>
              </div>
              <div>
                <span className="text-muted-foreground">Scopes</span>
                <div className="flex gap-1 mt-1 flex-wrap">
                  {tokenStatus?.scopes?.map((scope) => (
                    <Badge key={scope} variant="secondary" className="text-xs bg-secondary text-muted-foreground">
                      {scope}
                    </Badge>
                  )) ?? <span className="text-muted-foreground">—</span>}
                </div>
              </div>
              <div className="col-span-2">
                <span className="text-muted-foreground">Stored in</span>
                <p className="text-foreground mt-1">Azure Key Vault</p>
              </div>
            </div>
          )}

          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              className="border-border text-muted-foreground hover:text-foreground"
              onClick={() => validateMutation.mutate(newToken || "current")}
              disabled={validateMutation.isPending}
            >
              <ShieldCheck className="h-3.5 w-3.5 mr-1" />
              {validateMutation.isPending ? "Validating..." : "Validate Token"}
            </Button>
          </div>

          <Separator className="bg-border" />

          <div className="flex gap-2">
            <Input
              type="password"
              placeholder="New token (ghp_...)"
              value={newToken}
              onChange={(e) => setNewToken(e.target.value)}
              className="bg-secondary border-border text-foreground font-mono text-sm flex-1"
            />
            <Button
              className="bg-primary text-primary-foreground hover:bg-primary/90 shrink-0"
              onClick={() => rotateMutation.mutate(newToken)}
              disabled={!newToken || rotateMutation.isPending}
            >
              <RefreshCw className="h-3.5 w-3.5 mr-1" />
              {rotateMutation.isPending ? "Rotating..." : "Rotate Token"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Default Agent Settings */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-foreground">Default Agent Settings</CardTitle>
        </CardHeader>
        <CardContent>
          <DefaultModelSettings />
        </CardContent>
      </Card>

      {/* System Health */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="text-foreground">System Health</CardTitle>
        </CardHeader>
        <CardContent>
          <SystemHealthPanel />
        </CardContent>
      </Card>
    </div>
  );
};

export default Settings;