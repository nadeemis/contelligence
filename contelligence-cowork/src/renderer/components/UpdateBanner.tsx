import { useEffect, useState } from "react";
import { X, Download, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useUpdateStatus } from "@/hooks/useUpdateStatus";

const DISMISS_KEY_PREFIX = "update:dismissed:";

/**
 * Top-of-window banner that announces a new release. Dismissal is remembered
 * per version so a fresh release re-triggers the banner. Hidden whenever no
 * update is available.
 */
export function UpdateBanner() {
  const { status, isAvailable, openRelease, openDownloads } = useUpdateStatus();
  const [dismissed, setDismissed] = useState(false);

  // When the available version changes, re-evaluate the dismissal flag.
  useEffect(() => {
    if (!status.latestVersion) {
      setDismissed(false);
      return;
    }
    const key = `${DISMISS_KEY_PREFIX}${status.latestVersion}`;
    setDismissed(window.localStorage.getItem(key) === "1");
  }, [status.latestVersion]);

  if (!isAvailable || dismissed || !status.latestVersion) return null;

  const handleDismiss = () => {
    window.localStorage.setItem(
      `${DISMISS_KEY_PREFIX}${status.latestVersion}`,
      "1",
    );
    setDismissed(true);
  };

  return (
    <div
      role="status"
      className="flex items-center justify-between gap-3 border-b border-primary/20 bg-primary/10 px-4 py-2 text-sm text-foreground"
    >
      <div className="flex items-center gap-2 min-w-0">
        <Download className="h-4 w-4 shrink-0 text-primary" />
        <span className="truncate">
          <strong>Contelligence v{status.latestVersion}</strong> is available
          {status.currentVersion ? (
            <span className="text-muted-foreground">
              {" "}
              — you're on v{status.currentVersion}
            </span>
          ) : null}
        </span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => openRelease()}
          className="h-7 px-2 text-xs"
        >
          <ExternalLink className="h-3 w-3 mr-1" />
          Release notes
        </Button>
        <Button
          size="sm"
          onClick={() => openDownloads()}
          className="h-7 px-2 text-xs"
        >
          <Download className="h-3 w-3 mr-1" />
          Download
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={handleDismiss}
          aria-label="Dismiss update notification"
          className="h-7 w-7 text-muted-foreground hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
