import { useState, useMemo, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { dashboardApi } from "@/lib/api";
import type { DetailedMetrics, DailyDetailMetrics } from "@/types";

const CHART_STROKE = "hsl(38 80% 52%)";
const CHART_FILL = "hsl(38 80% 52% / 0.15)";
const CHART_SECONDARY = "hsl(15 65% 50%)";
const CHART_TERTIARY = "hsl(48 70% 50%)";
const GRID_STROKE = "hsl(220 8% 18%)";
const AXIS_STROKE = "hsl(35 25% 58%)";

const tooltipStyle = {
  backgroundColor: "hsl(220 10% 9%)",
  border: "1px solid hsl(220 8% 18%)",
  borderRadius: "8px",
  color: "hsl(40 50% 82%)",
};

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

function formatCost(cost: number): string {
  return `$${cost.toFixed(4)}`;
}

/** Tiny sparkline chart for trend visualization above tables */
function Sparkline({
  data,
  dataKey,
  secondaryKey,
  height = 120,
  type = "area",
}: {
  data: Record<string, unknown>[];
  dataKey: string;
  secondaryKey?: string;
  height?: number;
  type?: "area" | "bar";
}) {
  if (!data.length) return null;
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        {type === "bar" ? (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
            <XAxis dataKey="date" stroke={AXIS_STROKE} fontSize={10} tickLine={false} />
            <YAxis stroke={AXIS_STROKE} fontSize={10} tickLine={false} width={40} />
            <Tooltip contentStyle={tooltipStyle} />
            <Bar dataKey={dataKey} fill={CHART_STROKE} radius={[2, 2, 0, 0]} />
            {secondaryKey && <Bar dataKey={secondaryKey} fill={CHART_SECONDARY} radius={[2, 2, 0, 0]} />}
          </BarChart>
        ) : (
          <AreaChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
            <XAxis dataKey="date" stroke={AXIS_STROKE} fontSize={10} tickLine={false} />
            <YAxis stroke={AXIS_STROKE} fontSize={10} tickLine={false} width={40} />
            <Tooltip contentStyle={tooltipStyle} />
            <Area type="monotone" dataKey={dataKey} stroke={CHART_STROKE} fill={CHART_FILL} />
            {secondaryKey && (
              <Area type="monotone" dataKey={secondaryKey} stroke={CHART_SECONDARY} fill="hsl(15 65% 50% / 0.1)" />
            )}
          </AreaChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

/** A metric card with a sparkline and a data table */
function MetricTableCard({
  title,
  kpi,
  sparkData,
  sparkKey,
  sparkSecondaryKey,
  sparkType,
  headers,
  rows,
  isLoading,
  dateColumnIndex,
  onDateClick,
}: {
  title: string;
  kpi?: string;
  sparkData?: Record<string, unknown>[];
  sparkKey?: string;
  sparkSecondaryKey?: string;
  sparkType?: "area" | "bar";
  headers: string[];
  rows: (string | number)[][];
  isLoading: boolean;
  /** Which column (0-indexed) contains a clickable date (YYYY-MM-DD) */
  dateColumnIndex?: number;
  onDateClick?: (date: string) => void;
}) {
  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-foreground text-sm">{title}</CardTitle>
          {kpi && <span className="text-lg font-bold text-foreground">{kpi}</span>}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <Skeleton className="h-48 w-full" />
        ) : (
          <>
            {sparkData && sparkKey && (
              <Sparkline data={sparkData} dataKey={sparkKey} secondaryKey={sparkSecondaryKey} type={sparkType} />
            )}
            <div className="max-h-52 overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    {headers.map((h) => (
                      <TableHead key={h} className="text-xs text-muted-foreground">{h}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.length > 0 ? rows.map((row, i) => (
                    <TableRow
                      key={i}
                      className={dateColumnIndex !== undefined && onDateClick ? "cursor-pointer hover:bg-muted/50" : ""}
                      onClick={dateColumnIndex !== undefined && onDateClick ? () => onDateClick(String(row[dateColumnIndex])) : undefined}
                    >
                      {row.map((cell, j) => (
                        <TableCell
                          key={j}
                          className={`text-xs py-1.5 ${
                            j === dateColumnIndex && onDateClick
                              ? "text-primary underline decoration-dotted underline-offset-2 font-medium"
                              : "text-foreground"
                          }`}
                        >
                          {cell}
                        </TableCell>
                      ))}
                    </TableRow>
                  )) : (
                    <TableRow>
                      <TableCell colSpan={headers.length} className="text-center text-xs text-muted-foreground py-4">
                        No data in this time range
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}


// ── Daily Drill-Down Dialog ──────────────────────────────────────
function DailyDrillDownDialog({
  date,
  open,
  onOpenChange,
}: {
  date: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["daily-metrics", date],
    queryFn: () => dashboardApi.dailyMetrics(date!),
    enabled: open && !!date,
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto bg-card border-border">
        <DialogHeader>
          <DialogTitle className="text-foreground">Daily Details — {date}</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Drill-down view of all activity on this day
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : data ? (
          <div className="space-y-5 mt-2">
            {/* KPI summary row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: "Sessions", value: data.session_count },
                { label: "Completed", value: data.completed_count },
                { label: "Failed", value: data.failed_count },
                { label: "Tool Calls", value: data.total_tool_calls },
              ].map((kpi) => (
                <div key={kpi.label} className="rounded-lg border border-border bg-secondary/50 p-3">
                  <p className="text-xs text-muted-foreground">{kpi.label}</p>
                  <p className="text-lg font-bold text-foreground">{kpi.value}</p>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: "Tokens", value: formatNumber(data.total_tokens) },
                { label: "Cost", value: formatCost(data.total_cost) },
                { label: "Avg Duration", value: formatDuration(data.avg_duration) },
                { label: "Schedule Runs", value: data.total_schedule_runs },
              ].map((kpi) => (
                <div key={kpi.label} className="rounded-lg border border-border bg-secondary/50 p-3">
                  <p className="text-xs text-muted-foreground">{kpi.label}</p>
                  <p className="text-lg font-bold text-foreground">{kpi.value}</p>
                </div>
              ))}
            </div>

            {/* Sessions table */}
            {data.sessions.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-foreground mb-2">Sessions</h3>
                <div className="max-h-56 overflow-auto rounded-md border border-border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Instruction</TableHead>
                        <TableHead className="text-xs">Status</TableHead>
                        <TableHead className="text-xs">Duration</TableHead>
                        <TableHead className="text-xs">Tools</TableHead>
                        <TableHead className="text-xs">Tokens</TableHead>
                        <TableHead className="text-xs">Cost</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.sessions.map((s) => (
                        <TableRow key={s.id}>
                          <TableCell className="text-xs max-w-[200px] truncate" title={s.instruction}>{s.instruction || "—"}</TableCell>
                          <TableCell className="text-xs">
                            <Badge variant={s.status === "completed" ? "default" : s.status === "failed" ? "destructive" : "secondary"} className="text-[10px] px-1.5 py-0">
                              {s.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs">{formatDuration(s.duration)}</TableCell>
                          <TableCell className="text-xs">{s.tool_calls}</TableCell>
                          <TableCell className="text-xs">{formatNumber(s.tokens)}</TableCell>
                          <TableCell className="text-xs">{formatCost(s.cost)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            )}

            {/* Tool calls table */}
            {data.tool_calls.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-foreground mb-2">
                  Tool Calls
                  {data.total_tool_errors > 0 && (
                    <Badge variant="destructive" className="ml-2 text-[10px] px-1.5 py-0">{data.total_tool_errors} errors</Badge>
                  )}
                </h3>
                <div className="max-h-56 overflow-auto rounded-md border border-border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Tool</TableHead>
                        <TableHead className="text-xs">Status</TableHead>
                        <TableHead className="text-xs">Duration</TableHead>
                        <TableHead className="text-xs">Error</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.tool_calls.map((tc, i) => (
                        <TableRow key={i}>
                          <TableCell className="text-xs font-mono">{tc.tool_name}</TableCell>
                          <TableCell className="text-xs">
                            <Badge variant={tc.status === "success" ? "default" : tc.status === "error" ? "destructive" : "secondary"} className="text-[10px] px-1.5 py-0">
                              {tc.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs">{tc.duration_ms}ms</TableCell>
                          <TableCell className="text-xs text-destructive max-w-[200px] truncate" title={tc.error ?? undefined}>{tc.error ?? "—"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            )}

            {/* Schedule runs table */}
            {data.schedule_runs.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-foreground mb-2">Schedule Runs</h3>
                <div className="max-h-56 overflow-auto rounded-md border border-border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Schedule</TableHead>
                        <TableHead className="text-xs">Status</TableHead>
                        <TableHead className="text-xs">Duration</TableHead>
                        <TableHead className="text-xs">Trigger</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.schedule_runs.map((run, i) => (
                        <TableRow key={i}>
                          <TableCell className="text-xs">{run.name}</TableCell>
                          <TableCell className="text-xs">
                            <Badge variant={run.status === "completed" ? "default" : run.status === "failed" ? "destructive" : "secondary"} className="text-[10px] px-1.5 py-0">
                              {run.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs">{run.duration != null ? formatDuration(run.duration) : "—"}</TableCell>
                          <TableCell className="text-xs">{run.trigger_reason}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            )}

            {data.sessions.length === 0 && data.tool_calls.length === 0 && data.schedule_runs.length === 0 && (
              <div className="text-center text-muted-foreground text-sm py-8">No activity recorded on this day</div>
            )}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}


// ── Session Metrics Tab ──────────────────────────────────────────
function SessionsTab({ data, isLoading, onDateClick }: { data?: DetailedMetrics; isLoading: boolean; onDateClick: (date: string) => void }) {
  const s = data?.sessions;

  const tokenRows = useMemo(() => {
    if (!s) return [];
    return s.token_usage_by_day
      .filter((d) => d.total_tokens > 0)
      .slice(-15)
      .map((d) => [d.date, formatNumber(d.input_tokens), formatNumber(d.output_tokens), formatNumber(d.cache_tokens), formatNumber(d.total_tokens), formatCost(d.cost)]);
  }, [s]);

  const durationRows = useMemo(() => {
    if (!s) return [];
    return s.duration_by_day
      .filter((d) => d.session_count > 0)
      .slice(-15)
      .map((d) => [d.date, formatDuration(d.avg_duration), formatDuration(d.min_duration), formatDuration(d.max_duration), d.session_count]);
  }, [s]);

  const statusRows = useMemo(() => {
    if (!s) return [];
    return s.status_by_day
      .filter((d) => d.active + d.completed + d.failed + d.cancelled > 0)
      .slice(-15)
      .map((d) => [d.date, d.completed, d.failed, d.active, d.cancelled]);
  }, [s]);

  const docsRows = useMemo(() => {
    if (!s) return [];
    return s.documents_by_day
      .filter((d) => d.documents_processed + d.outputs_produced + d.errors > 0)
      .slice(-15)
      .map((d) => [d.date, d.documents_processed, d.outputs_produced, d.errors]);
  }, [s]);

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <MetricTableCard
        title="Token Usage & Cost"
        kpi={s ? formatCost(s.total_cost) : undefined}
        sparkData={s?.token_usage_by_day}
        sparkKey="total_tokens"
        isLoading={isLoading}
        headers={["Date", "Input", "Output", "Cache", "Total", "Cost"]}
        rows={tokenRows}
        dateColumnIndex={0}
        onDateClick={onDateClick}
      />
      <MetricTableCard
        title="Session Duration"
        kpi={s ? formatDuration(s.avg_duration) : undefined}
        sparkData={s?.duration_by_day}
        sparkKey="avg_duration"
        isLoading={isLoading}
        headers={["Date", "Avg", "Min", "Max", "Sessions"]}
        rows={durationRows}
        dateColumnIndex={0}
        onDateClick={onDateClick}
      />
      <MetricTableCard
        title="Status Distribution"
        sparkData={s?.status_by_day}
        sparkKey="completed"
        sparkSecondaryKey="failed"
        sparkType="bar"
        isLoading={isLoading}
        headers={["Date", "Completed", "Failed", "Active", "Cancelled"]}
        rows={statusRows}
        dateColumnIndex={0}
        onDateClick={onDateClick}
      />
      <MetricTableCard
        title="Document Processing"
        sparkData={s?.documents_by_day}
        sparkKey="documents_processed"
        isLoading={isLoading}
        headers={["Date", "Docs Processed", "Outputs", "Errors"]}
        rows={docsRows}
        dateColumnIndex={0}
        onDateClick={onDateClick}
      />
    </div>
  );
}


// ── Tool Calls Metrics Tab ───────────────────────────────────────
function ToolCallsTab({ data, isLoading, onDateClick }: { data?: DetailedMetrics; isLoading: boolean; onDateClick: (date: string) => void }) {
  const t = data?.tool_calls;

  const usageRows = useMemo(() => {
    if (!t) return [];
    return t.tool_usage.slice(0, 20).map((d) => [d.tool_name, d.total_calls, d.success_count, d.error_count, `${d.avg_duration_ms}ms`]);
  }, [t]);

  const errorRows = useMemo(() => {
    if (!t) return [];
    return t.tool_errors.slice(0, 15).map((d) => [d.tool_name, d.error_count, d.last_error ?? "—"]);
  }, [t]);

  const durationRows = useMemo(() => {
    if (!t) return [];
    return t.tool_duration.slice(0, 15).map((d) => [d.tool_name, `${d.avg_duration_ms}ms`, `${d.min_duration_ms}ms`, `${d.max_duration_ms}ms`]);
  }, [t]);

  const dailyRows = useMemo(() => {
    if (!t) return [];
    return t.tool_calls_by_day
      .filter((d) => d.count > 0)
      .slice(-15)
      .map((d) => [d.date, d.count]);
  }, [t]);

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <MetricTableCard
        title="Tool Usage"
        kpi={t ? formatNumber(t.total_tool_calls) : undefined}
        sparkData={t?.tool_calls_by_day}
        sparkKey="count"
        isLoading={isLoading}
        headers={["Tool", "Calls", "Success", "Errors", "Avg Duration"]}
        rows={usageRows}
      />
      <MetricTableCard
        title="Tool Duration"
        sparkData={t?.tool_calls_by_day}
        sparkKey="count"
        sparkType="bar"
        isLoading={isLoading}
        headers={["Tool", "Avg", "Min", "Max"]}
        rows={durationRows}
      />
      <MetricTableCard
        title="Tool Errors"
        kpi={t ? String(t.total_tool_errors) : undefined}
        isLoading={isLoading}
        headers={["Tool", "Error Count", "Last Error"]}
        rows={errorRows}
      />
      <MetricTableCard
        title="Daily Tool Calls"
        sparkData={t?.tool_calls_by_day}
        sparkKey="count"
        isLoading={isLoading}
        headers={["Date", "Calls"]}
        rows={dailyRows}
        dateColumnIndex={0}
        onDateClick={onDateClick}
      />
    </div>
  );
}


// ── Schedules Metrics Tab ────────────────────────────────────────
function SchedulesTab({ data, isLoading, onDateClick }: { data?: DetailedMetrics; isLoading: boolean; onDateClick: (date: string) => void }) {
  const sc = data?.schedules;

  const overviewRows = useMemo(() => {
    if (!sc) return [];
    return sc.schedule_overview.map((d) => [
      d.name,
      d.status,
      d.total_runs,
      `${d.success_rate}%`,
      d.last_run_at ? new Date(d.last_run_at).toLocaleDateString() : "—",
      d.next_run_at ? new Date(d.next_run_at).toLocaleDateString() : "—",
    ]);
  }, [sc]);

  const runsRows = useMemo(() => {
    if (!sc) return [];
    return sc.runs_by_day
      .filter((d) => d.runs > 0)
      .slice(-15)
      .map((d) => [d.date, d.runs, d.successes, d.failures]);
  }, [sc]);

  const durationRows = useMemo(() => {
    if (!sc) return [];
    return sc.schedule_duration.map((d) => [d.name, formatDuration(d.avg_duration), formatDuration(d.min_duration), formatDuration(d.max_duration)]);
  }, [sc]);

  const reliabilityRows = useMemo(() => {
    if (!sc) return [];
    return sc.schedule_reliability.map((d) => [d.name, d.total_runs, `${d.success_rate}%`, d.consecutive_failures]);
  }, [sc]);

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <MetricTableCard
        title="Schedule Overview"
        kpi={sc ? `${sc.total_runs} runs` : undefined}
        isLoading={isLoading}
        headers={["Name", "Status", "Runs", "Success %", "Last Run", "Next Run"]}
        rows={overviewRows}
      />
      <MetricTableCard
        title="Runs Over Time"
        sparkData={sc?.runs_by_day}
        sparkKey="runs"
        sparkSecondaryKey="failures"
        sparkType="bar"
        isLoading={isLoading}
        headers={["Date", "Runs", "Successes", "Failures"]}
        rows={runsRows}
        dateColumnIndex={0}
        onDateClick={onDateClick}
      />
      <MetricTableCard
        title="Schedule Duration"
        sparkData={sc?.runs_by_day}
        sparkKey="runs"
        isLoading={isLoading}
        headers={["Schedule", "Avg", "Min", "Max"]}
        rows={durationRows}
      />
      <MetricTableCard
        title="Schedule Reliability"
        isLoading={isLoading}
        headers={["Schedule", "Total Runs", "Success %", "Consec. Failures"]}
        rows={reliabilityRows}
      />
    </div>
  );
}


// ── Main Metrics Page ────────────────────────────────────────────
const Metrics = () => {
  const [days, setDays] = useState("30");
  const [drillDate, setDrillDate] = useState<string | null>(null);
  const [drillOpen, setDrillOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["detailed-metrics", days],
    queryFn: () => dashboardApi.detailedMetrics(parseInt(days)),
    refetchInterval: 30_000,
  });

  const handleDateClick = useCallback((date: string) => {
    setDrillDate(date);
    setDrillOpen(true);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground font-display tracking-wide">Metrics</h1>
        <Select value={days} onValueChange={setDays}>
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

      {/* Summary KPIs */}
      {data && (
        <div className="grid gap-4 grid-cols-2 md:grid-cols-5">
          {[
            { label: "Total Tokens", value: formatNumber(data.sessions.total_input_tokens + data.sessions.total_output_tokens) },
            { label: "Total Cost", value: formatCost(data.sessions.total_cost) },
            { label: "Avg Duration", value: formatDuration(data.sessions.avg_duration) },
            { label: "Tool Calls", value: formatNumber(data.tool_calls.total_tool_calls) },
            { label: "Schedule Runs", value: formatNumber(data.schedules.total_runs) },
          ].map((kpi) => (
            <Card key={kpi.label} className="bg-card border-border">
              <CardContent className="pt-4 pb-3">
                <p className="text-xs text-muted-foreground">{kpi.label}</p>
                <p className="text-xl font-bold text-foreground mt-1">{kpi.value}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Tabs defaultValue="sessions" className="w-full">
        <TabsList className="bg-secondary border border-border">
          <TabsTrigger value="sessions">Sessions</TabsTrigger>
          <TabsTrigger value="tool-calls">Tool Calls</TabsTrigger>
          <TabsTrigger value="schedules">Schedules</TabsTrigger>
        </TabsList>

        <TabsContent value="sessions" className="mt-4">
          <SessionsTab data={data} isLoading={isLoading} onDateClick={handleDateClick} />
        </TabsContent>

        <TabsContent value="tool-calls" className="mt-4">
          <ToolCallsTab data={data} isLoading={isLoading} onDateClick={handleDateClick} />
        </TabsContent>

        <TabsContent value="schedules" className="mt-4">
          <SchedulesTab data={data} isLoading={isLoading} onDateClick={handleDateClick} />
        </TabsContent>
      </Tabs>

      {/* Daily Drill-Down Dialog */}
      <DailyDrillDownDialog date={drillDate} open={drillOpen} onOpenChange={setDrillOpen} />
    </div>
  );
};

export default Metrics;