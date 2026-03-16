import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { dashboardApi, scheduleApi } from "@/lib/api";

const COLORS = ["hsl(38 80% 52%)", "hsl(28 55% 48%)", "hsl(15 65% 50%)", "hsl(48 70% 50%)", "hsl(8 55% 45%)"];

const tooltipStyle = {
  backgroundColor: "hsl(220 10% 9%)",
  border: "1px solid hsl(220 8% 18%)",
  borderRadius: "8px",
  color: "hsl(40 50% 82%)",
};

const Metrics = () => {
  const [range, setRange] = useState("30");
  const since = useMemo(
    () => new Date(Date.now() - parseInt(range) * 86400_000).toISOString(),
    [range],
  );

  const { data: metrics, isLoading } = useQuery({
    queryKey: ["dashboard-metrics", since],
    queryFn: () => dashboardApi.metrics(since),
    refetchInterval: 10_000,
  });

  const { data: schedules } = useQuery({
    queryKey: ["schedules"],
    queryFn: () => scheduleApi.list(),
    refetchInterval: 30_000,
  });

  // Derive schedule performance
  const schedulePerf = useMemo(() => {
    if (!schedules) return [];
    return schedules
      .filter((s) => s.total_runs > 0)
      .map((s) => ({
        name: s.name,
        success: s.total_runs - s.consecutive_failures,
        total: s.total_runs,
      }));
  }, [schedules]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground font-display tracking-wide">Metrics</h1>
        <Select value={range} onValueChange={setRange}>
          <SelectTrigger className="w-40 bg-secondary border-border text-foreground">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7">Last 7 Days</SelectItem>
            <SelectItem value="30">Last 30 Days</SelectItem>
            <SelectItem value="90">Last 90 Days</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Sessions Over Time */}
      <Card className="bg-card border-border">
        <CardHeader><CardTitle className="text-foreground">Sessions Over Time</CardTitle></CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={metrics?.sessions_by_day ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(220 8% 18%)" />
                  <XAxis dataKey="date" stroke="hsl(35 25% 58%)" fontSize={11} />
                  <YAxis stroke="hsl(35 25% 58%)" fontSize={11} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend />
                  <Area type="monotone" dataKey="count" stroke="hsl(38 80% 52%)" fill="hsl(38 80% 52% / 0.15)" name="Sessions" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {/* Tool Usage */}
        <Card className="bg-card border-border">
          <CardHeader><CardTitle className="text-foreground">Tool Usage</CardTitle></CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={metrics?.top_tools ?? []} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(220 8% 18%)" />
                    <XAxis type="number" stroke="hsl(35 25% 58%)" fontSize={11} />
                    <YAxis dataKey="tool" type="category" stroke="hsl(35 25% 58%)" fontSize={11} width={120} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Bar dataKey="calls" fill="hsl(38 80% 52%)" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Error Breakdown */}
        <Card className="bg-card border-border">
          <CardHeader><CardTitle className="text-foreground">Error Breakdown</CardTitle></CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : (metrics?.error_breakdown?.length ?? 0) > 0 ? (
              <div className="flex items-center">
                <div className="h-48 w-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={metrics!.error_breakdown}
                        cx="50%"
                        cy="50%"
                        innerRadius={40}
                        outerRadius={70}
                        dataKey="count"
                        nameKey="type"
                        paddingAngle={3}
                        label
                      >
                        {metrics!.error_breakdown!.map((_, i) => (
                          <Cell key={i} fill={COLORS[i % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={tooltipStyle} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="space-y-2 ml-4">
                  {metrics!.error_breakdown!.map((e, i) => (
                    <div key={e.type} className="flex items-center gap-2">
                      <span className="h-3 w-3 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                      <span className="text-sm text-foreground">{e.type}</span>
                      <span className="text-xs text-muted-foreground">{e.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="h-48 flex items-center justify-center text-muted-foreground text-sm">
                No errors in this time range
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Schedule Performance */}
      {schedulePerf.length > 0 && (
        <Card className="bg-card border-border">
          <CardHeader><CardTitle className="text-foreground">Schedule Performance</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {schedulePerf.map((s) => (
              <div key={s.name} className="flex items-center justify-between">
                <span className="text-sm text-foreground">{s.name}</span>
                <div className="flex items-center gap-3">
                  <div className="w-32 h-2 rounded-full bg-secondary overflow-hidden">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${(s.success / s.total) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm text-muted-foreground w-16 text-right">
                    {s.success}/{s.total}
                  </span>
                  <span className={`text-xs ${s.success === s.total ? "text-success" : "text-warning"}`}>
                    {Math.round((s.success / s.total) * 100)}%
                  </span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Summary KPIs */}
      {metrics && (
        <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
          {[
            { label: "Total Sessions", value: metrics.total_sessions },
            { label: "Total Tool Calls", value: metrics.total_tool_calls },
            { label: "Documents Processed", value: metrics.total_documents_processed },
            { label: "Error Rate", value: `${(metrics.error_rate * 100).toFixed(1)}%` },
          ].map((kpi) => (
            <Card key={kpi.label} className="bg-card border-border">
              <CardContent className="pt-4">
                <p className="text-xs text-muted-foreground">{kpi.label}</p>
                <p className="text-2xl font-bold text-foreground mt-1">{kpi.value}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

export default Metrics;