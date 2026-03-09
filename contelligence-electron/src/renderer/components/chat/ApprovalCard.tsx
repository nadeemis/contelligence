import { AlertTriangle, CheckCircle, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface ApprovalCardProps {
  toolName: string;
  arguments: Record<string, unknown>;
  reason: string;
  onApprove: () => void;
  onDeny: () => void;
  onApproveAll: () => void;
}

export function ApprovalCard({
  toolName,
  arguments: args,
  reason,
  onApprove,
  onDeny,
  onApproveAll,
}: ApprovalCardProps) {
  return (
    <div className="flex gap-3">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-warning/10">
        <AlertTriangle className="h-3.5 w-3.5 text-warning" />
      </div>
      <div className="rounded-lg border border-warning/30 bg-warning/5 p-3 max-w-[80%] w-full">
        <div className="flex items-center gap-2 mb-2">
          <Badge className="bg-warning/10 text-warning text-xs border-0">approval_required</Badge>
          <span className="text-sm font-mono text-foreground">{toolName}</span>
        </div>
        <p className="text-sm text-muted-foreground mb-3">{reason}</p>
        <pre className="mb-3 p-2 rounded bg-background/50 text-xs font-mono text-foreground overflow-x-auto">
          {JSON.stringify(args, null, 2)}
        </pre>
        <div className="flex gap-2">
          <Button size="sm" className="bg-success hover:bg-success/90 text-success-foreground h-7 text-xs" onClick={onApprove}>
            <CheckCircle className="h-3 w-3 mr-1" /> Approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="border-destructive text-destructive hover:bg-destructive/10 h-7 text-xs"
            onClick={onDeny}
          >
            <XCircle className="h-3 w-3 mr-1" /> Deny
          </Button>
          <Button size="sm" variant="outline" className="border-border h-7 text-xs text-muted-foreground" onClick={onApproveAll}>
            Approve All
          </Button>
        </div>
      </div>
    </div>
  );
}
