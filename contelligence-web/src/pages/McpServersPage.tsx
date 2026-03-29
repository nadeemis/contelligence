import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  Network,
  Plus,
  Pencil,
  Trash2,
  Activity,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";
import { mcpServersApi } from "@/lib/api";
import type { McpServerEntry, McpServerHealthResult, AddMcpServerRequest } from "@/types";

/* ── Server Dialog (Add / Edit) ────────────── */

interface ServerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: AddMcpServerRequest) => void;
  isSubmitting: boolean;
  /** When set, the dialog is in edit mode with fields pre-filled. */
  initial?: McpServerEntry;
}

const CONFIG_PLACEHOLDER = `{
  "type": "stdio",
  "command": ["npx", "-y", "@anthropic-ai/azure-mcp-server@latest"]
}`;

function ServerDialog({ open, onOpenChange, onSubmit, isSubmitting, initial }: ServerDialogProps) {
  const isEdit = !!initial;
  const [name, setName] = useState("");
  const [configText, setConfigText] = useState("");
  const [configError, setConfigError] = useState<string | null>(null);

  // Seed form when dialog opens with an initial value
  const resetToInitial = () => {
    if (initial) {
      setName(initial.name);
      setConfigText(JSON.stringify(initial.config, null, 2));
    } else {
      setName("");
      setConfigText("");
    }
    setConfigError(null);
  };

  // Seed form fields when dialog opens or initial changes
  useEffect(() => {
    if (open) resetToInitial();
  }, [open, initial]);

  const handleOpenChange = (v: boolean) => {
    onOpenChange(v);
  };

  const validateConfig = (text: string): Record<string, any> | null => {
    if (!text.trim()) {
      setConfigError("Config JSON is required");
      return null;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      setConfigError("Invalid JSON");
      return null;
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      setConfigError("Config must be a JSON object");
      return null;
    }
    const cfg = parsed as Record<string, any>;
    if (cfg.type !== "stdio" && cfg.type !== "http" && cfg.type !== "sse") {
      setConfigError('"type" must be "stdio", "http", or "sse"');
      return null;
    }
    if (cfg.type === "stdio" && !cfg.command) {
      setConfigError('"command" is required for stdio servers');
      return null;
    }
    if ((cfg.type === "http" || cfg.type === "sse") && !cfg.url) {
      setConfigError('"url" is required for HTTP/SSE servers';
      return null;
    }
    setConfigError(null);
    return cfg;
  };

  const handleSubmit = () => {
    if (!name.trim()) {
      toast.error("Server name is required");
      return;
    }
    const config = validateConfig(configText);
    if (!config) return;
    onSubmit({ name: name.trim(), config });
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit MCP Server" : "Add MCP Server"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update the configuration for this MCP server."
              : "Configure a new Model Context Protocol server."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="server-name">Name</Label>
            <Input
              id="server-name"
              placeholder="e.g. azure, my-server"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isEdit}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="server-config">Config</Label>
            <Textarea
              id="server-config"
              className="font-mono text-xs min-h-[120px]"
              placeholder={CONFIG_PLACEHOLDER}
              value={configText}
              onChange={(e) => {
                setConfigText(e.target.value);
                if (configError) setConfigError(null);
              }}
            />
            {configError && (
              <p className="text-xs text-destructive">{configError}</p>
            )}
            <p className="text-xs text-muted-foreground">
              JSON object with at least "type" ("stdio" or "http"), plus "command" (array) or "url".
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            {isEdit ? "Save Changes" : "Add Server"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ── Health Status Icon ────────────────────── */

function HealthIcon({ status }: { status: string }) {
  switch (status) {
    case "ok":
      return <CheckCircle className="h-4 w-4 text-green-500" />;
    case "degraded":
      return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
    case "unavailable":
      return <XCircle className="h-4 w-4 text-destructive" />;
    default:
      return <Activity className="h-4 w-4 text-muted-foreground" />;
  }
}

/* ── Main Page ─────────────────────────────── */

export default function McpServersPage() {
  const queryClient = useQueryClient();
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<McpServerEntry | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<McpServerEntry | null>(null);
  const [healthResults, setHealthResults] = useState<Record<string, McpServerHealthResult>>({});
  const [testingKeys, setTestingKeys] = useState<Set<string>>(new Set());

  // Fetch servers
  const {
    data: servers = [],
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["mcp-servers"],
    queryFn: mcpServersApi.list,
  });

  // Add mutation
  const addMutation = useMutation({
    mutationFn: (data: AddMcpServerRequest) => mcpServersApi.add(data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["mcp-servers"] });
      toast.success(`Server "${result.name}" added`);
      setAddDialogOpen(false);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Edit mutation (re-uses the add/update endpoint)
  const editMutation = useMutation({
    mutationFn: (data: AddMcpServerRequest) => mcpServersApi.add(data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["mcp-servers"] });
      toast.success(`Server "${result.name}" updated`);
      setEditTarget(null);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (key: string) => mcpServersApi.remove(key),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mcp-servers"] });
      toast.success("Server removed");
      setDeleteTarget(null);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Toggle disabled
  const toggleMutation = useMutation({
    mutationFn: ({ key, disabled }: { key: string; disabled: boolean }) =>
      mcpServersApi.setDisabled(key, disabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mcp-servers"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Test server
  const handleTest = async (name: string) => {
    setTestingKeys((prev) => new Set(prev).add(name));
    try {
      const result = await mcpServersApi.test(name);
      setHealthResults((prev) => ({ ...prev, [name]: result }));
      if (result.status === "ok") {
        toast.success(`${name}: ${result.detail || "OK"}`);
      } else {
        toast.warning(`${name}: ${result.status} — ${result.detail}`);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Test failed";
      toast.error(`${name}: ${msg}`);
    } finally {
      setTestingKeys((prev) => {
        const next = new Set(prev);
        next.delete(name);
        return next;
      });
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-9 w-28" />
        </div>
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="text-center py-16 text-sm text-destructive">
        Failed to load MCP servers: {(error as Error)?.message ?? "Unknown error"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold font-display tracking-wide text-foreground">
          MCP Servers
        </h1>
        <Button onClick={() => setAddDialogOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Add Server
        </Button>
      </div>

      {/* Empty state */}
      {servers.length === 0 && (
        <div className="text-center py-16 text-sm text-muted-foreground">
          <Network className="h-10 w-10 mx-auto mb-3 opacity-30" />
          No MCP servers configured. Add one to get started.
        </div>
      )}

      {/* Server list */}
      <div className="space-y-3">
        {servers.map((server) => {
          const health = healthResults[server.name];
          const isTesting = testingKeys.has(server.name);
          const transport = (server.config?.type as string) ?? "unknown";

          return (
            <Card
              key={server.name}
              className={`transition-colors ${server.disabled ? "opacity-60" : "hover:border-primary/30"}`}
            >
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-4">
                  {/* Left: info */}
                  <div className="flex items-start gap-3 min-w-0">
                    <div className="mt-0.5 text-primary shrink-0">
                      <Network className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-sm text-foreground font-medium">
                          {server.name}
                        </span>
                        <Badge variant="outline" className="text-[10px]">
                          {transport.toUpperCase()}
                        </Badge>
                        {server.disabled && (
                          <Badge variant="destructive" className="text-[10px]">
                            DISABLED
                          </Badge>
                        )}
                        {health && (
                          <span className="flex items-center gap-1 text-xs text-muted-foreground">
                            <HealthIcon status={health.status} />
                            {health.status}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground font-mono truncate max-w-lg">
                        {transport === "stdio"
                          ? (() => {
                              const cmd = server.config?.command;
                              const args = server.config?.args;
                              if (Array.isArray(cmd)) return cmd.join(" ");
                              if (typeof cmd === "string") {
                                return Array.isArray(args) ? [cmd, ...args].join(" ") : cmd;
                              }
                              return "—";
                            })()
                          : String(server.config?.url ?? "—")}
                      </p>
                      {health?.detail && (
                        <p className="text-xs text-muted-foreground">
                          {health.detail}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Right: actions */}
                  <div className="flex items-center gap-3 shrink-0">
                    <div className="flex items-center gap-2">
                      <Label htmlFor={`toggle-${server.name}`} className="text-xs text-muted-foreground">
                        {server.disabled ? "Disabled" : "Enabled"}
                      </Label>
                      <Switch
                        id={`toggle-${server.name}`}
                        checked={!server.disabled}
                        onCheckedChange={(checked) =>
                          toggleMutation.mutate({
                            key: server.name,
                            disabled: !checked,
                          })
                        }
                      />
                    </div>

                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setEditTarget(server)}
                    >
                      <Pencil className="h-4 w-4 mr-1" />
                      Edit
                    </Button>

                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleTest(server.name)}
                      disabled={isTesting}
                    >
                      {isTesting ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Activity className="h-4 w-4 mr-1" />
                      )}
                      Test
                    </Button>

                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setDeleteTarget(server)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Add dialog */}
      <ServerDialog
        open={addDialogOpen}
        onOpenChange={setAddDialogOpen}
        onSubmit={(data) => addMutation.mutate(data)}
        isSubmitting={addMutation.isPending}
      />

      {/* Edit dialog */}
      <ServerDialog
        open={!!editTarget}
        onOpenChange={(open) => !open && setEditTarget(null)}
        onSubmit={(data) => editMutation.mutate(data)}
        isSubmitting={editMutation.isPending}
        initial={editTarget ?? undefined}
      />

      {/* Delete confirmation */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove MCP Server</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to remove <strong>{deleteTarget?.name}</strong>?
              This will delete it from your config file.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.name)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
