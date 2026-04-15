import { Eye, Brain, Zap, DollarSign, ImageIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { ModelInfo } from "@/types";

function formatTokens(n?: number): string {
  if (!n) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  return `${(n / 1_000).toFixed(0)}K`;
}

function formatBytes(n?: number): string {
  if (!n) return "—";
  if (n >= 1_048_576) return `${(n / 1_048_576).toFixed(0)} MB`;
  return `${(n / 1_024).toFixed(0)} KB`;
}

function billingLabel(multiplier?: number): string {
  if (multiplier === undefined || multiplier === null) return "—";
  if (multiplier === 0) return "Free";
  return `${multiplier}×`;
}

export function ModelInfoCard({ model }: { model: ModelInfo }) {
  const caps = model.capabilities;
  const supports = caps?.supports;
  const limits = caps?.limits;

  return (
    <div className="w-72 rounded-md border bg-popover p-3 text-popover-foreground shadow-md text-xs">
      <div className="space-y-2.5">
        {/* Header */}
        <div>
          <p className="font-medium text-sm text-foreground">{model.name}</p>
          <p className="text-muted-foreground font-mono">{model.id}</p>
        </div>

        {/* Capabilities badges */}
        <div className="flex flex-wrap gap-1.5">
          {supports?.vision && (
            <Badge variant="secondary" className="gap-1 text-[10px] px-1.5 py-0">
              <Eye className="h-2.5 w-2.5" /> Vision
            </Badge>
          )}
          {supports?.reasoningEffort && (
            <Badge variant="secondary" className="gap-1 text-[10px] px-1.5 py-0">
              <Brain className="h-2.5 w-2.5" /> Reasoning
            </Badge>
          )}
          {model.billing && (
            <Badge variant="secondary" className="gap-1 text-[10px] px-1.5 py-0">
              <DollarSign className="h-2.5 w-2.5" /> {billingLabel(model.billing.multiplier)}
            </Badge>
          )}
        </div>

        {/* Token limits */}
        {limits && (
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-muted-foreground">
            <span>Context window</span>
            <span className="text-foreground font-mono">{formatTokens(limits.max_context_window_tokens)}</span>
            <span>Max prompt</span>
            <span className="text-foreground font-mono">{formatTokens(limits.max_prompt_tokens)}</span>
          </div>
        )}

        {/* Vision details */}
        {limits?.vision && (
          <div className="space-y-1">
            <div className="flex items-center gap-1 text-muted-foreground">
              <ImageIcon className="h-3 w-3" /> Vision details
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-muted-foreground pl-4">
              <span>Max images</span>
              <span className="text-foreground font-mono">{limits.vision.max_prompt_images ?? "—"}</span>
              <span>Max image size</span>
              <span className="text-foreground font-mono">{formatBytes(limits.vision.max_prompt_image_size)}</span>
              <span>Formats</span>
              <span className="text-foreground font-mono">
                {limits.vision.supported_media_types?.map((t) => t.split("/")[1]).join(", ") ?? "—"}
              </span>
            </div>
          </div>
        )}

        {/* Reasoning efforts */}
        {model.supportedReasoningEfforts && model.supportedReasoningEfforts.length > 0 && (
          <div className="space-y-1">
            <span className="text-muted-foreground flex items-center gap-1">
              <Zap className="h-3 w-3" /> Reasoning efforts
            </span>
            <div className="flex gap-1 pl-4">
              {model.supportedReasoningEfforts.map((e) => (
                <Badge
                  key={e}
                  variant={e === model.defaultReasoningEffort ? "default" : "outline"}
                  className="text-[10px] px-1.5 py-0"
                >
                  {e}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
