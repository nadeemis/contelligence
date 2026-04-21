import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
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
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { agentApi } from "@/lib/api";

interface DuplicateSessionDialogProps {
  sessionId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DuplicateSessionDialog({
  sessionId,
  open,
  onOpenChange,
}: DuplicateSessionDialogProps) {
  const [includeTurns, setIncludeTurns] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const qc = useQueryClient();
  const navigate = useNavigate();

  const mutation = useMutation({
    mutationFn: () =>
      agentApi.duplicateSession(sessionId!, {
        include_turns: includeTurns,
        new_title: newTitle.trim() || undefined,
      }),
    onSuccess: (record) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      toast.success(`Session duplicated: ${record.title ?? record.id}`);
      onOpenChange(false);
      setNewTitle("");
      setIncludeTurns(false);
      navigate(`/sessions/${record.id}`);
    },
    onError: (err: Error) => {
      toast.error(err.message || "Could not duplicate session");
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Duplicate session</DialogTitle>
          <DialogDescription>
            Create a copy of this session's instruction, model, skills, and agents.
            The copy starts in completed state — run it from the detail page when ready.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="new-title">New title (optional)</Label>
            <Input
              id="new-title"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Leave empty to use '<original> (copy)'"
            />
          </div>
          <div className="flex items-center gap-2">
            <Checkbox
              id="include-turns"
              checked={includeTurns}
              onCheckedChange={(v) => setIncludeTurns(v === true)}
            />
            <Label htmlFor="include-turns" className="font-normal cursor-pointer">
              Include full conversation history
            </Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!sessionId || mutation.isPending}
          >
            {mutation.isPending ? "Duplicating…" : "Duplicate"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
