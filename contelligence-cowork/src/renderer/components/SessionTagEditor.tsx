import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X, Plus } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { agentApi } from "@/lib/api";

interface SessionTagEditorProps {
  sessionId: string;
  tags: string[];
  editable?: boolean;
  compact?: boolean;
  onChange?: (tags: string[]) => void;
}

const TAG_RE = /^[a-z0-9][a-z0-9\-_]*$/;

export function SessionTagEditor({
  sessionId,
  tags,
  editable = true,
  compact = false,
  onChange,
}: SessionTagEditorProps) {
  const [draft, setDraft] = useState("");
  const qc = useQueryClient();

  const { data: allTags } = useQuery({
    queryKey: ["session-tags"],
    queryFn: () => agentApi.getSessionTags(),
    enabled: editable,
    staleTime: 30_000,
  });

  const setTags = useMutation({
    mutationFn: (next: string[]) => agentApi.setSessionTags(sessionId, next),
    onSuccess: (record) => {
      onChange?.(record.tags ?? []);
      qc.invalidateQueries({ queryKey: ["sessions"] });
      qc.invalidateQueries({ queryKey: ["session", sessionId] });
      qc.invalidateQueries({ queryKey: ["session-tags"] });
    },
    onError: (err: Error) => {
      toast.error(err.message || "Could not update tags");
    },
  });

  const handleAdd = (raw: string) => {
    const normalised = raw.trim().toLowerCase();
    if (!normalised) return;
    if (!TAG_RE.test(normalised)) {
      toast.error(
        "Invalid tag: use lowercase letters, digits, hyphens, or underscores.",
      );
      return;
    }
    if (tags.includes(normalised)) {
      setDraft("");
      return;
    }
    setTags.mutate([...tags, normalised]);
    setDraft("");
  };

  const handleRemove = (tag: string) => {
    setTags.mutate(tags.filter((t) => t !== tag));
  };

  const suggestions = useMemo(() => {
    if (!allTags) return [] as string[];
    return allTags
      .map((t) => t.tag)
      .filter((t) => !tags.includes(t) && t.startsWith(draft.toLowerCase()))
      .slice(0, 6);
  }, [allTags, tags, draft]);

  return (
    <div className="flex flex-wrap items-center gap-1">
      {tags.map((t) => (
        <Badge
          key={t}
          variant="outline"
          className={`text-xs gap-1 ${compact ? "py-0 px-1.5" : ""}`}
        >
          {t}
          {editable && (
            <button
              type="button"
              aria-label={`Remove tag ${t}`}
              onClick={(e) => {
                e.stopPropagation();
                handleRemove(t);
              }}
              className="hover:text-destructive"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </Badge>
      ))}
      {editable && (
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-1.5 text-xs gap-1"
              onClick={(e) => e.stopPropagation()}
            >
              <Plus className="h-3 w-3" />
              {!compact && "tag"}
            </Button>
          </PopoverTrigger>
          <PopoverContent
            align="start"
            className="w-60 p-2"
            onClick={(e) => e.stopPropagation()}
          >
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="new-tag"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleAdd(draft);
                }
              }}
              className="mb-2"
            />
            {suggestions.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {suggestions.map((s) => (
                  <Badge
                    key={s}
                    variant="secondary"
                    className="text-xs cursor-pointer hover:bg-accent"
                    onClick={() => handleAdd(s)}
                  >
                    {s}
                  </Badge>
                ))}
              </div>
            )}
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}
