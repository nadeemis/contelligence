import { format, formatDistanceToNow } from "date-fns";

/**
 * Format a date string for display (e.g. "Feb 28, 06:01 AM")
 */
export function formatDate(dateStr: string): string {
  try {
    return format(new Date(dateStr), "MMM d, HH:mm");
  } catch {
    return dateStr;
  }
}

/**
 * Format a date as relative time (e.g. "3 minutes ago")
 */
export function formatRelativeTime(dateStr: string): string {
  try {
    return formatDistanceToNow(new Date(dateStr), { addSuffix: true });
  } catch {
    return dateStr;
  }
}

/**
 * Format bytes into human-readable size
 */
export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

/**
 * Format seconds into human-readable duration
 */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

/**
 * Status icon mapping for session statuses
 */
export function statusIcon(status: string): string {
  switch (status) {
    case "completed":
      return "✅";
    case "active":
    case "running":
      return "🔄";
    case "failed":
      return "❌";
    case "cancelled":
      return "🚫";
    case "waiting_approval":
    case "waiting":
      return "⏳";
    default:
      return "•";
  }
}
