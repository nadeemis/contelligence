import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { agentApi } from "@/lib/api";
import type { SessionRecord } from "@/types";

interface RenameSessionDialogProps {
  session: SessionRecord | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RenameSessionDialog({
  session,
  open,
  onOpenChange,
}: RenameSessionDialogProps) {
  const [title, setTitle] = useState("");
  const qc = useQueryClient();

  useEffect(() => {
    if (open && session) {
      setTitle(session.title ?? "");
    }
  }, [open, session]);

  const manualMutation = useMutation({
    mutationFn: () =>
      agentApi.renameSession(session!.id, { auto: false, title: title.trim() }),
    onSuccess: (record) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      qc.invalidateQueries({ queryKey: ["session", session!.id] });
      toast.success(`Session renamed: ${record.title ?? record.id}`);
      onOpenChange(false);
    },
    onError: (err: Error) => {
      toast.error(err.message || "Could not rename session");
    },
  });

  const autoMutation = useMutation({
    mutationFn: () => agentApi.renameSession(session!.id, { auto: true }),
    onSuccess: (record) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      qc.invalidateQueries({ queryKey: ["session", session!.id] });
      toast.success(`Title regenerated: ${record.title ?? record.id}`);
      onOpenChange(false);
    },
    onError: (err: Error) => {
      toast.error(err.message || "Auto-rename failed");
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rename session</DialogTitle>
          <DialogDescription>
            Set a manual title, or regenerate a title automatically from the
            session's content.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-2">
            <Label htmlFor="session-title">Title</Label>
            <Input
              id="session-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Descriptive title"
              maxLength={120}
              onKeyDown={(e) => {
                if (e.key === "Enter" && title.trim()) {
                  manualMutation.mutate();
                }
              }}
            />
          </div>
          {session?.title_source === "manual" && (
            <p className="text-xs text-muted-foreground">
              Current title was set manually.
            </p>
          )}
        </div>
        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={manualMutation.isPending || autoMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="outline"
            onClick={() => autoMutation.mutate()}
            disabled={!session || autoMutation.isPending || manualMutation.isPending}
          >
            {autoMutation.isPending ? "Regenerating…" : "Auto-rename"}
          </Button>
          <Button
            onClick={() => manualMutation.mutate()}
            disabled={
              !session ||
              !title.trim() ||
              manualMutation.isPending ||
              autoMutation.isPending
            }
          >
            {manualMutation.isPending ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
