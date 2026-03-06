import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, Play, FileOutput, Wrench, Clock, FileText, AlertCircle } from "lucide-react";
import { agentApi } from "@/lib/api";
import { formatDate, formatDuration, formatBytes, statusIcon } from "@/lib/format";
import type { SessionRecord, ConversationTurn, OutputArtifact } from "@/types";

function SessionHeader({ session }: { session?: SessionRecord }) {
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
          Session {session.id.slice(0, 8)}
        </h1>
        <Badge variant="outline" className={statusColors[session.status] ?? statusColors.active}>
          {statusIcon(session.status)} {session.status}
        </Badge>
      </div>

      <p className="text-sm text-muted-foreground">{session.instruction}</p>

      <div className="flex items-center gap-6 text-sm text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <Wrench className="h-3.5 w-3.5" />
          <span>{session.metrics.total_tool_calls} tool calls</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Clock className="h-3.5 w-3.5" />
          <span>{formatDuration(session.metrics.total_duration_seconds)}</span>
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
        <span>Started {formatDate(session.created_at)}</span>
        {session.schedule_id && (
          <Link to={`/schedules/${session.schedule_id}`} className="text-primary hover:underline">
            Schedule: {session.schedule_id.slice(0, 8)}
          </Link>
        )}
      </div>

      {session.summary && (
        <Card className="bg-secondary/50 border-border">
          <CardContent className="p-3">
            <p className="text-sm text-foreground">{session.summary}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ConversationLog({ turns }: { turns: ConversationTurn[] }) {
  const roleStyles: Record<string, { icon: string; bg: string }> = {
    user: { icon: "👤", bg: "bg-accent/10" },
    assistant: { icon: "🤖", bg: "bg-primary/10" },
    tool: { icon: "🔧", bg: "bg-secondary" },
  };

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
            const style = roleStyles[turn.role] ?? roleStyles.assistant;
            return (
              <div key={turn.sequence} className={`rounded-lg p-3 ${style.bg}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span>{style.icon}</span>
                  <span className="text-xs font-medium text-muted-foreground uppercase">{turn.role}</span>
                  <span className="text-xs text-muted-foreground ml-auto">{formatDate(turn.timestamp)}</span>
                </div>
                {turn.prompt && (
                  <p className="text-sm text-foreground whitespace-pre-wrap">{turn.prompt}</p>
                )}
                {turn.content && (
                  <p className="text-sm text-foreground whitespace-pre-wrap">{turn.content}</p>
                )}
                {turn.reasoning && (
                  <p className="text-sm text-foreground whitespace-pre-wrap">{turn.reasoning}</p>
                )}
                {turn.tool_call && (
                  <div className="mt-2 rounded bg-background/50 p-2 font-mono text-xs">
                    <div className="flex items-center gap-2">
                      <span className="text-primary font-medium">{turn.tool_call.tool_name}</span>
                      <span className={turn.tool_call.success ? "text-success" : "text-destructive"}>
                        {turn.tool_call.success ? "✅" : "❌"}
                      </span>
                      <span className="text-muted-foreground">{turn.tool_call.duration_ms}ms</span>
                    </div>
                    <p className="text-muted-foreground mt-1">{turn.tool_call.result_summary}</p>
                  </div>
                )}
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}

function OutputList({ outputs }: { outputs: OutputArtifact[] }) {
  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-foreground">Output Artifacts</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="divide-y divide-border">
          {outputs.map((output) => (
            <div key={output.id} className="flex items-center justify-between py-3">
              <div className="flex items-center gap-3">
                <FileOutput className="h-4 w-4 text-muted-foreground" />
                <div>
                  <span className="text-sm font-mono text-foreground">{output.file_name}</span>
                  <p className="text-xs text-muted-foreground">{output.content_type} • {formatBytes(output.size_bytes)}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{formatDate(output.created_at)}</span>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs"
                  onClick={() =>
                    window.open(
                      `/api/agent/sessions/${output.session_id}/outputs/${output.id}/download`,
                      "_blank"
                    )
                  }
                >
                  Download
                </Button>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

const SessionDetailPage = () => {
  const { id } = useParams();

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

  const { data: outputs } = useQuery({
    queryKey: ["session-outputs", id],
    queryFn: () => agentApi.getSessionOutputs(id!),
    enabled: !!id && session?.status === "completed",
  });

  return (
    <div className="space-y-6">
      <Link to="/sessions" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to Sessions
      </Link>

      <SessionHeader session={session} />

      <div className="flex gap-2">
        <Button asChild variant="outline" className="border-border">
          <Link to={`/chat/${id}`}>
            <Play className="h-3.5 w-3.5 mr-1.5" /> Resume Session
          </Link>
        </Button>
      </div>

      <ConversationLog turns={logs ?? []} />

      {outputs && outputs.length > 0 && <OutputList outputs={outputs} />}
    </div>
  );
};

export default SessionDetailPage;
