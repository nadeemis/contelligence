import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
  Copy,
  Filter,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Search,
  Sparkles,
  Tags,
  Trash2,
  X,
} from "lucide-react";
import { agentApi } from "@/lib/api";
import { useSearchParam } from "@/hooks/useSearchParam";
import { formatDate, formatDuration, statusIcon } from "@/lib/format";
import { SessionTagEditor } from "@/components/SessionTagEditor";
import { RenameSessionDialog } from "@/components/RenameSessionDialog";
import { DuplicateSessionDialog } from "@/components/DuplicateSessionDialog";
import type { SessionRecord } from "@/types";

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
  const [tagsParam, setTagsParam] = useSearchParam("tags", "");
  const [pinnedFirst, setPinnedFirst] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [renameTarget, setRenameTarget] = useState<SessionRecord | null>(null);
  const [duplicateTarget, setDuplicateTarget] = useState<string | null>(null);

  const selectedTags = useMemo(
    () => (tagsParam ? tagsParam.split(",").filter(Boolean) : []),
    [tagsParam],
  );

  const { data: sessions, isLoading } = useQuery({
    queryKey: ["sessions", statusFilter, selectedTags, search, pinnedFirst],
    queryFn: () =>
      agentApi.getSessions({
        status: statusFilter || undefined,
        tags: selectedTags.length ? selectedTags.join(",") : undefined,
        search: search || undefined,
        pinned_first: pinnedFirst,
      }),
    refetchInterval: 5_000,
  });

  const { data: tagOptions } = useQuery({
    queryKey: ["session-tags"],
    queryFn: () => agentApi.getSessionTags(),
    staleTime: 30_000,
  });

  const list = sessions ?? [];

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
      prev.size === list.length ? new Set() : new Set(list.map((s) => s.id)),
    );
  }, [list]);

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

  const pinMutation = useMutation({
    mutationFn: ({ id, pinned }: { id: string; pinned: boolean }) =>
      agentApi.pinSession(id, pinned),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (err: Error) => {
      toast.error(err.message || "Could not update pin");
    },
  });

  const toggleTag = (tag: string) => {
    const next = selectedTags.includes(tag)
      ? selectedTags.filter((t) => t !== tag)
      : [...selectedTags, tag];
    setTagsParam(next.join(","));
  };

  const clearTags = () => setTagsParam("");

  const allChecked = list.length > 0 && selected.size === list.length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold text-foreground font-display tracking-wide">
          Sessions
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          {selected.size > 0 && (
            <Button
              variant="outline"
              size="sm"
              className="border-border text-destructive hover:text-destructive"
              onClick={() => {
                setDeleteConfirm("");
                setDeleteOpen(true);
              }}
            >
              <Trash2 className="h-3.5 w-3.5 mr-1" />
              Delete {selected.size}
            </Button>
          )}
          <Select
            value={statusFilter || "all"}
            onValueChange={(v) => setStatusFilter(v === "all" ? "" : v)}
          >
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

          <Popover>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="h-9 gap-2 bg-secondary border-border text-foreground"
              >
                <Tags className="h-3.5 w-3.5" />
                Tags
                {selectedTags.length > 0 && (
                  <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-xs">
                    {selectedTags.length}
                  </Badge>
                )}
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-64 p-2">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-muted-foreground">
                  Filter by tag
                </span>
                {selectedTags.length > 0 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-xs"
                    onClick={clearTags}
                  >
                    Clear
                  </Button>
                )}
              </div>
              <div className="max-h-60 overflow-y-auto space-y-1">
                {(tagOptions ?? []).length === 0 && (
                  <p className="text-xs text-muted-foreground text-center py-4">
                    No tags yet
                  </p>
                )}
                {(tagOptions ?? []).map((t) => (
                  <label
                    key={t.tag}
                    className="flex items-center gap-2 px-1 py-1 rounded hover:bg-accent cursor-pointer text-sm"
                  >
                    <Checkbox
                      checked={selectedTags.includes(t.tag)}
                      onCheckedChange={() => toggleTag(t.tag)}
                    />
                    <span className="flex-1 truncate">{t.tag}</span>
                    <span className="text-xs text-muted-foreground">
                      {t.count}
                    </span>
                  </label>
                ))}
              </div>
            </PopoverContent>
          </Popover>

          <Button
            variant={pinnedFirst ? "default" : "outline"}
            size="sm"
            className="h-9 gap-2"
            onClick={() => setPinnedFirst((v) => !v)}
            title="Show pinned sessions first"
          >
            <Pin className="h-3.5 w-3.5" />
            Pinned first
          </Button>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search title or instruction..."
              className="pl-9 w-56 bg-secondary border-border text-foreground"
            />
          </div>
        </div>
      </div>

      {selectedTags.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted-foreground">Active tag filters:</span>
          {selectedTags.map((t) => (
            <Badge
              key={t}
              variant="secondary"
              className="gap-1 cursor-pointer"
              onClick={() => toggleTag(t)}
            >
              {t}
              <X className="h-3 w-3" />
            </Badge>
          ))}
        </div>
      )}

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
                <TableHead className="w-8"></TableHead>
                <TableHead className="text-muted-foreground">Title / Instruction</TableHead>
                <TableHead className="text-muted-foreground">Tags</TableHead>
                <TableHead className="text-muted-foreground">Status</TableHead>
                <TableHead className="text-muted-foreground">Updated</TableHead>
                <TableHead className="text-muted-foreground text-right">Tools</TableHead>
                <TableHead className="text-muted-foreground text-right">Duration</TableHead>
                <TableHead className="w-8"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading
                ? Array.from({ length: 5 }).map((_, i) => (
                    <TableRow key={i} className="border-border">
                      <TableCell>
                        <Skeleton className="h-4 w-4" />
                      </TableCell>
                      <TableCell></TableCell>
                      <TableCell>
                        <Skeleton className="h-4 w-48" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-4 w-20" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-5 w-16" />
                      </TableCell>
                      <TableCell>
                        <Skeleton className="h-4 w-24" />
                      </TableCell>
                      <TableCell className="text-right">
                        <Skeleton className="h-4 w-8 ml-auto" />
                      </TableCell>
                      <TableCell className="text-right">
                        <Skeleton className="h-4 w-10 ml-auto" />
                      </TableCell>
                      <TableCell></TableCell>
                    </TableRow>
                  ))
                : list.map((s) => {
                    const cfg = statusConfig[s.status] ?? statusConfig.active;
                    const displayTitle = s.title?.trim() || s.instruction;
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
                            aria-label={`Select session ${s.id.slice(0, 12)}`}
                          />
                        </TableCell>
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            onClick={() =>
                              pinMutation.mutate({ id: s.id, pinned: !s.pinned })
                            }
                            title={s.pinned ? "Unpin" : "Pin"}
                          >
                            {s.pinned ? (
                              <Pin className="h-3.5 w-3.5 text-primary fill-primary" />
                            ) : (
                              <Pin className="h-3.5 w-3.5 text-muted-foreground" />
                            )}
                          </Button>
                        </TableCell>
                        <TableCell className="max-w-sm">
                          <div className="flex flex-col gap-0.5">
                            <span className="text-foreground truncate font-medium">
                              {displayTitle}
                              {s.title_source === "auto" && (
                                <Sparkles className="inline-block h-3 w-3 ml-1 text-muted-foreground" />
                              )}
                            </span>
                            {s.title && s.title !== s.instruction && (
                              <span className="text-xs text-muted-foreground truncate">
                                {s.instruction}
                              </span>
                            )}
                            <span className="text-[10px] text-muted-foreground/70 font-mono truncate">
                              {s.id}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <SessionTagEditor
                            sessionId={s.id}
                            tags={s.tags ?? []}
                            compact
                          />
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
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7"
                                aria-label="Session actions"
                              >
                                <MoreHorizontal className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => setRenameTarget(s)}>
                                <Pencil className="h-3.5 w-3.5 mr-2" />
                                Rename
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                onClick={() =>
                                  pinMutation.mutate({
                                    id: s.id,
                                    pinned: !s.pinned,
                                  })
                                }
                              >
                                {s.pinned ? (
                                  <>
                                    <PinOff className="h-3.5 w-3.5 mr-2" />
                                    Unpin
                                  </>
                                ) : (
                                  <>
                                    <Pin className="h-3.5 w-3.5 mr-2" />
                                    Pin
                                  </>
                                )}
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem onClick={() => setDuplicateTarget(s.id)}>
                                <Copy className="h-3.5 w-3.5 mr-2" />
                                Duplicate…
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    );
                  })}
              {!isLoading && list.length === 0 && (
                <TableRow>
                  <TableCell colSpan={9} className="text-center text-muted-foreground py-8">
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
            <DialogTitle>
              Delete {selected.size} Session{selected.size === 1 ? "" : "s"}
            </DialogTitle>
            <DialogDescription>
              This will permanently delete the selected session
              {selected.size === 1 ? "" : "s"} and all related data (conversation
              logs, output artifacts, and stored blobs). This action cannot be
              undone.
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
              disabled={
                deleteConfirm.trim().toLowerCase() !== "yes" ||
                bulkDeleteMutation.isPending
              }
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

      <RenameSessionDialog
        session={renameTarget}
        open={renameTarget !== null}
        onOpenChange={(o) => !o && setRenameTarget(null)}
      />
      <DuplicateSessionDialog
        sessionId={duplicateTarget}
        open={duplicateTarget !== null}
        onOpenChange={(o) => !o && setDuplicateTarget(null)}
      />
    </div>
  );
};

export default Sessions;
