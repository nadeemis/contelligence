import { useMemo, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Search, Filter, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { agentApi } from "@/lib/api";
import { useSearchParam } from "@/hooks/useSearchParam";
import { formatDate, formatDuration, statusIcon } from "@/lib/format";

const statusConfig: Record<string, { label: string; className: string }> = {
  completed: { label: "Done", className: "bg-success/10 text-success border-success/20" },
  active: { label: "Active", className: "bg-primary/10 text-primary border-primary/20" },
  failed: { label: "Failed", className: "bg-destructive/10 text-destructive border-destructive/20" },
  waiting_approval: { label: "Waiting", className: "bg-warning/10 text-warning border-warning/20" },
  cancelled: { label: "Cancelled", className: "bg-muted text-muted-foreground border-border" },
};

const Sessions = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useSearchParam("status", "");
  const [search, setSearch] = useSearchParam("q", "");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState("");

  const { data: sessions, isLoading } = useQuery({
    queryKey: ["sessions", statusFilter],
    queryFn: () => agentApi.getSessions({ status: statusFilter || undefined }),
    refetchInterval: 5_000,
  });

  const filteredSessions = useMemo(() => {
    if (!sessions) return [];
    if (!search) return sessions;
    const q = search.toLowerCase();
    return sessions.filter(
      (s) => s.instruction.toLowerCase().includes(q) || s.id.includes(q)
    );
  }, [sessions, search]);

  const toggleSelect = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    setSelected((prev) =>
      prev.size === filteredSessions.length
        ? new Set()
        : new Set(filteredSessions.map((s) => s.id)),
    );
  }, [filteredSessions]);

  const bulkDeleteMutation = useMutation({
    mutationFn: async () => {
      const ids = Array.from(selected);
      await Promise.all(ids.map((id) => agentApi.deleteSession(id)));
    },
    onSuccess: () => {
      toast.success(`Deleted ${selected.size} session(s)`);
      setSelected(new Set());
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (err: Error) => {
      toast.error(err.message || "Failed to delete sessions");
    },
  });

  const allChecked = filteredSessions.length > 0 && selected.size === filteredSessions.length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground font-display tracking-wide">Sessions</h1>
        <div className="flex items-center gap-2">
          {selected.size > 0 && (
            <Button
              variant="outline"
              size="sm"
              className="border-border text-destructive hover:text-destructive"
              onClick={() => { setDeleteConfirm(""); setDeleteOpen(true); }}
            >
              <Trash2 className="h-3.5 w-3.5 mr-1" />
              Delete {selected.size}
            </Button>
          )}
          <Select value={statusFilter || "all"} onValueChange={(v) => setStatusFilter(v === "all" ? "" : v)}>
            <SelectTrigger className="w-32 bg-secondary border-border text-foreground">
              <Filter className="h-3 w-3 mr-1" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
              <SelectItem value="waiting_approval">Waiting</SelectItem>
              <SelectItem value="cancelled">Cancelled</SelectItem>
            </SelectContent>
          </Select>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search..."
              className="pl-9 w-48 bg-secondary border-border text-foreground"
            />
          </div>
        </div>
      </div>

      <Card className="bg-card border-border">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-border hover:bg-transparent">
                <TableHead className="w-10">
                  <Checkbox
                    checked={allChecked}
                    onCheckedChange={toggleAll}
                    aria-label="Select all sessions"
                  />
                </TableHead>
                <TableHead className="text-muted-foreground">ID</TableHead>
                <TableHead className="text-muted-foreground">Instruction</TableHead>
                <TableHead className="text-muted-foreground">Status</TableHead>
                <TableHead className="text-muted-foreground">Started/Updated</TableHead>
                <TableHead className="text-muted-foreground text-right">Tools</TableHead>
                <TableHead className="text-muted-foreground text-right">Duration</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 5 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      <TableCell><Skeleton className="h-4 w-4" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-12" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-48" /></TableCell>
                      <TableCell><Skeleton className="h-5 w-16" /></TableCell>
                      <TableCell className="text-right"><Skeleton className="h-4 w-8 ml-auto" /></TableCell>
                      <TableCell className="text-right"><Skeleton className="h-4 w-10 ml-auto" /></TableCell>
                    </TableRow>
                  ))
                : filteredSessions.map((s) => {
                    const cfg = statusConfig[s.status] ?? statusConfig.active;
                    return (
                      <TableRow
                        key={s.id}
                        className="border-border cursor-pointer hover:bg-secondary/50"
                        onClick={() => navigate(`/sessions/${s.id}`)}
                      >
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <Checkbox
                            checked={selected.has(s.id)}
                            onCheckedChange={() => toggleSelect(s.id)}
                            aria-label={`Select session ${s.id.slice(0, 8)}`}
                          />
                        </TableCell>
                        <TableCell className="font-mono text-primary text-sm">
                          {s.id.slice(0, 8)}
                        </TableCell>
                        <TableCell className="text-foreground max-w-xs truncate">
                          {s.instruction}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cfg.className + " text-xs"}>
                            {statusIcon(s.status)} {cfg.label}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {formatDate(s.updated_at ?? s.created_at)}
                        </TableCell>
                        <TableCell className="text-right text-muted-foreground">
                          {s.metrics.total_tool_calls}
                        </TableCell>
                        <TableCell className="text-right text-muted-foreground font-mono text-xs">
                          {formatDuration(s.metrics.total_duration_seconds)}
                        </TableCell>
                      </TableRow>
                    );
                  })}
              {!isLoading && filteredSessions.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                    No sessions found
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Bulk delete confirmation dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {selected.size} Session{selected.size === 1 ? "" : "s"}</DialogTitle>
            <DialogDescription>
              This will permanently delete the selected session{selected.size === 1 ? "" : "s"} and
              all related data (conversation logs, output artifacts, and stored
              blobs). This action cannot be undone.
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
              disabled={deleteConfirm.trim().toLowerCase() !== "yes" || bulkDeleteMutation.isPending}
              onClick={() => {
                bulkDeleteMutation.mutate();
                setDeleteOpen(false);
              }}
            >
              {bulkDeleteMutation.isPending ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Sessions;