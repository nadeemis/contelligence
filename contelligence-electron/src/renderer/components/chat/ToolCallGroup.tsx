import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Wrench, ArrowRight, CheckCircle, XCircle, ChevronRight, ChevronDown } from "lucide-react";
import type { AgentEventUnion, ToolGroup } from "@/types/agent-events";

interface ToolCallGroupProps {
  group: ToolGroup;
}

const PREVIEW_LINES = 3;

/** Badge color per tool event type */
function eventBadgeStyle(type: string): string {
  switch (type) {
    case "tool_execution_start":
      return "bg-amber-600/10 text-amber-400 border-0";
    case "tool_call_start":
      return "bg-amber-500/10 text-amber-400 border-0";
    case "tool_call_complete":
      return "bg-emerald-500/10 text-emerald-400 border-0";
    case "tool_execution_complete":
      return "bg-green-500/10 text-green-400 border-0";
    default:
      return "bg-muted text-muted-foreground border-0";
  }
}

/** Icon indicating direction of the lifecycle step */
function eventIcon(type: string) {
  switch (type) {
    case "tool_execution_start":
    case "tool_call_start":
      return <ArrowRight className="h-3 w-3" />;
    case "tool_call_complete":
    case "tool_execution_complete":
      return <CheckCircle className="h-3 w-3" />;
    default:
      return null;
  }
}

/** Collapsible JSON payload – shows first N lines with an expand toggle. */
function CollapsiblePayload({ data }: { data: Record<string, unknown> }) {
  const [expanded, setExpanded] = useState(false);
  const full = JSON.stringify(data, null, 2);
  const lines = full.split("\n");
  const needsTruncation = lines.length > PREVIEW_LINES;
  const preview = lines.slice(0, PREVIEW_LINES).join("\n");

  return (
    <div>
      <pre className="text-xs font-mono overflow-x-auto whitespace-pre-wrap text-foreground/80">
        {expanded || !needsTruncation ? full : preview}
      </pre>
      {needsTruncation && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-1 flex items-center gap-1 text-[10px] text-primary hover:underline"
        >
          {expanded ? (
            <><ChevronDown className="h-3 w-3" /> Collapse</>
          ) : (
            <><ChevronRight className="h-3 w-3" /> Show all {lines.length} lines</>
          )}
        </button>
      )}
    </div>
  );
}

export function ToolCallGroup({ group }: ToolCallGroupProps) {
  const [expanded, setExpanded] = useState(false);

  const hasError = group.events.some(
    (e) => e.type === "tool_execution_complete" && e.payload?.result && typeof e.payload.result === "object" && "error" in (e.payload.result as Record<string, unknown>)
  );

  return (
    <div className="flex gap-3">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
        <Wrench className="h-3.5 w-3.5 text-primary" />
      </div>
      <div className={`rounded-lg border ${hasError ? "border-destructive/40" : "border-border"} bg-card max-w-full w-full overflow-hidden`}>
        {/* Clickable header */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center gap-2 flex-wrap px-3 py-2 hover:bg-muted/30 transition-colors"
        >
          <ChevronRight
            className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${
              expanded ? "rotate-90" : ""
            }`}
          />
          <Badge className="bg-primary/10 text-primary text-xs border-0">Tool Call</Badge>
          <span className="text-sm font-mono font-medium text-foreground">{group.toolName}</span>
          <span className="text-xs text-muted-foreground font-mono">({group.toolCallId.slice(0, 16)}…)</span>
          <span className="text-[10px] text-muted-foreground ml-auto">{group.events.length} events</span>
          {hasError && <XCircle className="h-3.5 w-3.5 text-destructive" />}
        </button>

        {/* Collapsible stacked sub-events */}
        {expanded && (
          <div className="px-3 pb-3 space-y-2">
            {group.events.map((event: AgentEventUnion, idx: number) => (
              <div
                key={idx}
                className="rounded border border-border/40 bg-background/50 p-2 space-y-1"
              >
                <div className="flex items-center gap-2">
                  {eventIcon(event.type)}
                  <Badge className={`text-[10px] px-1.5 py-0 ${eventBadgeStyle(event.type)}`}>
                    {event.type}
                  </Badge>
                </div>
                <CollapsiblePayload data={event.payload} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
