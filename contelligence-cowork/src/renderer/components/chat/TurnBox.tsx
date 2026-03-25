import React, { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { ChevronRight } from "lucide-react";
import { UsageInfoBar } from "./UsageInfoBar";
import type { ProcessedTurn } from "@/types/agent-events";

interface TurnBoxProps {
  turn: ProcessedTurn;
  children: React.ReactNode;
}

export function TurnBox({ turn, children }: TurnBoxProps) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="space-y-0">
      {/* Usage info above the turn box */}
      <UsageInfoBar usageEvents={turn.usageEvents} />

      {/* Turn bounding box */}
      <div className="rounded-lg border border-border/60 bg-card/20 overflow-hidden">
        {/* Clickable turn header */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-muted/30 transition-colors"
        >
          <ChevronRight
            className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${
              expanded ? "rotate-90" : ""
            }`}
          />
          <Badge
            variant="outline"
            className="text-xs font-mono border-primary/40 text-primary bg-primary/5"
          >
            Turn {turn.turnId}
          </Badge>
          {turn.interactionId && (
            <span className="text-[10px] text-muted-foreground font-mono truncate max-w-[220px]">
              {turn.interactionId}
            </span>
          )}
        </button>

        {/* Collapsible turn content */}
        {expanded && <div className="px-4 pb-4 space-y-3">{children}</div>}
      </div>
    </div>
  );
}
