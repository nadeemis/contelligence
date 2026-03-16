import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Plus, Search, MoreHorizontal, BookOpen } from "lucide-react";
import { toast } from "sonner";
import { skillsApi } from "@/lib/api";
import type { SkillSummary, SkillStatusType } from "@/types";

const statusConfig: Record<
  SkillStatusType,
  { label: string; className: string }
> = {
  active: {
    label: "ACTIVE ●",
    className: "bg-primary/15 text-primary border-primary/30",
  },
  draft: {
    label: "DRAFT ○",
    className: "bg-muted text-muted-foreground border-border",
  },
  disabled: {
    label: "DISABLED",
    className: "bg-destructive/15 text-destructive border-destructive/30",
  },
};

export default function Skills() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [deleteTarget, setDeleteTarget] = useState<SkillSummary | null>(null);

  // Fetch all skills
  const {
    data: skills = [],
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: [
      "skills",
      statusFilter !== "all" ? statusFilter : undefined,
    ],
    queryFn: () =>
      skillsApi.list(
        statusFilter !== "all" ? { status: statusFilter } : undefined,
      ),
  });

  // Status update mutation
  const updateStatusMutation = useMutation({
    mutationFn: ({
      id,
      status,
    }: {
      id: string;
      status: SkillStatusType;
    }) => skillsApi.update(id, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["skills"] });
      toast.success("Skill status updated");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => skillsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["skills"] });
      toast.success("Skill deleted");
      setDeleteTarget(null);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Client-side search + category filtering
  const filtered = skills.filter((s) => {
    if (
      categoryFilter !== "all" &&
      !(s.tags ?? []).includes(categoryFilter)
    )
      return false;
    if (
      search &&
      !s.name.toLowerCase().includes(search.toLowerCase()) &&
      !s.description.toLowerCase().includes(search.toLowerCase())
    )
      return false;
    return true;
  });

  // Derive unique tags for category filter
  const allTags = Array.from(
    new Set(skills.flatMap((s) => s.tags ?? [])),
  ).sort();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-9 w-28" />
        </div>
        <Skeleton className="h-12 w-full" />
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-28 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="text-center py-16 text-sm text-destructive">
        Failed to load skills: {(error as Error)?.message ?? "Unknown error"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold font-display tracking-wide text-foreground">
          Skills Library
        </h1>
        <Button onClick={() => navigate("/skills/new")}>
          <Plus className="h-4 w-4 mr-2" />
          New Skill
        </Button>
      </div>

      <Card>
        <CardContent className="p-4 flex flex-wrap items-center gap-3">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="All" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="built-in">Built-in</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="draft">Draft</SelectItem>
              <SelectItem value="disabled">Disabled</SelectItem>
            </SelectContent>
          </Select>
          <Select value={categoryFilter} onValueChange={setCategoryFilter}>
            <SelectTrigger className="w-[170px]">
              <SelectValue placeholder="All Categories" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Categories</SelectItem>
              {allTags.map((tag) => (
                <SelectItem key={tag} value={tag}>
                  {tag.charAt(0).toUpperCase() + tag.slice(1)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search skills..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
        </CardContent>
      </Card>

      {filtered.length === 0 && (
        <div className="text-center py-16 text-sm text-muted-foreground">
          <BookOpen className="h-10 w-10 mx-auto mb-3 opacity-30" />
          {skills.length === 0
            ? "No skills yet. Create your first skill."
            : "No skills match your filters."}
        </div>
      )}

      <div className="space-y-3">
        {filtered.map((skill) => {
          const sc =
            statusConfig[skill.status as SkillStatusType] ??
            statusConfig.draft;
          const isCustom = skill.source === "user-created";

          return (
            <Card
              key={skill.id}
              className="hover:border-primary/30 transition-colors"
            >
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3 min-w-0">
                    <div className="mt-0.5 text-primary shrink-0">
                      <BookOpen className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-sm text-foreground font-medium">
                          {skill.name}
                        </span>
                        <Badge
                          variant="outline"
                          className={sc.className}
                        >
                          {sc.label}
                        </Badge>
                        {isCustom && (
                          <Badge
                            variant="secondary"
                            className="text-[10px]"
                          >
                            CUSTOM
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {skill.description}
                      </p>
                      <div className="flex items-center gap-4 text-xs text-muted-foreground pt-1 flex-wrap">
                        {skill.tags && skill.tags.length > 0 && (
                          <span>Tags: {skill.tags.join(", ")}</span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => navigate(`/skills/${skill.id}`)}
                    >
                      {isCustom ? "Edit" : "View"}
                    </Button>
                    {skill.status === "draft" && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          updateStatusMutation.mutate({
                            id: skill.id,
                            status: "active",
                          })
                        }
                      >
                        Activate
                      </Button>
                    )}
                    {skill.status === "active" && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          updateStatusMutation.mutate({
                            id: skill.id,
                            status: "disabled",
                          })
                        }
                      >
                        Disable
                      </Button>
                    )}
                    {skill.status === "disabled" && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          updateStatusMutation.mutate({
                            id: skill.id,
                            status: "active",
                          })
                        }
                      >
                        Enable
                      </Button>
                    )}
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
                            onClick={() =>
                              navigate(`/skills/${skill.id}`)
                            }
                          >
                            Edit
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() => setDeleteTarget(skill)}
                          >
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

      {/* Delete confirmation */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={() => setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Skill</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete{" "}
              <strong>{deleteTarget?.name}</strong>? This action cannot be
              undone.
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
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}