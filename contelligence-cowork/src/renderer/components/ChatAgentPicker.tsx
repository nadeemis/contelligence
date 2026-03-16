import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Bot, ChevronDown, ChevronUp } from "lucide-react";
import { agentsApi } from "@/lib/api";
import type { AgentSummary } from "@/types";

interface ChatAgentPickerProps {
  selected: string[];
  onSelectionChange: (ids: string[]) => void;
}

export function ChatAgentPicker({
  selected,
  onSelectionChange,
}: ChatAgentPickerProps) {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);

  const { data: agents = [], isLoading } = useQuery({
    queryKey: ["agents-picker"],
    queryFn: () => agentsApi.list(),
  });

  const toggle = (id: string) => {
    onSelectionChange(
      selected.includes(id)
        ? selected.filter((x) => x !== id)
        : [...selected, id],
    );
  };

  const builtIn = agents.filter((a: AgentSummary) => a.source === "built-in");
  const custom = agents.filter((a: AgentSummary) => a.source === "user-created" && a.status === "active");

  return (
    <div className="rounded-lg border border-border bg-card">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-secondary/50 transition-colors rounded-t-lg"
      >
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium text-foreground">Agents</span>
          <Badge variant="secondary" className="text-xs">
            {selected.length} selected
          </Badge>
        </div>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-4 pt-2 border-t border-border space-y-4">
          {isLoading ? (
            <div className="flex gap-2">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-16 w-36" />
              ))}
            </div>
          ) : (
            <>
              {/* Built-in */}
              {builtIn.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                    Built-in:
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {builtIn.map((agent: AgentSummary) => (
                      <AgentCard
                        key={agent.id}
                        agent={agent}
                        checked={selected.includes(agent.id)}
                        onToggle={() => toggle(agent.id)}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Custom */}
              {custom.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                    Custom:
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {custom.map((agent: AgentSummary) => (
                      <AgentCard
                        key={agent.id}
                        agent={agent}
                        checked={selected.includes(agent.id)}
                        onToggle={() => toggle(agent.id)}
                      />
                    ))}
                  </div>
                </div>
              )}

              {agents.length === 0 && (
                <p className="text-sm text-muted-foreground py-2">
                  No agents available.
                </p>
              )}
            </>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1">
            <Button
              variant="ghost"
              size="sm"
              className="text-xs h-7"
              onClick={() =>
                onSelectionChange([...builtIn, ...custom].map((a) => a.id))
              }
            >
              Select All
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-xs h-7"
              onClick={() => onSelectionChange([])}
            >
              Clear
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-xs h-7 ml-auto"
              onClick={() => navigate("/agents")}
            >
              Manage Agents &rarr;
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function AgentCard({
  agent,
  checked,
  onToggle,
}: {
  agent: AgentSummary;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label
      className={`flex items-start gap-2 rounded-lg border p-3 cursor-pointer transition-colors min-w-[140px] max-w-[160px] ${
        checked
          ? "border-primary/50 bg-primary/5"
          : "border-border bg-muted/30 hover:border-muted-foreground/30"
      }`}
    >
      <Checkbox
        checked={checked}
        onCheckedChange={onToggle}
        className="mt-0.5"
      />
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 mb-0.5">
          <Bot className="h-3.5 w-3.5 text-primary" />
        </div>
        <p className="text-xs font-mono font-medium text-foreground truncate">
          {agent.display_name}
        </p>
        <p className="text-[10px] text-muted-foreground leading-tight">
          {agent.description?.slice(0, 50) || agent.id}
        </p>
      </div>
    </label>
  );
}