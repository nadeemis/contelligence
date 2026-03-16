import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { ChevronDown, Bot } from "lucide-react";

interface ToolCallCardProps {
  toolName: string;
  arguments: Record<string, unknown>;
  callId: string;
}

export function ToolCallCard({ toolName, arguments: args, callId }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="flex gap-3">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
        <Bot className="h-3.5 w-3.5 text-primary" />
      </div>
      <div className="rounded-lg border border-border bg-card p-3 max-w-[80%] w-full">
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center gap-2"
        >
          <Badge className="bg-primary/10 text-primary text-xs border-0">tool_call</Badge>
          <span className="text-sm font-mono text-foreground">{toolName}</span>
          <span className="text-xs text-muted-foreground">({callId.slice(0, 8)})</span>
          <ChevronDown
            className={`w-4 h-4 ml-auto text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`}
          />
        </button>

        {expanded && (
          <pre className="mt-2 p-3 text-xs bg-background/50 rounded font-mono overflow-x-auto text-foreground">
            {JSON.stringify(args, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
