import { useState } from "react";
import { CheckCircle, XCircle, Bot, Eye, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { agentApi } from "@/lib/api";

interface ToolResultCardProps {
  callId: string;
  toolName: string;
  result: unknown;
  parameters: Record<string, unknown>;
  timestamp: string;
  startedAt: string | null;
  completedAt: string | null;
  durationMs: number;
  sessionId?: string;
  sequence?: number;
}

export function ToolResultCard({ callId, toolName, result, parameters, timestamp, startedAt, completedAt, durationMs, sessionId, sequence }: ToolResultCardProps) {
  const [fullResult, setFullResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const isTruncated = typeof result === "object" && result !== null && "_truncated" in result;
  const displayResult = fullResult ?? result;
  const resultStr = typeof displayResult === "string" ? displayResult : JSON.stringify(displayResult, null, 2);
  const isError = typeof displayResult === "object" && displayResult !== null && "error" in displayResult;

  const handleViewFull = async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const turns = await agentApi.getSessionLogs(sessionId, { include_tool_results: true });
      const match = turns.find((t) => t.sequence === sequence && t.role === "tool");
      if (match?.tool_call?.result) {
        setFullResult(match.tool_call.result);
      }
    } finally {
      setLoading(false);
    }
  };

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
          {displayResult && (!isTruncated || fullResult) && (
            <div>
              <span className="text-muted-foreground">result:</span>
              <pre className="text-foreground mt-1 whitespace-pre-wrap break-all">
                {resultStr.length > 200 && !fullResult ? resultStr.slice(0, 200) + "..." : resultStr}
              </pre>
            </div>
          )}
          {isTruncated && !fullResult && (
            <div>
              <span className="text-muted-foreground">result:</span>
              <button
                onClick={handleViewFull}
                disabled={loading || !sessionId}
                className="ml-2 inline-flex items-center gap-1 text-xs text-primary hover:text-primary/80 disabled:opacity-50"
              >
                {loading ? (
                  <><Loader2 className="h-3 w-3 animate-spin" /> Loading…</>
                ) : (
                  <><Eye className="h-3 w-3" /> View full result</>
                )}
              </button>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
