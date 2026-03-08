import { CheckCircle, XCircle, Bot } from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface ToolResultCardProps {
  callId: string;
  toolName: string;
  result: unknown;
  parameters: Record<string, unknown>;
  timestamp: string;
  startedAt: string;
  completedAt: string;
  durationMs: number;
}

export function ToolResultCard({ callId, toolName, result, parameters, timestamp, startedAt, completedAt, durationMs }: ToolResultCardProps) {
  const resultStr = typeof result === "string" ? result : JSON.stringify(result, null, 2);
  const isError = typeof result === "object" && result !== null && "error" in result;

  return (
    <div className="flex gap-3">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
        <Bot className="h-3.5 w-3.5 text-primary" />
      </div>
      <div className="rounded-lg border border-border bg-card p-3 max-w-[80%] w-full">
        <div className="flex items-center gap-2 mb-2">
          <Badge className="bg-success/10 text-success text-xs border-0">tool_result</Badge>
          <span className="text-sm font-mono text-foreground">{toolName}</span>
          <span className="text-xs text-muted-foreground ml-2">({timestamp})</span>
          <span className="ml-auto flex items-center gap-1.5 shrink-0">
            {isError ? (
              <XCircle className="h-3 w-3 text-destructive" />
            ) : (
              <CheckCircle className="h-3 w-3 text-success" />
            )}
            <span className="text-xs text-muted-foreground">{durationMs}ms</span>
          </span>
        </div>
        <div className="rounded bg-background/50 p-3 font-mono text-xs space-y-2">
          {parameters && (
            <div>
              <span className="text-muted-foreground">parameters:</span>
              <pre className="text-foreground mt-1 whitespace-pre-wrap break-all">
                {JSON.stringify(parameters, null, 2)}
              </pre>
            </div>
          )}
          {result && (
            <div>
              <span className="text-muted-foreground">result:</span>
              <pre className="text-foreground mt-1 whitespace-pre-wrap break-all">
                {resultStr.length > 200 ? resultStr.slice(0, 200) + "..." : resultStr}
              </pre>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
