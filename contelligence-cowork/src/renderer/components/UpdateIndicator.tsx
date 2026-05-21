import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useUpdateStatus } from "@/hooks/useUpdateStatus";

/**
 * Compact icon button shown in the top bar when a new release is available.
 * Clicking it opens the GitHub release page.
 */
export function UpdateIndicator() {
  const { status, isAvailable, openRelease } = useUpdateStatus();

  if (!isAvailable) return null;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => openRelease()}
          className="relative text-muted-foreground hover:text-foreground"
          aria-label={`Update available: version ${status.latestVersion}`}
        >
          <Download className="h-4 w-4" />
          <span className="absolute right-1.5 top-1.5 flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
          </span>
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom">
        <p className="text-xs">
          Update available — v{status.latestVersion}
        </p>
      </TooltipContent>
    </Tooltip>
  );
}
