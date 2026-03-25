import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { Skeleton } from "@/components/ui/skeleton";
import {
  Plus,
  Search,
  MoreHorizontal,
  Bot,
  Copy,
  Pencil,
  Archive,
  Trash2,
  CheckCircle,
  Power,
  ScrollText,
} from "lucide-react";
import { toast } from "sonner";
import { agentsApi, promptsApi } from "@/lib/api";
import { PromptEditDialog } from "@/components/PromptEditDialog";
import type { AgentSummary, AgentStatusType, PromptResponse } from "@/types";

const statusConfig: Record<
  AgentStatusType | "built-in",
  { label: string; className: string }
> = {
  "built-in": {
    label: "BUILT-IN",
    className: "bg-muted text-muted-foreground border-border",
  },
  active: {
    label: "ACTIVE",
    className: "bg-primary/15 text-primary border-primary/30",
  },
  draft: {
    label: "DRAFT",
    className: "bg-muted text-muted-foreground border-border",
  },
  archived: {
    label: "ARCHIVED",
    className: "bg-destructive/15 text-destructive border-destructive/30",
  },
};

export default function Agents() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [deleteTarget, setDeleteTarget] = useState<AgentSummary | null>(null);
  const [editingPrompt, setEditingPrompt] = useState<PromptResponse | null>(null);
  const [promptDialogOpen, setPromptDialogOpen] = useState(false);

  // ── Fetch agents ──
  const {
    data: agents = [],
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["agents", statusFilter, sourceFilter],
    queryFn: () =>
      agentsApi.list({
        status: statusFilter !== "all" ? statusFilter : undefined,
        source: sourceFilter !== "all" ? sourceFilter : undefined,
      }),
  });

  // ── Prompt management ──
  const { data: prompts = [] } = useQuery<PromptResponse[]>({
    queryKey: ["admin-prompts"],
    queryFn: promptsApi.list,
  });

  const promptsByAgent = new Map<string, PromptResponse>();
  for (const p of prompts) {
    // Map system prompt to "default" agent, agent prompts by their id
    promptsByAgent.set(p.id, p);
  }

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

  const openPromptEditor = (prompt: PromptResponse) => {
    setEditingPrompt(prompt);
    setPromptDialogOpen(true);
  };

  const findPromptForAgent = (agent: AgentSummary): PromptResponse | undefined => {
    // Only match agent-type prompts (system prompt is managed on Settings page)
    const match = promptsByAgent.get(agent.id) ?? prompts.find((p) => p.name === agent.display_name);
    return match?.prompt_type === "system" ? undefined : match;
  };

  // ── Mutations ──
  const cloneMutation = useMutation({
    mutationFn: (id: string) => agentsApi.clone(id),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      toast.success(`Cloned as "${result.id}"`);
      navigate(`/agents/${result.id}`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const updateStatusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: AgentStatusType }) =>
      agentsApi.update(id, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      toast.success("Agent status updated");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => agentsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      toast.success("Agent deleted");
      setDeleteTarget(null);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // ── Client-side search filter ──
  const filtered = agents.filter((a) => {
    if (
      search &&
      !a.display_name.toLowerCase().includes(search.toLowerCase()) &&
      !a.id.toLowerCase().includes(search.toLowerCase())
    )
      return false;
    return true;
  });

  const getDisplayStatus = (agent: AgentSummary) =>
    agent.source === "built-in" ? "built-in" : agent.status;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold font-display tracking-wide text-foreground">
          Agents
        </h1>
        <Button onClick={() => navigate("/agents/new")}>
          <Plus className="h-4 w-4 mr-2" />
          New Agent
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4 flex flex-wrap items-center gap-3">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="All" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="draft">Draft</SelectItem>
              <SelectItem value="archived">Archived</SelectItem>
            </SelectContent>
          </Select>
          <Select value={sourceFilter} onValueChange={setSourceFilter}>
            <SelectTrigger className="w-[150px]">
              <SelectValue placeholder="All Sources" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Sources</SelectItem>
              <SelectItem value="built-in">Built-in</SelectItem>
              <SelectItem value="user-created">Custom</SelectItem>
            </SelectContent>
          </Select>
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search agents..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
        </CardContent>
      </Card>

      {/* Loading state */}
      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="p-5 space-y-3">
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-3 w-96" />
                <Skeleton className="h-3 w-64" />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Error state */}
      {isError && (
        <Card>
          <CardContent className="p-8 text-center text-muted-foreground">
            Failed to load agents. Please try again.
          </CardContent>
        </Card>
      )}

      {/* Agent list */}
      {!isLoading && !isError && (
        <div className="space-y-3">
          {filtered.length === 0 && (
            <Card>
              <CardContent className="p-8 text-center text-muted-foreground">
                {search
                  ? "No agents match your search."
                  : "No agents found. Create your first agent to get started."}
              </CardContent>
            </Card>
          )}

          {filtered.map((agent) => {
            const displayStatus = getDisplayStatus(agent);
            const sc = statusConfig[displayStatus];
            const isCustom = agent.source === "user-created";
            const displayTools = agent.tools?.slice(0, 2);
            const extraTools = agent.tools ? agent.tools.length - 2 : 0;

            return (
              <Card
                key={agent.id}
                className="hover:border-primary/30 transition-colors"
              >
                <CardContent className="p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3 min-w-0">
                      <div className="mt-0.5 text-primary shrink-0">
                        <Bot className="h-5 w-5" />
                      </div>
                      <div className="min-w-0 space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-mono text-sm text-muted-foreground">
                            {agent.id}
                          </span>
                          <Badge variant="outline" className={sc.className}>
                            {sc.label}
                          </Badge>
                        </div>
                        <p className="font-semibold text-foreground">
                          {agent.display_name}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {agent.description}
                        </p>
                        <div className="flex items-center gap-4 text-xs text-muted-foreground pt-1 flex-wrap">
                          {agent.tools && agent.tools.length > 0 && (
                            <span>
                              Tools: {displayTools.join(", ")}
                              {extraTools > 0 && ` +${extraTools}`}
                            </span>
                          )}
                          {agent.tags && agent.tags.length > 0 && (
                            <span>Tags: {agent.tags.join(", ")}</span>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground">
                          Used: {agent.usage_count} times
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {(() => {
                        const prompt = findPromptForAgent(agent);
                        return prompt ? (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => openPromptEditor(prompt)}
                          >
                            <ScrollText className="h-3.5 w-3.5 mr-1" />
                            Prompt
                            {!prompt.is_default && (
                              <span className="ml-1 h-1.5 w-1.5 rounded-full bg-primary" />
                            )}
                          </Button>
                        ) : null;
                      })()}
                      {isCustom && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => navigate(`/agents/${agent.id}`)}
                        >
                          <Pencil className="h-3.5 w-3.5 mr-1" />
                          Edit
                        </Button>
                      )}
                      {isCustom && agent.status === "draft" && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            updateStatusMutation.mutate({
                              id: agent.id,
                              status: "active",
                            })
                          }
                        >
                          <CheckCircle className="h-3.5 w-3.5 mr-1" />
                          Activate
                        </Button>
                      )}
                      {isCustom && agent.status === "active" && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            updateStatusMutation.mutate({
                              id: agent.id,
                              status: "archived",
                            })
                          }
                        >
                          <Archive className="h-3.5 w-3.5 mr-1" />
                          Archive
                        </Button>
                      )}
                      {isCustom && agent.status === "archived" && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            updateStatusMutation.mutate({
                              id: agent.id,
                              status: "active",
                            })
                          }
                        >
                          <Power className="h-3.5 w-3.5 mr-1" />
                          Reactivate
                        </Button>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => cloneMutation.mutate(agent.id)}
                        disabled={cloneMutation.isPending}
                      >
                        <Copy className="h-3.5 w-3.5 mr-1" />
                        Clone
                      </Button>
                      {isCustom && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                            >
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => navigate(`/agents/${agent.id}`)}
                            >
                              View Details
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => cloneMutation.mutate(agent.id)}
                            >
                              Duplicate
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-destructive"
                              onClick={() => setDeleteTarget(agent)}
                            >
                              <Trash2 className="h-3.5 w-3.5 mr-2" />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Agent</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to permanently delete{" "}
              <strong>{deleteTarget?.display_name}</strong>? This action cannot
              be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() =>
                deleteTarget && deleteMutation.mutate(deleteTarget.id)
              }
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Prompt Edit Dialog */}
      <PromptEditDialog
        prompt={editingPrompt}
        open={promptDialogOpen}
        onOpenChange={setPromptDialogOpen}
        onSave={async (id, content) => {
          await saveMutation.mutateAsync({ id, content });
        }}
        onReset={async (id) => {
          await resetMutation.mutateAsync(id);
        }}
        isSaving={saveMutation.isPending || resetMutation.isPending}
      />
    </div>
  );
}