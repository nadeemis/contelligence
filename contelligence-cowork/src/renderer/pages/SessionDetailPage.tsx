import React, { useState, useRef, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ArrowLeft, Play, FileOutput, Wrench, Clock, FileText, AlertCircle, Trash2, User, Brain, Hash, DollarSign, ArrowDownToLine, ArrowUpFromLine } from "lucide-react";
import { MarkdownContent } from "@/components/MarkdownContent";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { ToolResultCard } from "@/components/chat/ToolResultCard";
import { toast } from "sonner";
import { agentApi } from "@/lib/api";
import { formatDate, formatDuration, formatBytes, statusIcon } from "@/lib/format";
import type { SessionRecord, ConversationTurn, OutputArtifact } from "@/types";
import type { AgentEventUnion } from "@/types/agent-events";

function SessionHeader({ session, actions }: { session?: SessionRecord; actions?: React.ReactNode }) {
  const [summaryExpanded, setSummaryExpanded] = useState(false);
  const [summaryOverflows, setSummaryOverflows] = useState(false);
  const summaryRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!summaryExpanded && summaryRef.current) {
      setSummaryOverflows(summaryRef.current.scrollHeight > summaryRef.current.clientHeight);
    }
  }, [session?.summary, summaryExpanded]);

  if (!session) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-96" />
      </div>
    );
  }

  const statusColors: Record<string, string> = {
    completed: "bg-success/10 text-success border-success/20",
    active: "bg-primary/10 text-primary border-primary/20",
    failed: "bg-destructive/10 text-destructive border-destructive/20",
    waiting_approval: "bg-warning/10 text-warning border-warning/20",
    cancelled: "bg-muted text-muted-foreground border-border",
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold text-foreground font-display tracking-wide">
          Session {session.id}
        </h1>
        <Badge variant="outline" className={statusColors[session.status] ?? statusColors.active}>
          {statusIcon(session.status)} {session.status}
        </Badge>
      </div>

      <p className="text-sm text-muted-foreground">{session.instruction}</p>

      <div className="space-y-2 text-sm text-muted-foreground">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-1.5">
            <Wrench className="h-3.5 w-3.5" />
            <span>{session.metrics.total_tool_calls} tool calls</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Clock className="h-3.5 w-3.5" />
            <span>{formatDuration(session.metrics.total_duration_seconds)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Brain className="h-3.5 w-3.5" />
            <span>Model {session.metrics.model}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5" />
            <span>{session.metrics.documents_processed} docs</span>
          </div>
          {session.metrics.errors_encountered > 0 && (
            <div className="flex items-center gap-1.5 text-destructive">
              <AlertCircle className="h-3.5 w-3.5" />
              <span>{session.metrics.errors_encountered} errors</span>
            </div>
          )}
          <div className="flex items-center gap-1.5">
            <Clock className="h-3.5 w-3.5" />
            <span>{formatDate(session.created_at)}</span>
          </div>
          {session.schedule_id && (
            <Link to={`/schedules/${session.schedule_id}`} className="text-primary hover:underline">
              Schedule: {session.schedule_id.slice(0, 8)}
            </Link>
          )}
          {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
        </div>
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-1.5">
            <ArrowDownToLine className="h-3.5 w-3.5" />
            <span>{(session.metrics.input_tokens ?? 0).toLocaleString()} input tokens</span>
          </div>
          <div className="flex items-center gap-1.5">
            <ArrowUpFromLine className="h-3.5 w-3.5" />
            <span>{(session.metrics.output_tokens ?? 0).toLocaleString()} output tokens</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Hash className="h-3.5 w-3.5" />
            <span>{(session.metrics.total_tokens_used).toLocaleString()} total tokens</span>
          </div>
          {session.metrics.cost != null && (
            <div className="flex items-center gap-1.5">
              <DollarSign className="h-3.5 w-3.5" />
              <span>${session.metrics.cost.toFixed(4)} cost</span>
            </div>
          )}
        </div>
      </div>

      {session.summary && (
        <Card className="bg-secondary/50 border-border">
          <CardHeader>
            <CardTitle className="text-foreground">Summary</CardTitle>
          </CardHeader>
          <CardContent className="p-3 pt-0">
            <div
              ref={summaryRef}
              className={`relative ${summaryExpanded ? "" : "max-h-[15rem] overflow-hidden"}`}
            >
              <MarkdownContent className="text-sm text-foreground">{session.summary}</MarkdownContent>
              {!summaryExpanded && summaryOverflows && (
                <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-secondary/50 to-transparent" />
              )}
            </div>
            {summaryOverflows && (
              <Button
                variant="ghost"
                size="sm"
                className="mt-1 h-7 text-xs text-muted-foreground hover:text-foreground"
                onClick={() => setSummaryExpanded(!summaryExpanded)}
              >
                {summaryExpanded ? "Show less" : "Show more"}
              </Button>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ConversationLog({ turns }: { turns: ConversationTurn[] }) {
  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-foreground">Conversation Log</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {turns.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">No conversation turns</p>
        ) : (
          turns.map((turn) => {
            const key = `turn-${turn.sequence}`;

            if (turn.role === "user") {
              if (!turn.prompt) return null;
              return (
                <div key={key} className="flex gap-3">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/20">
                    <User className="h-3.5 w-3.5 text-accent" />
                  </div>
                  <div className="rounded-lg bg-secondary p-3 max-w-[80%]">
                    <p className="text-sm text-foreground">{turn.prompt}</p>
                  </div>
                </div>
              );
            }

            if (turn.role === "tool" && turn.tool_call) {
              return (
                <ToolResultCard
                  key={key}
                  callId={turn.tool_call.tool_name}
                  toolName={turn.tool_call.tool_name}
                  result={turn.tool_call.error ?? turn.tool_call.result ?? ""}
                  parameters={turn.tool_call.parameters}
                  timestamp={turn.timestamp}
                  startedAt={turn.tool_call.started_at}
                  completedAt={turn.tool_call.completed_at}
                  durationMs={turn.tool_call.duration_ms}
                  sessionId={turn.session_id}
                  sequence={turn.sequence}
                />
              );
            }

            if (turn.role === "assistant") {
              return (
                <React.Fragment key={key}>
                  {turn.reasoning && (
                    <ChatMessage
                      event={{ type: "thinking", content: turn.reasoning, timestamp: turn.timestamp, payload: {} } as AgentEventUnion}
                      onApprove={() => {}}
                    />
                  )}
                  {turn.content && (
                    <ChatMessage
                      event={{ type: "message", content: turn.content, timestamp: turn.timestamp, payload: {} } as AgentEventUnion}
                      onApprove={() => {}}
                    />
                  )}
                </React.Fragment>
              );
            }

            return null;
          })
        )}
      </CardContent>
    </Card>
  );
}


const SessionDetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState("");

  const { data: session } = useQuery({
    queryKey: ["session", id],
    queryFn: () => agentApi.getSession(id!),
    enabled: !!id,
    refetchInterval: (query) =>
      query.state.data?.status === "active" ? 3_000 : false,
  });

  const { data: logs } = useQuery({
    queryKey: ["session-logs", id],
    queryFn: () => agentApi.getSessionLogs(id!),
    enabled: !!id,
    refetchInterval: (query) =>
      session?.status === "active" ? 3_000 : false,
  });

  const deleteMutation = useMutation({
    mutationFn: () => agentApi.deleteSession(id!),
    onSuccess: () => {
      toast.success("Session deleted");
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
      navigate("/sessions");
    },
    onError: (err: Error) => {
      toast.error(err.message || "Failed to delete session");
    },
  });

  return (
    <div className="space-y-6">
      <Link to="/sessions" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to Sessions
      </Link>

      <SessionHeader
        session={session}
        actions={
          <>
            <Button asChild variant="outline" size="sm" className="border-border">
              <Link to={`/chat/${id}`}>
                <Play className="h-3.5 w-3.5 mr-1.5" /> Resume Session
              </Link>
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="border-border text-destructive hover:text-destructive"
              onClick={() => { setDeleteConfirm(""); setDeleteOpen(true); }}
            >
              <Trash2 className="h-3.5 w-3.5 mr-1" /> Delete Session
            </Button>
          </>
        }
      />

      {/* Delete confirmation dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Session</DialogTitle>
            <DialogDescription>
              This will permanently delete the session and all related data
              (conversation logs, output artifacts, and stored blobs). This
              action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Type <strong>yes</strong> to confirm.
            </p>
            <Input
              value={deleteConfirm}
              onChange={(e) => setDeleteConfirm(e.target.value)}
              placeholder="yes"
              className="bg-secondary border-border"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleteConfirm.trim().toLowerCase() !== "yes" || deleteMutation.isPending}
              onClick={() => {
                deleteMutation.mutate();
                setDeleteOpen(false);
              }}
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConversationLog turns={logs ?? []} />

    </div>
  );
};

export default SessionDetailPage;
