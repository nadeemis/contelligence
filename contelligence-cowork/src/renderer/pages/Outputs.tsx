import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Download, Copy, FolderOpen, FileText, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { agentApi, getBaseUrlSync } from "@/lib/api";
import { formatBytes, formatDate } from "@/lib/format";
import type { OutputArtifact, SessionRecord } from "@/types";

/* ── Session Output Group ─────────────────── */
function SessionOutputGroup({
  session,
  onSelect,
  selectedId,
}: {
  session: SessionRecord;
  onSelect: (output: OutputArtifact) => void;
  selectedId: string | undefined;
}) {
  const { data: outputs } = useQuery({
    queryKey: ["session-outputs", session.id],
    queryFn: () => agentApi.getSessionOutputs(session.id),
  });

  if (!outputs || outputs.length === 0) return null;

  return (
    <div>
      <div className="flex items-center gap-2 py-2">
        <FolderOpen className="h-4 w-4 text-warning" />
        <span className="text-sm font-medium text-foreground">
          Session {session.id.slice(0, 8)}
        </span>
        <span className="text-xs text-muted-foreground truncate">
          — "{session.instruction.slice(0, 60)}..."
        </span>
      </div>
      <div className="ml-6 space-y-1">
        {outputs.map((output) => (
          <button
            key={output.id}
            onClick={() => onSelect(output)}
            className={`w-full text-left flex items-center justify-between rounded-lg px-3 py-2 cursor-pointer transition-colors ${
              selectedId === output.id
                ? "bg-primary/10 border border-primary/20"
                : "hover:bg-secondary/50"
            }`}
          >
            <div className="flex items-center gap-2">
              <FileText className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-sm text-foreground font-mono">{output.file_name}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground">{formatBytes(output.size_bytes)}</span>
              <span className="text-xs text-muted-foreground">{formatDate(output.created_at)}</span>
              <ChevronRight className="h-3 w-3 text-muted-foreground" />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── Output Preview ───────────────────────── */
function OutputPreview({ output }: { output: OutputArtifact }) {
  const downloadUrl = `${getBaseUrlSync()}/agent/sessions/${output.session_id}/outputs/${output.id}/download`;

  const isTextPreviewable =
    output.size_bytes <= 1_000_000 &&
    (output.content_type.startsWith("text/") ||
      output.content_type.includes("json") ||
      output.content_type.includes("csv"));

  const { data: content } = useQuery({
    queryKey: ["output-content", output.id],
    queryFn: async () => {
      const res = await fetch(downloadUrl);
      return res.text();
    },
    enabled: isTextPreviewable,
  });

  return (
    <Card className="bg-card border-border sticky top-6">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-foreground text-sm font-mono">{output.file_name}</CardTitle>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="border-border text-muted-foreground hover:text-foreground h-7 text-xs"
            onClick={() => window.open(downloadUrl, "_blank")}
          >
            <Download className="h-3 w-3 mr-1" /> Download
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="border-border text-muted-foreground hover:text-foreground h-7 text-xs"
            onClick={() => {
              navigator.clipboard.writeText(output.blob_url || downloadUrl);
              toast.success("URL copied");
            }}
          >
            <Copy className="h-3 w-3 mr-1" /> Copy URL
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-xs text-muted-foreground mb-3 space-x-3">
          <span>{output.content_type}</span>
          <span>{formatBytes(output.size_bytes)}</span>
          <span>{formatDate(output.created_at)}</span>
        </div>
        {content ? (
          <pre className="rounded-lg bg-background p-4 text-xs font-mono text-foreground overflow-auto max-h-[60vh] whitespace-pre-wrap">
            {content}
          </pre>
        ) : (
          <div className="text-center text-muted-foreground py-10">
            Preview not available for this file type. Click Download to view.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ── Main Page ────────────────────────────── */
const Outputs = () => {
  const [selectedOutput, setSelectedOutput] = useState<OutputArtifact | null>(null);

  const { data: sessions, isLoading } = useQuery({
    queryKey: ["sessions", "completed"],
    queryFn: () => agentApi.getSessions({ status: "completed", limit: 50 }),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-foreground font-display tracking-wide">Outputs</h1>

      <div className="flex gap-6">
        {/* Left panel: file browser */}
        <div className="flex-1 min-w-0">
          <Card className="bg-card border-border">
            <CardContent className="p-4 space-y-1">
              {isLoading
                ? Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="space-y-2 py-2">
                      <Skeleton className="h-4 w-48" />
                      <Skeleton className="h-8 w-full ml-6" />
                      <Skeleton className="h-8 w-full ml-6" />
                    </div>
                  ))
                : sessions?.map((session) => (
                    <SessionOutputGroup
                      key={session.id}
                      session={session}
                      onSelect={setSelectedOutput}
                      selectedId={selectedOutput?.id}
                    />
                  ))}
              {!isLoading && (!sessions || sessions.length === 0) && (
                <p className="text-center text-muted-foreground py-8">
                  No sessions with outputs found.
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right panel: preview */}
        <div className="flex-1 min-w-0">
          {selectedOutput ? (
            <OutputPreview output={selectedOutput} />
          ) : (
            <div className="flex items-center justify-center h-64 text-muted-foreground">
              Select a file to preview
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Outputs;