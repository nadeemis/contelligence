import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Activity, Zap, AlertTriangle, Users } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { dashboardApi, scheduleApi } from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";
import { Link } from "react-router-dom";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardMetrics, ActivityEvent, ScheduleRecord } from "@/types";

const triggerIcons: Record<string, string> = {
  cron: "📅",
  interval: "🔄",
  event: "⚡",
  webhook: "🔗",
};

const tooltipStyle = {
  backgroundColor: "hsl(220 10% 9%)",
  border: "1px solid hsl(220 8% 18%)",
  borderRadius: "8px",
  color: "hsl(40 50% 82%)",
};

function MetricCard({
  title,
  value,
  icon: Icon,
  isLoading,
}: {
  title: string;
  value: string | number | undefined;
  icon: React.ElementType;
  isLoading: boolean;
}) {
  return (
    <Card className="bg-card border-border">
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <div className="rounded-lg bg-primary/10 p-2">
            <Icon className="h-4 w-4 text-primary" />
          </div>
        </div>
        <div className="mt-3">
          {isLoading ? (
            <Skeleton className="h-8 w-20" />
          ) : (
            <p className="text-2xl font-bold text-foreground">{value ?? "—"}</p>
          )}
          <p className="text-sm text-muted-foreground">{title}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function SessionsChart({ data }: { data: { date: string; count: number }[] }) {
  return (
    <Card className="bg-card border-border">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-foreground">Sessions Over Time</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(220 8% 18%)" />
              <XAxis dataKey="date" stroke="hsl(35 25% 58%)" fontSize={12} />
              <YAxis stroke="hsl(35 25% 58%)" fontSize={12} />
              <Tooltip contentStyle={tooltipStyle} />
              <Area type="monotone" dataKey="count" stroke="hsl(38 80% 52%)" fill="hsl(38 80% 52% / 0.15)" name="Sessions" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function ActivityFeed({ events, isLoading }: { events: ActivityEvent[]; isLoading: boolean }) {
  const typeColors: Record<string, string> = {
    session_completed: "bg-success",
    session_started: "bg-primary",
    tool_call: "bg-accent",
    schedule_fired: "bg-warning",
  };

  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-foreground">Recent Activity</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))
        ) : events.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">No recent activity</p>
        ) : (
          events.slice(0, 8).map((event, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
              <div className="flex items-center gap-3">
                <span className={`h-2 w-2 rounded-full ${typeColors[event.type] ?? "bg-muted-foreground"}`} />
                <span className="text-sm text-foreground font-mono">{event.summary}</span>
                {event.session_id && (
                  <Link to={`/sessions/${event.session_id}`} className="text-xs text-primary hover:underline">
                    {event.session_id.slice(0, 8)}
                  </Link>
                )}
              </div>
              <span className="text-xs text-muted-foreground">{formatRelativeTime(event.timestamp)}</span>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function ActiveSchedulesList({ schedules, isLoading }: { schedules: ScheduleRecord[]; isLoading: boolean }) {
  return (
    <Card className="bg-card border-border">
      <CardHeader>
        <CardTitle className="text-foreground">Active Schedules</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))
        ) : schedules.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">No active schedules</p>
        ) : (
          schedules.map((s) => (
            <Link
              key={s.id}
              to={`/schedules/${s.id}`}
              className="flex items-center justify-between rounded-lg bg-secondary/50 p-3 hover:bg-secondary/80 transition-colors"
            >
              <div className="flex items-center gap-3">
                <span className="text-lg">{triggerIcons[s.trigger.type] ?? "📅"}</span>
                <span className="text-sm text-foreground">{s.name}</span>
              </div>
              <span className="text-xs text-muted-foreground">
                {s.next_run_at ? `next ${new Date(s.next_run_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : "On trigger"}
              </span>
            </Link>
          ))
        )}
      </CardContent>
    </Card>
  );
}

const Dashboard = () => {
  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ["dashboard-metrics"],
    queryFn: () => dashboardApi.metrics(),
    refetchInterval: 10_000,
  });

  const { data: activity, isLoading: activityLoading } = useQuery({
    queryKey: ["dashboard-activity"],
    queryFn: () => dashboardApi.activity(20),
    refetchInterval: 10_000,
  });

  const { data: schedules, isLoading: schedulesLoading } = useQuery({
    queryKey: ["schedules", "active"],
    queryFn: () => scheduleApi.list({ status: "active" }),
    refetchInterval: 30_000,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground font-display tracking-wide">Dashboard</h1>
      </div>

      {/* KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard title="Sessions Today" value={metrics?.total_sessions} icon={Users} isLoading={metricsLoading} />
        <MetricCard title="Active Now" value={metrics?.active_sessions} icon={Activity} isLoading={metricsLoading} />
        <MetricCard title="Tool Calls" value={metrics?.total_tool_calls?.toLocaleString()} icon={Zap} isLoading={metricsLoading} />
        <MetricCard
          title="Error Rate"
          value={metrics ? `${((metrics.error_rate ?? 0) * 100).toFixed(1)}%` : undefined}
          icon={AlertTriangle}
          isLoading={metricsLoading}
        />
      </div>

      {/* Sessions Over Time Chart */}
      <SessionsChart data={metrics?.sessions_by_day ?? []} />

      {/* Bottom Row */}
      <div className="grid gap-4 md:grid-cols-2">
        <ActivityFeed events={activity ?? []} isLoading={activityLoading} />
        <ActiveSchedulesList schedules={schedules ?? []} isLoading={schedulesLoading} />
      </div>
    </div>
  );
};

export default Dashboard;