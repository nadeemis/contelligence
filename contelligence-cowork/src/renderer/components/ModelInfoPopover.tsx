import { Eye, Brain, Zap, DollarSign, ImageIcon, Cpu, Wrench, Layers } from "lucide-react";
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

function formatPrice(raw?: number, batchSize?: number): string {
  if (!raw || !batchSize) return "—";
  // raw is in 1e-12 units per batchSize tokens
  const perToken = raw / 1e12;
  const perMillion = perToken * 1_000_000;
  if (perMillion < 0.01) return `$${(perMillion * 1000).toFixed(2)}/B`;
  return `$${perMillion.toFixed(2)}/M`;
}

function categoryLabel(category?: string): string {
  if (!category) return "";
  return category.charAt(0).toUpperCase() + category.slice(1);
}

export function ModelInfoCard({ model }: { model: ModelInfo }) {
  const raw = model;
  const supports = (raw?.capabilities?.supports ?? model.capabilities?.supports) as Record<string, any> | undefined;
  const limits = raw?.capabilities?.limits ?? model.capabilities?.limits as Record<string, any> | undefined;
  const billing = raw?.billing;
  const policy = raw?.policy ?? model.policy;
  const reasoningEfforts = raw?.supportedReasoningEfforts ?? model.supportedReasoningEfforts;
  const defaultEffort = raw?.defaultReasoningEffort ?? model.defaultReasoningEffort;
  const family = raw?.capabilities?.family;
  const tokenizer = raw?.capabilities?.tokenizer;
  const modelType = raw?.capabilities?.type;
  const pickerCategory = raw?.modelPickerCategory;
  const priceCategory = raw?.modelPickerPriceCategory;

  return (
    <div className="w-80 rounded-md border bg-popover p-3 text-popover-foreground shadow-md text-xs">
      <div className="space-y-2.5">
        {/* Header */}
        <div>
          <div className="flex items-center justify-between">
            <p className="font-medium text-sm text-foreground">{model.name}</p>
            {pickerCategory && (
              <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                {categoryLabel(pickerCategory)}
              </Badge>
            )}
          </div>
          <p className="text-muted-foreground font-mono">{model.id}</p>
          {family && family !== model.id && (
            <p className="text-muted-foreground">Family: <span className="font-mono">{family}</span></p>
          )}
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
          {supports?.adaptive_thinking && (
            <Badge variant="secondary" className="gap-1 text-[10px] px-1.5 py-0">
              <Brain className="h-2.5 w-2.5" /> Thinking
            </Badge>
          )}
          {supports?.tool_calls && (
            <Badge variant="secondary" className="gap-1 text-[10px] px-1.5 py-0">
              <Wrench className="h-2.5 w-2.5" /> Tools
            </Badge>
          )}
          {supports?.parallel_tool_calls && (
            <Badge variant="secondary" className="gap-1 text-[10px] px-1.5 py-0">
              <Layers className="h-2.5 w-2.5" /> Parallel
            </Badge>
          )}
          {supports?.structured_outputs && (
            <Badge variant="secondary" className="gap-1 text-[10px] px-1.5 py-0">
              <Cpu className="h-2.5 w-2.5" /> Structured
            </Badge>
          )}
          {priceCategory && (
            <Badge variant="secondary" className="gap-1 text-[10px] px-1.5 py-0">
              <DollarSign className="h-2.5 w-2.5" /> {categoryLabel(priceCategory)}
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
            {limits.max_output_tokens && (
              <>
                <span>Max output</span>
                <span className="text-foreground font-mono">{formatTokens(limits.max_output_tokens)}</span>
              </>
            )}
            {limits.max_non_streaming_output_tokens && (
              <>
                <span>Max sync output</span>
                <span className="text-foreground font-mono">{formatTokens(limits.max_non_streaming_output_tokens)}</span>
              </>
            )}
          </div>
        )}

        {/* Thinking budget */}
        {supports?.adaptive_thinking && (supports.min_thinking_budget || supports.max_thinking_budget) && (
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-muted-foreground">
            <span>Thinking budget</span>
            <span className="text-foreground font-mono">
              {formatTokens(supports.min_thinking_budget)}–{formatTokens(supports.max_thinking_budget)}
            </span>
          </div>
        )}

        {/* Vision details */}
        {limits?.vision && (
          <div className="space-y-1">
            <div className="flex items-center gap-1 text-muted-foreground">
              <ImageIcon className="h-3 w-3" /> Vision
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-muted-foreground pl-4">
              <span>Max images</span>
              <span className="text-foreground font-mono">{limits.vision.max_prompt_images ?? "—"}</span>
              <span>Max size</span>
              <span className="text-foreground font-mono">{formatBytes(limits.vision.max_prompt_image_size)}</span>
              <span>Formats</span>
              <span className="text-foreground font-mono">
                {limits.vision.supported_media_types?.map((t) => t.split("/")[1]).join(", ") ?? "—"}
              </span>
            </div>
          </div>
        )}

        {/* Pricing */}
        {billing?.tokenPrices && (
          <div className="space-y-1">
            <div className="flex items-center gap-1 text-muted-foreground">
              <DollarSign className="h-3 w-3" /> Pricing
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-muted-foreground pl-4">
              <span>Input</span>
              <span className="text-foreground font-mono">{formatPrice(billing.tokenPrices.inputPrice, billing.tokenPrices.batchSize)}</span>
              <span>Output</span>
              <span className="text-foreground font-mono">{formatPrice(billing.tokenPrices.outputPrice, billing.tokenPrices.batchSize)}</span>
              {billing.tokenPrices.cachePrice != null && (
                <>
                  <span>Cache</span>
                  <span className="text-foreground font-mono">{formatPrice(billing.tokenPrices.cachePrice, billing.tokenPrices.batchSize)}</span>
                </>
              )}
            </div>
          </div>
        )}

        {/* Reasoning efforts */}
        {reasoningEfforts && reasoningEfforts.length > 0 && (
          <div className="space-y-1">
            <span className="text-muted-foreground flex items-center gap-1">
              <Zap className="h-3 w-3" /> Reasoning efforts
            </span>
            <div className="flex gap-1 pl-4">
              {reasoningEfforts.map((e) => (
                <Badge
                  key={e}
                  variant={e === defaultEffort ? "default" : "outline"}
                  className="text-[10px] px-1.5 py-0"
                >
                  {e}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Footer metadata */}
        {(tokenizer || modelType || policy?.state) && (
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-muted-foreground border-t pt-2">
            {modelType && <span>Type: <span className="text-foreground">{modelType}</span></span>}
            {tokenizer && <span>Tokenizer: <span className="text-foreground font-mono">{tokenizer}</span></span>}
            {policy?.state && <span>Status: <span className="text-foreground">{policy.state}</span></span>}
          </div>
        )}
      </div>
    </div>
  );
}
