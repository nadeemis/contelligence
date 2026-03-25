import { Brain, Bot, Users, AlertTriangle, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type {
  AgentEventUnion,
  SubagentStartedEvent,
  SubagentCompletedEvent,
} from "@/types/agent-events";
import { ApprovalCard } from "./ApprovalCard";
import { MarkdownContent } from "@/components/MarkdownContent";

interface ChatMessageProps {
  event: AgentEventUnion;
  onApprove: (msg: string) => void;
}

export function ChatMessage({ event, onApprove }: ChatMessageProps) {
  switch (event.type) {
    case "thinking":
      return (
        <div className="flex gap-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted">
            <Brain className="h-3.5 w-3.5 text-muted-foreground" />
          </div>
          <div className="rounded-lg border border-border/50 bg-muted/50 p-3 max-w-[80%]">
            <MarkdownContent className="max-w-none italic text-muted-foreground">
              {event.content}
            </MarkdownContent>
          </div>
        </div>
      );

    case "message":
      // Skip empty messages (the backend sends {"content": ""} as a placeholder)
      if (!event.content) return null;
      return (
        <div className="flex gap-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
            <Bot className="h-3.5 w-3.5 text-primary" />
          </div>
          <div className="rounded-lg bg-secondary p-3 max-w-[80%]">
            <MarkdownContent>{event.content}</MarkdownContent>
          </div>
        </div>
      );

    case "subagent_started": {
      const e = event as SubagentStartedEvent;
      return (
        <div className="flex gap-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/10">
            <Users className="h-3.5 w-3.5 text-accent" />
          </div>
          <div className="rounded-lg border border-accent/30 bg-accent/5 p-3 max-w-[80%]">
            <div className="flex items-center gap-2 mb-1">
              <Badge className="bg-accent/10 text-accent text-xs border-0">subagent_started</Badge>
              <span className="text-sm font-mono text-foreground">{e.agent_name}</span>
            </div>
            <pre className="text-xs font-mono overflow-x-auto whitespace-pre-wrap text-foreground/70">
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          </div>
        </div>
      );
    }

    case "subagent_completed": {
      const e = event as SubagentCompletedEvent;
      return (
        <div className="flex gap-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/10">
            <Users className="h-3.5 w-3.5 text-accent" />
          </div>
          <div className="rounded-lg border border-accent/30 bg-accent/5 p-3 max-w-[80%]">
            <div className="flex items-center gap-2 mb-1">
              <Badge className="bg-accent/10 text-accent text-xs border-0">subagent_completed</Badge>
              <span className="text-sm font-mono text-foreground">{e.agent_name}</span>
            </div>
            <pre className="text-xs font-mono overflow-x-auto whitespace-pre-wrap text-foreground/70">
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          </div>
        </div>
      );
    }

    case "approval_required":
      return (
        <ApprovalCard
          toolName={event.tool_name}
          arguments={event.arguments}
          reason={event.reason}
          onApprove={() => onApprove("approve")}
          onDeny={() => onApprove("deny")}
          onApproveAll={() => onApprove("approve_all")}
        />
      );

    case "error":
      return (
        <div className="flex gap-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-destructive/10">
            <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
          </div>
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 max-w-[80%]">
            <span className="text-destructive font-medium text-sm">Error:</span>{" "}
            <span className="text-sm text-foreground">{event.message}</span>
            <pre className="mt-2 text-xs font-mono overflow-x-auto whitespace-pre-wrap text-foreground/60">
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          </div>
        </div>
      );

    case "done":
      return (
        <div className="flex gap-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-success/10">
            <Bot className="h-3.5 w-3.5 text-success" />
          </div>
          <div className="rounded-lg border border-success/30 bg-success/5 p-3 max-w-[80%]">
            <span className="text-success font-medium text-sm">Session complete.</span>
            {event.summary && <p className="text-sm text-muted-foreground mt-1">{event.summary}</p>}
          </div>
        </div>
      );

    // Metadata events — not user-facing, hide from chat
    case "usage_info":
    case "assistant_usage":
    case "turn_start":
    case "turn_end":
      return null;

    // Tool lifecycle events rendered as orphans (normally grouped inside TurnBox)
    case "tool_call_start":
    case "tool_call_complete":
    case "tool_execution_start":
    case "tool_execution_complete":
      return (
        <div className="flex gap-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
            <Wrench className="h-3.5 w-3.5 text-primary" />
          </div>
          <div className="rounded-lg border border-border bg-card p-2 max-w-[80%] flex items-center gap-2">
            <Badge variant="outline" className="text-[10px]">{event.type.replace(/_/g, " ")}</Badge>
            {"tool_name" in event && (
              <span className="text-xs font-mono text-muted-foreground">{(event as { tool_name: string }).tool_name}</span>
            )}
          </div>
        </div>
      );

    // Fallback: render any unhandled event with its full payload
    default:
      return (
        <div className="flex gap-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted">
            <Bot className="h-3.5 w-3.5 text-muted-foreground" />
          </div>
          <div className="rounded-lg border border-border/50 bg-muted/30 p-3 max-w-[80%]">
            <Badge variant="outline" className="text-[10px] mb-1">{event.type}</Badge>
            <pre className="text-xs font-mono overflow-x-auto whitespace-pre-wrap text-foreground/70">
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          </div>
        </div>
      );
  }
}
