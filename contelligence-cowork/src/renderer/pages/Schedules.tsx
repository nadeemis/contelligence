import { Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Plus, Play, Pencil, Trash2, CalendarClock, Copy } from "lucide-react";
import { toast } from "sonner";
import { scheduleApi } from "@/lib/api";
import { formatDate, statusIcon } from "@/lib/format";
import type { ScheduleRecord } from "@/types";

const triggerBadge: Record<string, string> = {
  cron: "bg-primary/10 text-primary border-primary/20",
  interval: "bg-success/10 text-success border-success/20",
  event: "bg-warning/10 text-warning border-warning/20",
  webhook: "bg-accent/10 text-accent border-accent/20",
};

function formatTrigger(trigger: ScheduleRecord["trigger"]): string {
  switch (trigger.type) {
    case "cron":
      return trigger.cron ?? "cron";
    case "interval":
      return `every ${trigger.interval_minutes ?? "?"}m`;
    case "event":
      return trigger.event_source ?? "event";
    case "webhook":
      return "POST webhook";
    default:
      return trigger.type;
  }
}

const Schedules = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: schedules, isLoading } = useQuery({
    queryKey: ["schedules"],
    queryFn: () => scheduleApi.list(),
    refetchInterval: 10_000,
  });

  const pauseMutation = useMutation({
    mutationFn: scheduleApi.pause,
    onMutate: async (scheduleId) => {
      await queryClient.cancelQueries({ queryKey: ["schedules"] });
      const prev = queryClient.getQueryData<ScheduleRecord[]>(["schedules"]);
      queryClient.setQueryData<ScheduleRecord[]>(["schedules"], (old) =>
        old?.map((s) => (s.id === scheduleId ? { ...s, status: "paused" as const } : s))
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      queryClient.setQueryData(["schedules"], ctx?.prev);
      toast.error("Failed to pause schedule");
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["schedules"] }),
  });

  const resumeMutation = useMutation({
    mutationFn: scheduleApi.resume,
    onMutate: async (scheduleId) => {
      await queryClient.cancelQueries({ queryKey: ["schedules"] });
      const prev = queryClient.getQueryData<ScheduleRecord[]>(["schedules"]);
      queryClient.setQueryData<ScheduleRecord[]>(["schedules"], (old) =>
        old?.map((s) => (s.id === scheduleId ? { ...s, status: "active" as const } : s))
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      queryClient.setQueryData(["schedules"], ctx?.prev);
      toast.error("Failed to resume schedule");
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["schedules"] }),
  });

  const triggerMutation = useMutation({
    mutationFn: scheduleApi.trigger,
    onSuccess: (data) => {
      toast.success(`Triggered → session ${data.session_id.slice(0, 8)}...`);
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
    },
    onError: () => toast.error("Failed to trigger schedule"),
  });

  const deleteMutation = useMutation({
    mutationFn: scheduleApi.delete,
    onSuccess: () => {
      toast.success("Schedule deleted");
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
    },
    onError: () => toast.error("Failed to delete schedule"),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground font-display tracking-wide">Schedules</h1>
        <Button asChild className="bg-primary text-primary-foreground hover:bg-primary/90">
          <Link to="/schedules/new">
            <Plus className="h-4 w-4 mr-2" /> New Schedule
          </Link>
        </Button>
      </div>

      <Card className="bg-card border-border">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="text-muted-foreground">Name</TableHead>
                <TableHead className="text-muted-foreground">Trigger</TableHead>
                <TableHead className="text-muted-foreground">Schedule</TableHead>
                <TableHead className="text-muted-foreground">Last Run</TableHead>
                <TableHead className="text-muted-foreground">Next Run</TableHead>
                <TableHead className="text-muted-foreground">Runs</TableHead>
                <TableHead className="text-muted-foreground">Enabled</TableHead>
                <TableHead className="text-muted-foreground text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 4 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-12" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-10" /></TableCell>
                      <TableCell><Skeleton className="h-8 w-24 ml-auto" /></TableCell>
                    </TableRow>
                  ))
                : schedules?.map((s) => (
                    <TableRow
                      key={s.id}
                      className="border-border hover:bg-secondary/50 cursor-pointer"
                      onClick={() => navigate(`/schedules/${s.id}`)}
                    >
                      <TableCell className="text-foreground font-medium">
                        <div className="flex items-center gap-2">
                          <CalendarClock className="h-4 w-4 text-muted-foreground" />
                          {s.name}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={(triggerBadge[s.trigger.type] ?? "") + " text-xs"}>
                          {s.trigger.type}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {formatTrigger(s.trigger)}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {s.last_run_at ? formatDate(s.last_run_at) : "Never"}
                        {s.last_run_status && ` ${statusIcon(s.last_run_status)}`}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {s.next_run_at ? formatDate(s.next_run_at) : "On trigger"}
                      </TableCell>
                      <TableCell>
                        <span className="text-sm text-foreground">{s.total_runs}</span>
                        {s.consecutive_failures > 0 && (
                          <span className="text-xs text-destructive ml-1">
                            ({s.consecutive_failures} failed)
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Switch
                          checked={s.status === "active"}
                          onClick={(e) => e.stopPropagation()}
                          onCheckedChange={() =>
                            s.status === "active"
                              ? pauseMutation.mutate(s.id)
                              : resumeMutation.mutate(s.id)
                          }
                        />
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                          {(s.trigger.type === "cron" || s.trigger.type === "interval") && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-muted-foreground hover:text-foreground"
                              onClick={() => triggerMutation.mutate(s.id)}
                              title="Trigger Now"
                            >
                              <Play className="h-3.5 w-3.5" />
                            </Button>
                          )}
                          {s.trigger.type === "webhook" && s.webhook_url && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-muted-foreground hover:text-foreground"
                              onClick={() => {
                                navigator.clipboard.writeText(s.webhook_url!);
                                toast.success("Webhook URL copied");
                              }}
                              title="Copy Webhook URL"
                            >
                              <Copy className="h-3.5 w-3.5" />
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-muted-foreground hover:text-foreground"
                            onClick={() => navigate(`/schedules/${s.id}/edit`)}
                            title="Edit"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-muted-foreground hover:text-destructive"
                            onClick={() => deleteMutation.mutate(s.id)}
                            title="Delete"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
              {!isLoading && (!schedules || schedules.length === 0) && (
                <TableRow>
                  <TableCell colSpan={8} className="text-center text-muted-foreground py-8">
                    No schedules found. <Link to="/schedules/new" className="text-primary hover:underline">Create one</Link>
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

export default Schedules;