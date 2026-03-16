import { Link, useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft, Pencil, Trash2, Play, Pause, PlayCircle, CalendarClock } from "lucide-react";
import { toast } from "sonner";
import { scheduleApi } from "@/lib/api";
import { formatDate, formatDuration, statusIcon } from "@/lib/format";

const triggerLabel: Record<string, string> = {
  cron: "📅 Cron",
  interval: "🔄 Interval",
  event: "⚡ Event",
  webhook: "🔗 Webhook",
};

const ScheduleDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: schedule, isLoading } = useQuery({
    queryKey: ["schedule", id],
    queryFn: () => scheduleApi.get(id!),
    enabled: !!id,
    refetchInterval: 10_000,
  });

  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: ["schedule-history", id],
    queryFn: () => scheduleApi.history(id!, 50),
    enabled: !!id,
    refetchInterval: 10_000,
  });

  const pauseMutation = useMutation({
    mutationFn: () => scheduleApi.pause(id!),
    onSuccess: () => {
      toast.success("Schedule paused");
      queryClient.invalidateQueries({ queryKey: ["schedule", id] });
    },
  });

  const resumeMutation = useMutation({
    mutationFn: () => scheduleApi.resume(id!),
    onSuccess: () => {
      toast.success("Schedule resumed");
      queryClient.invalidateQueries({ queryKey: ["schedule", id] });
    },
  });

  const triggerMutation = useMutation({
    mutationFn: () => scheduleApi.trigger(id!),
    onSuccess: (data) => {
      toast.success(`Triggered → session ${data.session_id.slice(0, 8)}...`);
      queryClient.invalidateQueries({ queryKey: ["schedule-history", id] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => scheduleApi.delete(id!),
    onSuccess: () => {
      toast.success("Schedule deleted");
      navigate("/schedules");
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!schedule) {
    return (
      <div className="text-center text-muted-foreground py-20">
        Schedule not found.{" "}
        <Link to="/schedules" className="text-primary hover:underline">Back to schedules</Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            className="text-muted-foreground hover:text-foreground"
            onClick={() => navigate("/schedules")}
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <CalendarClock className="h-5 w-5 text-muted-foreground" />
          <h1 className="text-2xl font-bold text-foreground font-display tracking-wide">{schedule.name}</h1>
          <Badge
            variant={schedule.status === "active" ? "default" : "secondary"}
            className={schedule.status === "active" ? "bg-success/15 text-success" : ""}
          >
            {schedule.status}
          </Badge>
        </div>
        <div className="flex gap-2">
          {schedule.status === "active" ? (
            <Button
              variant="outline"
              size="sm"
              className="border-border text-muted-foreground hover:text-foreground"
              onClick={() => pauseMutation.mutate()}
            >
              <Pause className="h-3.5 w-3.5 mr-1" /> Pause
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="border-border text-muted-foreground hover:text-foreground"
              onClick={() => resumeMutation.mutate()}
            >
              <PlayCircle className="h-3.5 w-3.5 mr-1" /> Resume
            </Button>
          )}
          {(schedule.trigger.type === "cron" || schedule.trigger.type === "interval") && (
            <Button
              variant="outline"
              size="sm"
              className="border-border text-muted-foreground hover:text-foreground"
              onClick={() => triggerMutation.mutate()}
            >
              <Play className="h-3.5 w-3.5 mr-1" /> Trigger Now
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            className="border-border text-muted-foreground hover:text-foreground"
            onClick={() => navigate(`/schedules/${id}/edit`)}
          >
            <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="border-border text-destructive hover:text-destructive"
            onClick={() => deleteMutation.mutate()}
          >
            <Trash2 className="h-3.5 w-3.5 mr-1" /> Delete
          </Button>
        </div>
      </div>

      {/* Schedule Definition */}
      <Card className="bg-card border-border">
        <CardHeader><CardTitle className="text-foreground">Definition</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-y-3 gap-x-8 text-sm">
            {schedule.description && (
              <>
                <span className="text-muted-foreground">Description</span>
                <span className="text-foreground">{schedule.description}</span>
              </>
            )}
            <span className="text-muted-foreground">Trigger</span>
            <span className="text-foreground">{triggerLabel[schedule.trigger.type] || schedule.trigger.type}</span>

            {schedule.trigger.type === "cron" && (
              <>
                <span className="text-muted-foreground">Cron</span>
                <span className="text-foreground font-mono text-xs">{schedule.trigger.cron}</span>
                <span className="text-muted-foreground">Timezone</span>
                <span className="text-foreground">{schedule.trigger.timezone || "UTC"}</span>
              </>
            )}
            {schedule.trigger.type === "interval" && (
              <>
                <span className="text-muted-foreground">Interval</span>
                <span className="text-foreground">Every {schedule.trigger.interval_minutes} minutes</span>
              </>
            )}
            {schedule.trigger.type === "event" && (
              <>
                <span className="text-muted-foreground">Event Source</span>
                <span className="text-foreground font-mono text-xs">{schedule.trigger.event_source}</span>
                {schedule.trigger.event_filter && (
                  <>
                    <span className="text-muted-foreground">Event Filter</span>
                    <span className="text-foreground font-mono text-xs">{schedule.trigger.event_filter}</span>
                  </>
                )}
              </>
            )}
            {schedule.trigger.type === "webhook" && schedule.webhook_url && (
              <>
                <span className="text-muted-foreground">Webhook URL</span>
                <span className="text-foreground font-mono text-xs break-all">{schedule.webhook_url}</span>
              </>
            )}

            <span className="text-muted-foreground">Model</span>
            <span className="text-foreground">{schedule.options.model ?? "default"}</span>

            <span className="text-muted-foreground">Last Run</span>
            <span className="text-foreground">
              {schedule.last_run_at ? formatDate(schedule.last_run_at) : "Never"}
              {schedule.last_run_status && ` ${statusIcon(schedule.last_run_status)}`}
            </span>

            <span className="text-muted-foreground">Next Run</span>
            <span className="text-foreground">
              {schedule.next_run_at ? formatDate(schedule.next_run_at) : "On trigger"}
            </span>

            <span className="text-muted-foreground">Total Runs</span>
            <span className="text-foreground">{schedule.total_runs}</span>

            {schedule.consecutive_failures > 0 && (
              <>
                <span className="text-muted-foreground">Consecutive Failures</span>
                <span className="text-destructive">{schedule.consecutive_failures}</span>
              </>
            )}

            {schedule.tags.length > 0 && (
              <>
                <span className="text-muted-foreground">Tags</span>
                <div className="flex flex-wrap gap-1">
                  {schedule.tags.map((t) => (
                    <Badge key={t} variant="secondary" className="text-xs bg-secondary text-muted-foreground">
                      {t}
                    </Badge>
                  ))}
                </div>
              </>
            )}

            <span className="text-muted-foreground">Created</span>
            <span className="text-foreground">{formatDate(schedule.created_at)}</span>
          </div>

          {/* Instruction */}
          <div className="mt-4 space-y-1.5">
            <span className="text-sm text-muted-foreground">Instruction</span>
            <pre className="text-xs font-mono text-foreground bg-background rounded-lg p-3 whitespace-pre-wrap">
              {schedule.instruction}
            </pre>
          </div>
        </CardContent>
      </Card>

      {/* Run History */}
      <Card className="bg-card border-border">
        <CardHeader><CardTitle className="text-foreground">Run History</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-muted-foreground">Triggered</TableHead>
                <TableHead className="text-muted-foreground">Reason</TableHead>
                <TableHead className="text-muted-foreground">Status</TableHead>
                <TableHead className="text-muted-foreground">Duration</TableHead>
                <TableHead className="text-muted-foreground">Tools</TableHead>
                <TableHead className="text-muted-foreground">Docs</TableHead>
                <TableHead className="text-muted-foreground">Session</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {historyLoading
                ? Array.from({ length: 3 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      {Array.from({ length: 7 }).map((_, j) => (
                        <TableCell key={j}><Skeleton className="h-4 w-16" /></TableCell>
                      ))}
                    </TableRow>
                  ))
                : history?.map((run) => (
                    <TableRow key={run.id} className="border-border hover:bg-secondary/50">
                      <TableCell className="text-sm text-foreground">
                        {formatDate(run.triggered_at)}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {run.trigger_reason}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={
                            run.status === "completed"
                              ? "bg-success/10 text-success border-success/20"
                              : run.status === "failed"
                              ? "bg-destructive/10 text-destructive border-destructive/20"
                              : run.status === "running"
                              ? "bg-primary/10 text-primary border-primary/20"
                              : "bg-secondary text-muted-foreground"
                          }
                        >
                          {run.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {run.duration_seconds != null ? formatDuration(run.duration_seconds) : "—"}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {run.tool_calls ?? "—"}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {run.documents_processed ?? "—"}
                      </TableCell>
                      <TableCell>
                        <Link
                          to={`/sessions/${run.session_id}`}
                          className="text-primary hover:underline text-xs font-mono"
                        >
                          {run.session_id.slice(0, 8)}...
                        </Link>
                      </TableCell>
                    </TableRow>
                  ))}
              {!historyLoading && (!history || history.length === 0) && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                    No runs yet
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
};

export default ScheduleDetailPage;
