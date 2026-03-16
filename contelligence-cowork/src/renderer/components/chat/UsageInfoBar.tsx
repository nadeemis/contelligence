import { Gauge, Cpu, Coins, Clock, Layers } from "lucide-react";
import type { UsageInfoEvent, AssistantUsageEvent } from "@/types/agent-events";

interface UsageInfoBarProps {
  usageEvents: (UsageInfoEvent | AssistantUsageEvent)[];
}

export function UsageInfoBar({ usageEvents }: UsageInfoBarProps) {
  if (usageEvents.length === 0) return null;

  return (
    <div className="mb-2 space-y-1.5 px-1">
      {usageEvents.map((evt, i) => {
        if (evt.type === "usage_info") {
          const e = evt as UsageInfoEvent;
          const pct = e.token_limit > 0 ? ((e.current_tokens / e.token_limit) * 100).toFixed(1) : "–";
          return (
            <div key={`usage-${i}`} className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <Gauge className="h-3 w-3" />
                Tokens: {e.current_tokens.toLocaleString()} / {e.token_limit.toLocaleString()} ({pct}%)
              </span>
              <span className="flex items-center gap-1">
                <Layers className="h-3 w-3" />
                Messages: {e.messages_length}
              </span>
            </div>
          );
        }

        if (evt.type === "assistant_usage") {
          const e = evt as AssistantUsageEvent;
          return (
            <div key={`assist-${i}`} className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <Cpu className="h-3 w-3" />
                {e.model}
              </span>
              <span>In: {e.input_tokens.toLocaleString()}</span>
              <span>Out: {e.output_tokens.toLocaleString()}</span>
              <span>Cache R: {e.cache_read_tokens.toLocaleString()} W: {e.cache_write_tokens.toLocaleString()}</span>
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {e.duration.toLocaleString()}ms
              </span>
              <span className="flex items-center gap-1">
                <Coins className="h-3 w-3" />
                ${e.cost.toFixed(4)}
              </span>
            </div>
          );
        }

        return null;
      })}
    </div>
  );
}
