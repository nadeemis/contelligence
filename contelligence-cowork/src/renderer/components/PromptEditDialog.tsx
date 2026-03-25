import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { RotateCcw, Save, Loader2 } from "lucide-react";
import type { PromptResponse } from "@/types";

interface PromptEditDialogProps {
  prompt: PromptResponse | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (id: string, content: string) => Promise<void>;
  onReset: (id: string) => Promise<void>;
  isSaving: boolean;
}

export function PromptEditDialog({
  prompt,
  open,
  onOpenChange,
  onSave,
  onReset,
  isSaving,
}: PromptEditDialogProps) {
  const [content, setContent] = useState("");
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (prompt) {
      setContent(prompt.content);
      setDirty(false);
    }
  }, [prompt]);

  const handleContentChange = (value: string) => {
    setContent(value);
    setDirty(value !== prompt?.content);
  };

  const handleSave = async () => {
    if (!prompt) return;
    await onSave(prompt.id, content);
    setDirty(false);
  };

  const handleReset = async () => {
    if (!prompt) return;
    await onReset(prompt.id);
  };

  if (!prompt) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col gap-0 p-0">
        <DialogHeader className="px-6 pt-6 pb-4 border-b border-border space-y-2">
          <div className="flex items-center justify-between">
            <DialogTitle className="text-foreground">{prompt.name}</DialogTitle>
            <div className="flex items-center gap-2">
              {prompt.is_default ? (
                <Badge variant="secondary" className="text-xs">Default</Badge>
              ) : (
                <Badge className="text-xs bg-primary/15 text-primary border-primary/30">Customised</Badge>
              )}
              <Badge variant="outline" className="text-xs">v{prompt.version}</Badge>
            </div>
          </div>
          <DialogDescription>
            {prompt.prompt_type === "system"
              ? "The main system prompt governing the agent's behaviour across every conversation."
              : `System prompt for the ${prompt.name} agent.`
            }
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 min-h-0 px-6 py-4 overflow-hidden">
          <Textarea
            value={content}
            onChange={(e) => handleContentChange(e.target.value)}
            className="h-full min-h-[400px] max-h-[55vh] resize-none font-mono text-xs leading-relaxed bg-secondary/30"
            spellCheck={false}
          />
        </div>

        <DialogFooter className="px-6 pb-6 pt-4 border-t border-border flex-row justify-between sm:justify-between">
          <Button
            variant="outline"
            size="sm"
            onClick={handleReset}
            disabled={isSaving || prompt.is_default}
            className="gap-1.5"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Reset to Default
          </Button>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={!dirty || isSaving}
              className="gap-1.5"
            >
              {isSaving ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5" />
              )}
              Save
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
